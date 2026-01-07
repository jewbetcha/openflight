use anyhow::{Context, Result};
use serde_json::json;
use std::io::Write;
use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::time::timeout;

use crate::shot::Shot;

/// OpenGolfSim integration client with persistent TCP connection
pub struct OpenGolfSimClient {
    host: String,
    port: u16,
    use_http: bool,
    tcp_stream: Arc<Mutex<Option<TcpStream>>>,
}

impl OpenGolfSimClient {
    pub fn new(host: String, port: u16, use_http: bool) -> Self {
        Self {
            host,
            port,
            use_http,
            tcp_stream: Arc::new(Mutex::new(None)),
        }
    }

    /// Connect to OpenGolfSim and maintain persistent connection
    pub fn connect(&mut self) -> Result<()> {
        let address = format!("{}:{}", self.host, self.port);

        // Check if already connected
        {
            let stream_guard = self.tcp_stream.lock().unwrap();
            if stream_guard.is_some() {
                log::debug!("[OPENGOLFSIM] Already connected to {}", address);
                return Ok(());
            }
        }

        log::info!("[OPENGOLFSIM] Connecting to {}...", address);
        match TcpStream::connect(&address) {
            Ok(stream) => {
                // Set TCP_NODELAY to reduce latency
                if let Err(e) = stream.set_nodelay(true) {
                    log::warn!("[OPENGOLFSIM] Failed to set TCP_NODELAY: {}", e);
                }

                let mut stream_guard = self.tcp_stream.lock().unwrap();
                *stream_guard = Some(stream);
                drop(stream_guard); // Release lock before sending ready status

                log::info!("[OPENGOLFSIM] Connected to {}", address);

                // Send ready status (with small delay for connection to stabilize)
                std::thread::sleep(Duration::from_millis(100));
                if let Err(e) = self.send_device_status_internal("ready") {
                    log::warn!("[OPENGOLFSIM] Failed to send ready status: {}", e);
                    // Don't fail the connection if ready status fails
                } else {
                    log::info!("[OPENGOLFSIM] Device status: ready");
                }

                Ok(())
            }
            Err(e) => {
                log::debug!("[OPENGOLFSIM] Failed to connect to {}: {}", address, e);
                Err(anyhow::anyhow!("TCP connection failed: {}", e))
            }
        }
    }

    /// Disconnect from OpenGolfSim
    pub fn disconnect(&mut self) {
        // Send busy status before disconnecting
        let _ = self.send_device_status_internal("busy");

        let mut stream_guard = self.tcp_stream.lock().unwrap();
        *stream_guard = None;
        log::info!("[OPENGOLFSIM] Disconnected");
    }

    /// Ensure connection is established, reconnect if needed
    fn ensure_connected(&mut self) -> Result<()> {
        // Check if connection exists
        {
            let stream_guard = self.tcp_stream.lock().unwrap();
            if stream_guard.is_some() {
                return Ok(()); // Already connected
            }
        }

        // Connection doesn't exist, try to connect
        log::debug!("[OPENGOLFSIM] Connection not established, attempting to connect...");
        self.connect()
    }

    /// Send shot data to OpenGolfSim
    ///
    /// OpenGolfSim uses TCP sockets, not HTTP. HTTP mode will auto-fallback to TCP.
    /// Uses persistent TCP connection.
    pub async fn send_shot(&mut self, shot: &Shot) -> Result<()> {
        // Ensure we have a connection
        self.ensure_connected()?;

        let shot_data = self.format_shot_data(shot);

        if self.use_http {
            // Try HTTP first, but fall back to TCP if HTTP fails with version error
            match self.send_http(&shot_data).await {
                Ok(()) => Ok(()),
                Err(e)
                    if e.to_string().contains("invalid HTTP version")
                        || e.to_string().contains("HTTP version") =>
                {
                    // HTTP version error suggests it's not HTTP - try TCP instead
                    log::info!("[OPENGOLFSIM] HTTP failed (invalid version), trying TCP instead");
                    self.send_tcp_internal(&shot_data)
                }
                Err(e) => Err(e),
            }
        } else {
            // OpenGolfSim uses TCP by default (persistent connection)
            self.send_tcp_internal(&shot_data)
        }
    }

    /// Send device status (ready/busy) to OpenGolfSim
    pub fn send_device_status(&mut self, status: &str) -> Result<()> {
        self.ensure_connected()?;
        self.send_device_status_internal(status)
    }

    /// Internal method to send device status (assumes connection exists)
    fn send_device_status_internal(&self, status: &str) -> Result<()> {
        let status_data = json!({
            "type": "device",
            "status": status  // "ready" or "busy"
        });
        self.send_tcp_internal(&status_data)
    }

    /// Format shot data for OpenGolfSim API
    ///
    /// OpenGolfSim expects:
    /// - type: "shot"
    /// - unit: "imperial" (mph) or "metric" (m/s)
    /// - shot: { ballSpeed, verticalLaunchAngle, horizontalLaunchAngle, spinSpeed, spinAxis }
    ///
    /// See: https://help.opengolfsim.com/desktop/apis/shot-data/
    fn format_shot_data(&self, shot: &Shot) -> serde_json::Value {
        // OpenGolfSim uses imperial (mph) by default
        // We'll send in imperial since we have ball speed in mph

        // Build the shot object
        let mut shot_obj = json!({
            "ballSpeed": shot.ball_speed_mph,
        });

        // Add launch angles if available (from camera)
        if let Some(vertical) = shot.launch_angle_vertical {
            shot_obj["verticalLaunchAngle"] = json!(vertical);
        }
        if let Some(horizontal) = shot.launch_angle_horizontal {
            shot_obj["horizontalLaunchAngle"] = json!(horizontal);
        }

        // Add spin data if available (we don't have this yet)
        // shot_obj["spinSpeed"] = json!(spin_rpm);
        // shot_obj["spinAxis"] = json!(spin_axis);

        // Build the full payload according to OpenGolfSim API
        json!({
            "type": "shot",
            "unit": "imperial",  // Using mph
            "shot": shot_obj
        })
    }

    /// Send shot data via HTTP POST
    async fn send_http(&self, data: &serde_json::Value) -> Result<()> {
        // Create client on-demand since reqwest::Client doesn't implement Clone
        let client = reqwest::Client::new();

        // Try common OpenGolfSim endpoints
        let endpoints = vec![
            format!("http://{}:{}/api/shot", self.host, self.port),
            format!("http://{}:{}/shot", self.host, self.port),
            format!("http://{}:{}/api/launch-monitor/shot", self.host, self.port),
        ];

        let mut last_error = None;
        for url in &endpoints {
            // Try with longer timeout (5 seconds)
            match timeout(Duration::from_secs(5), client.post(url).json(data).send()).await {
                Ok(Ok(response)) if response.status().is_success() => {
                    log::info!("[OPENGOLFSIM] Shot sent successfully to {}", url);
                    return Ok(());
                }
                Ok(Ok(response)) => {
                    log::debug!(
                        "[OPENGOLFSIM] Endpoint {} returned status: {}",
                        url,
                        response.status()
                    );
                    last_error = Some(format!("HTTP {} from {}", response.status(), url));
                }
                Ok(Err(e)) => {
                    let error_str = e.to_string();
                    // Check for HTTP version errors - might indicate wrong protocol
                    if error_str.contains("invalid HTTP version")
                        || error_str.contains("HTTP version")
                    {
                        log::debug!(
                            "[OPENGOLFSIM] Endpoint {} may not be HTTP - trying TCP instead",
                            url
                        );
                        last_error = Some(format!("Not an HTTP endpoint: {}", url));
                    } else {
                        log::debug!("[OPENGOLFSIM] Endpoint {} error: {}", url, e);
                        last_error = Some(format!("Connection error to {}: {}", url, e));
                    }
                }
                Err(_) => {
                    log::debug!("[OPENGOLFSIM] Endpoint {} timeout", url);
                    last_error = Some(format!("Timeout connecting to {}", url));
                }
            }
        }

        // If all endpoints failed, return error with concise message
        let error_msg = last_error.unwrap_or_else(|| "Unknown error".to_string());
        Err(anyhow::anyhow!("{}", error_msg))
    }

    /// Send data via persistent TCP socket
    ///
    /// OpenGolfSim expects JSON payloads over TCP on port 3111
    /// See: https://help.opengolfsim.com/desktop/apis/shot-data/
    ///
    /// Uses the persistent connection maintained by the client.
    fn send_tcp_internal(&self, data: &serde_json::Value) -> Result<()> {
        let json_str = serde_json::to_string(data).context("Failed to serialize JSON")?;
        let message = format!("{}\n", json_str);

        let mut stream_guard = self.tcp_stream.lock().unwrap();

        if let Some(ref mut stream) = *stream_guard {
            // Try to write to existing connection
            match stream.write_all(message.as_bytes()) {
                Ok(_) => {
                    if let Err(e) = stream.flush() {
                        log::warn!("[OPENGOLFSIM] Flush failed: {}", e);
                        // Still return Ok since write succeeded
                    }
                    log::debug!("[OPENGOLFSIM] Data sent via TCP ({} bytes)", message.len());
                    Ok(())
                }
                Err(e) => {
                    // Connection might be broken, clear it so we reconnect next time
                    log::debug!(
                        "[OPENGOLFSIM] Write failed, connection may be broken: {}",
                        e
                    );
                    *stream_guard = None;
                    Err(anyhow::anyhow!("TCP write failed: {}", e))
                }
            }
        } else {
            Err(anyhow::anyhow!("TCP connection not established"))
        }
    }
}
