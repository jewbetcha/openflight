use anyhow::{Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use std::time::{Duration, Instant};
use serialport::SerialPort;

use crate::shot::{Direction, SpeedReading};
use crate::launch_monitor::RadarInterface;

pub struct OPS243Radar {
    port_name: Option<String>,
    port: Option<Box<dyn SerialPort>>,
    unit: String,
    json_mode: bool,
    magnitude_enabled: bool,
}

impl OPS243Radar {
    const DEFAULT_BAUD: u32 = 57600;
    const DEFAULT_TIMEOUT: Duration = Duration::from_secs(1);

    pub fn new(port: Option<String>) -> Result<Self> {
        Ok(Self {
            port_name: port,
            port: None,
            unit: "mph".to_string(),
            json_mode: false,
            magnitude_enabled: false,
        })
    }

    fn connect_internal(&mut self) -> Result<()> {
        let port_name = if let Some(ref name) = self.port_name {
            name.clone()
        } else {
            self.find_radar_port()
                .context("No OPS243 radar found. Check USB connection.")?
        };

        let builder = serialport::new(&port_name, Self::DEFAULT_BAUD)
            .timeout(Self::DEFAULT_TIMEOUT);

        let port = builder.open()
            .with_context(|| format!("Failed to connect to {}", port_name))?;

        // Give sensor time to initialize
        std::thread::sleep(Duration::from_millis(500));
        
        // Flush any startup data
        port.clear(serialport::ClearBuffer::Input)?;

        self.port = Some(port);
        self.port_name = Some(port_name);

        Ok(())
    }

    fn disconnect_internal(&mut self) {
        if let Some(port) = self.port.take() {
            let _ = port.clear(serialport::ClearBuffer::All);
        }
    }

    fn find_radar_port(&self) -> Option<String> {
        // Try common port names
        let common_ports = if cfg!(target_os = "linux") {
            vec!["/dev/ttyACM0", "/dev/ttyUSB0", "/dev/ttyACM1"]
        } else if cfg!(target_os = "macos") {
            vec!["/dev/tty.usbmodem*", "/dev/tty.usbserial*"]
        } else if cfg!(target_os = "windows") {
            vec!["COM3", "COM4", "COM5", "COM6"]
        } else {
            vec![]
        };

        // Check available ports
        for port_info in serialport::available_ports().unwrap_or_default() {
            if common_ports.iter().any(|&p| port_info.port_name.contains(p.trim_start_matches("/dev/"))) {
                return Some(port_info.port_name);
            }
        }

        // Fallback: use first available port
        serialport::available_ports()
            .ok()?
            .first()
            .map(|p| p.port_name.clone())
    }

    fn send_command(&mut self, cmd: &str) -> Result<String> {
        let port = self.port.as_mut()
            .context("Not connected to radar")?;

        // Clear input buffer
        port.clear(serialport::ClearBuffer::Input)?;

        // Send command
        let cmd_bytes = cmd.as_bytes();
        port.write_all(cmd_bytes)?;

        // For commands that require carriage return
        if cmd.contains('=') || cmd.contains('>') || cmd.contains('<') {
            port.write_all(b"\r")?;
        }

        // Wait for response
        std::thread::sleep(Duration::from_millis(100));

        // Read response
        let mut response = String::new();
        let mut buffer = [0u8; 256];
        let start = Instant::now();

        while start.elapsed() < Duration::from_millis(500) {
            match port.read(&mut buffer) {
                Ok(n) if n > 0 => {
                    response.push_str(&String::from_utf8_lossy(&buffer[..n]));
                    std::thread::sleep(Duration::from_millis(50));
                }
                Ok(_) => break,
                Err(_) => break,
            }
        }

        Ok(response.trim().to_string())
    }

    fn get_info_internal(&mut self) -> Result<HashMap<String, String>> {
        let response = self.send_command("??")?;
        let mut info = HashMap::new();

        for line in response.lines() {
            let line = line.trim();
            if line.starts_with('{') && line.ends_with('}') {
                if let Ok(data) = serde_json::from_str::<Value>(line) {
                    if let Value::Object(map) = data {
                        for (key, value) in map {
                            info.insert(key, value.to_string().trim_matches('"').to_string());
                        }
                    }
                }
            }
        }

        Ok(info)
    }

    fn configure_for_golf_internal(&mut self) -> Result<()> {
        // Set units to MPH
        self.send_command("US")?;
        self.unit = "mph".to_string();

        // 50kHz sample rate - max detectable speed ~347 mph
        self.send_command("SL")?;

        // 512 buffer for faster update rate
        self.send_command("S<")?;

        // Enable magnitude reporting
        self.send_command("OM")?;
        self.magnitude_enabled = true;

        // Clear direction filter to get both directions
        self.send_command("R|")?;

        // Minimum speed 10 mph
        self.send_command("R>10")?;

        // Max transmit power
        self.send_command("P0")?;

        // Enable JSON output
        self.send_command("OJ")?;
        self.json_mode = true;

        // Enable multi-object reporting (O4)
        self.send_command("O4")?;

        // Disable peak averaging
        self.send_command("K-")?;

        // Re-enable JSON after O4
        self.send_command("OJ")?;

        Ok(())
    }

    fn read_speed_internal(&mut self) -> Result<Option<SpeedReading>> {
        let port = self.port.as_mut()
            .context("Not connected to radar")?;

        // Try to read available bytes
        let mut buffer = vec![0u8; 1024];
        match port.read(&mut buffer) {
            Ok(n) if n > 0 => {
                // Find first complete line (ending with \n or \r\n)
                let data = &buffer[..n];
                let mut line_end = None;
                
                for (i, &byte) in data.iter().enumerate() {
                    if byte == b'\n' {
                        line_end = Some(i);
                        break;
                    }
                }

                if let Some(end) = line_end {
                    let line = String::from_utf8_lossy(&data[..end]).trim().to_string();
                    if !line.is_empty() {
                        return self.parse_reading(&line);
                    }
                } else {
                    // No newline found, might be partial line - try parsing anyway
                    let line = String::from_utf8_lossy(data).trim().to_string();
                    if !line.is_empty() && (line.starts_with('{') || line.parse::<f64>().is_ok()) {
                        return self.parse_reading(&line);
                    }
                }
            }
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::TimedOut => {}
            Err(e) => return Err(anyhow::anyhow!("Serial read error: {}", e)),
        }

        Ok(None)
    }

    fn parse_reading(&self, line: &str) -> Result<Option<SpeedReading>> {
        if self.json_mode && line.starts_with('{') {
            // Parse JSON format
            let data: Value = serde_json::from_str(line)
                .context("Failed to parse JSON reading")?;

            let speed_data = data.get("speed");
            let magnitude_data = data.get("magnitude");

            let speed = if let Some(Value::Array(arr)) = speed_data {
                // Multi-object mode - use first (strongest) reading
                arr.first()
                    .and_then(|v| v.as_f64())
                    .context("No speed in array")?
            } else {
                speed_data
                    .and_then(|v| v.as_f64())
                    .context("No speed value")?
            };

            let magnitude = if let Some(Value::Array(arr)) = magnitude_data {
                arr.first().and_then(|v| v.as_f64())
            } else {
                magnitude_data.and_then(|v| v.as_f64())
            };

            // Direction from sign of speed value
            // Negative = OUTBOUND (away from radar - golf ball flight)
            // Positive = INBOUND (toward radar - backswing)
            let direction = if speed > 0.0 {
                Direction::Inbound
            } else {
                Direction::Outbound
            };

            Ok(Some(SpeedReading {
                speed: speed.abs(),
                direction,
                magnitude,
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs_f64(),
            }))
        } else {
            // Plain number format
            let speed: f64 = line.parse()
                .context("Failed to parse speed as number")?;

            let direction = if speed > 0.0 {
                Direction::Inbound
            } else {
                Direction::Outbound
            };

            Ok(Some(SpeedReading {
                speed: speed.abs(),
                direction,
                magnitude: None,
                timestamp: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs_f64(),
            }))
        }
    }
}

impl RadarInterface for OPS243Radar {
    fn connect(&mut self) -> Result<()> {
        self.connect_internal()
    }

    fn disconnect(&mut self) {
        self.disconnect_internal();
    }

    fn get_info(&mut self) -> Result<std::collections::HashMap<String, String>> {
        self.get_info_internal()
    }

    fn configure_for_golf(&mut self) -> Result<()> {
        self.configure_for_golf_internal()
    }

    fn read_speed(&mut self) -> Result<Option<SpeedReading>> {
        self.read_speed_internal()
    }
}

impl Drop for OPS243Radar {
    fn drop(&mut self) {
        self.disconnect_internal();
    }
}

