use crate::shot::{ClubType, Direction, Shot, SpeedReading};
use anyhow::Result;
use std::sync::Arc;
use std::time::{Duration, Instant};

// Trait for radar interface (real or mock)
pub trait RadarInterface {
    fn connect(&mut self) -> Result<()>;
    fn disconnect(&mut self);
    fn get_info(&mut self) -> Result<std::collections::HashMap<String, String>>;
    fn configure_for_golf(&mut self) -> Result<()>;
    fn read_speed(&mut self) -> Result<Option<SpeedReading>>;
}

pub struct LaunchMonitor<R: RadarInterface> {
    radar: R,
    show_live: bool,
    opengolfsim_client: Option<Arc<std::sync::Mutex<crate::opengolfsim::OpenGolfSimClient>>>,

    // Shot detection state
    current_readings: Vec<SpeedReading>,
    last_reading_time: Option<Instant>,
    shot_start_time: Option<Instant>,

    // Configuration constants (matching Python version)
    min_club_speed_mph: f64,
    max_club_speed_mph: f64,
    min_ball_speed_mph: f64,
    max_ball_speed_mph: f64,
    shot_timeout_sec: f64,
    min_readings_for_shot: usize,
    club_ball_window_sec: f64,
    club_speed_min_ratio: f64,
    club_speed_max_ratio: f64,
    min_magnitude: f64,
    max_magnitude: f64,
    max_shot_duration_sec: f64,
    smash_factor_min: f64,
    smash_factor_max: f64,

    current_club: ClubType,
    detect_club_speed: bool,
}

impl<R: RadarInterface> LaunchMonitor<R> {
    pub fn new(radar: R, show_live: bool) -> Self {
        Self::with_opengolfsim(radar, show_live, None)
    }

    pub fn with_opengolfsim(
        radar: R,
        show_live: bool,
        mut opengolfsim_client: Option<crate::opengolfsim::OpenGolfSimClient>,
    ) -> Self {
        // Connect to OpenGolfSim if enabled
        if let Some(ref mut client) = opengolfsim_client {
            match client.connect() {
                Ok(()) => {
                    // Wait a bit for OpenGolfSim to be ready
                    std::thread::sleep(Duration::from_millis(500));
                    log::info!("[OPENGOLFSIM] Ready to send shots");
                }
                Err(e) => {
                    log::info!("[OPENGOLFSIM] OpenGolfSim not available at startup: {}. Will retry when shots are detected.", e);
                }
            }
        }

        // Wrap in Arc<Mutex<>> for thread-safe access
        let opengolfsim_client = opengolfsim_client.map(|c| Arc::new(std::sync::Mutex::new(c)));

        Self {
            radar,
            show_live,
            opengolfsim_client,
            current_readings: Vec::new(),
            last_reading_time: None,
            shot_start_time: None,
            min_club_speed_mph: 30.0,
            max_club_speed_mph: 140.0,
            min_ball_speed_mph: 30.0,
            max_ball_speed_mph: 220.0,
            shot_timeout_sec: 0.5,
            min_readings_for_shot: 3,
            club_ball_window_sec: 0.3,
            club_speed_min_ratio: 0.50,
            club_speed_max_ratio: 0.85,
            min_magnitude: 20.0,
            max_magnitude: 10000.0, //increase size for mock
            max_shot_duration_sec: 0.3,
            smash_factor_min: 1.1,
            smash_factor_max: 1.7,
            current_club: ClubType::Driver,
            detect_club_speed: true,
        }
    }

    pub fn run(&mut self) -> Result<()> {
        // Connection already established in with_opengolfsim, ready status already sent

        // Setup Ctrl+C handler
        let (tx, rx) = std::sync::mpsc::channel();
        ctrlc::set_handler(move || {
            let _ = tx.send(());
        })?;

        loop {
            // Check for Ctrl+C
            if rx.try_recv().is_ok() {
                println!("\n");
                println!("Stopping...");
                // Process any pending shot
                if !self.current_readings.is_empty() {
                    self.process_shot();
                }
                break;
            }

            // Read speed from radar (works with both real and mock)
            match self.radar.read_speed() {
                Ok(Some(reading)) => {
                    self.on_reading(reading);
                }
                Ok(None) => {
                    // No reading available, check for shot timeout
                    self.check_shot_timeout();
                }
                Err(e) => {
                    log::warn!("Error reading from radar: {}", e);
                }
            }

            // Small sleep to avoid busy-waiting
            std::thread::sleep(Duration::from_millis(10));
        }

        Ok(())
    }

    fn on_reading(&mut self, reading: SpeedReading) {
        let now = Instant::now();

        // Show live reading if requested
        if self.show_live {
            print!("\r  [{:.1} {}]  ", reading.speed, "mph");
            std::io::Write::flush(&mut std::io::stdout()).ok();
        }

        // Determine valid speed range based on detection mode
        let min_speed = if self.detect_club_speed {
            self.min_club_speed_mph
        } else {
            self.min_ball_speed_mph
        };

        // Filter by realistic speeds
        if reading.speed < min_speed || reading.speed > self.max_ball_speed_mph {
            log::debug!(
                "[FILTER] Speed {:.1} outside range {}-{}",
                reading.speed,
                min_speed,
                self.max_ball_speed_mph
            );
            return;
        }

        // Only accept outbound readings (ball/club moving away from radar)
        if reading.direction != Direction::Outbound {
            log::debug!("[FILTER] Direction is not outbound");
            return;
        }

        // Filter by magnitude (signal strength)
        if let Some(magnitude) = reading.magnitude {
            if magnitude < self.min_magnitude || magnitude > self.max_magnitude {
                log::warn!(
                    "[FILTER] Magnitude {:.1} outside range {}-{}",
                    magnitude,
                    self.min_magnitude,
                    self.max_magnitude
                );
                return;
            }
        }

        log::debug!(
            "[ACCEPTED] {:.1} mph outbound - buffered: {}",
            reading.speed,
            self.current_readings.len()
        );

        // Check if this is part of current shot or new shot
        if let Some(last_time) = self.last_reading_time {
            if now.duration_since(last_time).as_secs_f64() > self.shot_timeout_sec {
                // Previous shot complete, process it
                log::debug!(
                    "[TIMEOUT] Processing shot with {} readings",
                    self.current_readings.len()
                );
                self.process_shot();
            }
        }

        // Track shot start time
        if self.current_readings.is_empty() {
            self.shot_start_time = Some(now);
        }

        // Add to current readings
        self.current_readings.push(reading);
        self.last_reading_time = Some(now);
    }

    fn check_shot_timeout(&mut self) {
        if let Some(last_time) = self.last_reading_time {
            if last_time.elapsed().as_secs_f64() > self.shot_timeout_sec {
                if !self.current_readings.is_empty() {
                    log::debug!(
                        "[TIMEOUT] Processing shot with {} readings",
                        self.current_readings.len()
                    );
                    self.process_shot();
                }
            }
        }
    }

    fn process_shot(&mut self) {
        if self.current_readings.len() < self.min_readings_for_shot {
            log::debug!(
                "[REJECTED] Only {} readings (need {})",
                self.current_readings.len(),
                self.min_readings_for_shot
            );
            self.current_readings.clear();
            return;
        }

        // Sort readings by timestamp for temporal analysis
        let mut sorted_readings = self.current_readings.clone();
        sorted_readings.sort_by(|a, b| a.timestamp.partial_cmp(&b.timestamp).unwrap());

        // Check max shot duration using timestamps (not wall-clock time)
        if sorted_readings.len() >= 2 {
            let first_timestamp = sorted_readings.first().unwrap().timestamp;
            let last_timestamp = sorted_readings.last().unwrap().timestamp;
            let duration = last_timestamp - first_timestamp;
            if duration > self.max_shot_duration_sec {
                log::warn!(
                    "[REJECTED] Shot duration {:.3}s exceeds max {:.3}s",
                    duration,
                    self.max_shot_duration_sec
                );
                self.current_readings.clear();
                return;
            }
        }

        // Find ball: peak speed reading
        let ball_reading = sorted_readings
            .iter()
            .max_by(|a, b| a.speed.partial_cmp(&b.speed).unwrap())
            .unwrap();
        let ball_speed = ball_reading.speed;
        let ball_time = ball_reading.timestamp;

        // Get peak magnitude
        let peak_mag = sorted_readings
            .iter()
            .filter_map(|r| r.magnitude)
            .fold(0.0, f64::max);
        let peak_mag = if peak_mag > 0.0 { Some(peak_mag) } else { None };

        // Find club speed
        let club_speed = if self.detect_club_speed {
            self.find_club_speed(&sorted_readings, ball_speed, ball_time)
        } else {
            None
        };

        log::info!(
            "[SHOT ANALYSIS] Ball={:.1} mph, Club={}, Readings={}",
            ball_speed,
            club_speed
                .map(|s| format!("{:.1} mph", s))
                .unwrap_or_else(|| "N/A".to_string()),
            sorted_readings.len()
        );

        // Create shot
        let shot = Shot {
            ball_speed_mph: ball_speed,
            timestamp: chrono::Utc::now(),
            club_speed_mph: club_speed,
            peak_magnitude: peak_mag,
            readings: self.current_readings.clone(),
            club: self.current_club,
            launch_angle_vertical: None,
            launch_angle_horizontal: None,
            launch_angle_confidence: None,
        };

        // Print shot metrics to stdout
        self.print_shot(&shot);

        // Clear for next shot
        self.current_readings.clear();
        self.last_reading_time = None;
        self.shot_start_time = None;
    }

    fn find_club_speed(
        &self,
        readings: &[SpeedReading],
        ball_speed: f64,
        ball_time: f64,
    ) -> Option<f64> {
        if readings.len() < 2 {
            return None;
        }

        // Speed range: club should be 50-85% of ball speed
        let club_speed_min = self
            .min_club_speed_mph
            .max(ball_speed * self.club_speed_min_ratio);
        let club_speed_max = self
            .max_club_speed_mph
            .min(ball_speed * self.club_speed_max_ratio);

        // Find candidate club readings (before ball, in speed range)
        let club_candidates: Vec<&SpeedReading> = readings
            .iter()
            .filter(|r| {
                let r_time = r.timestamp;

                // Must be before the ball reading
                if r_time >= ball_time {
                    return false;
                }

                // Must be within time window (not too early)
                if ball_time - r_time > self.club_ball_window_sec {
                    return false;
                }

                // Must be in realistic club speed range
                if !(club_speed_min <= r.speed && r.speed <= club_speed_max) {
                    return false;
                }

                // Must be less than ball speed
                if r.speed >= ball_speed {
                    return false;
                }

                true
            })
            .collect();

        if club_candidates.is_empty() {
            return None;
        }

        // Select best candidate: prefer highest magnitude (larger RCS = club head)
        let club_reading = club_candidates
            .iter()
            .filter(|c| c.magnitude.is_some())
            .max_by(|a, b| {
                a.magnitude
                    .unwrap()
                    .partial_cmp(&b.magnitude.unwrap())
                    .unwrap()
            })
            .or_else(|| {
                // No magnitude data - use reading closest in time to ball
                club_candidates
                    .iter()
                    .max_by(|a, b| a.timestamp.partial_cmp(&b.timestamp).unwrap())
            })?;

        // Validate smash factor
        let smash = ball_speed / club_reading.speed;
        if !(self.smash_factor_min <= smash && smash <= self.smash_factor_max) {
            log::debug!(
                "[CLUB REJECTED] Smash factor {:.2} outside range {}-{}",
                smash,
                self.smash_factor_min,
                self.smash_factor_max
            );
            return None;
        }

        log::info!(
            "[CLUB DETECTED] {:.1} mph (smash: {:.2})",
            club_reading.speed,
            smash
        );

        Some(club_reading.speed)
    }

    fn print_shot(&self, shot: &Shot) {
        let (carry_low, carry_high) = shot.estimated_carry_range();

        println!();
        println!("{}", "-".repeat(40));
        if let Some(club_speed) = shot.club_speed_mph {
            println!("  Club Speed:   {:.1} mph", club_speed);
        }
        println!("  Ball Speed:   {:.1} mph", shot.ball_speed_mph);
        if let Some(smash) = shot.smash_factor() {
            println!("  Smash Factor: {:.2}", smash);
        }
        println!("  Est. Carry:   {:.0} yards", shot.estimated_carry_yards());
        println!("  Range:        {:.0}-{:.0} yards", carry_low, carry_high);
        if let Some(mag) = shot.peak_magnitude {
            println!("  Signal:       {:.0}", mag);
        }
        println!("{}", "-".repeat(40));
        println!();

        // Send to OpenGolfSim if enabled (spawn in background thread)
        if let Some(ref client) = self.opengolfsim_client {
            let client = client.clone(); // Arc clones the pointer, not the data
            let shot = shot.clone();
            std::thread::spawn(move || {
                let rt = tokio::runtime::Runtime::new().unwrap();
                rt.block_on(async move {
                    if let Ok(mut client) = client.lock() {
                        log::debug!("[OPENGOLFSIM] Attempting to send shot (ballSpeed: {:.1} mph)", shot.ball_speed_mph);
                        match client.send_shot(&shot).await {
                            Ok(_) => {
                                log::info!("[OPENGOLFSIM] Shot sent successfully");
                            }
                            Err(e) => {
                                // Log connection errors as debug (OpenGolfSim not running)
                                // Log other errors as warnings
                                let error_str = e.to_string();
                                if error_str.contains("refused") || error_str.contains("timeout") || 
                                   error_str.contains("connection") || error_str.contains("not established") {
                                    log::debug!("[OPENGOLFSIM] Could not send shot (OpenGolfSim may not be running): {}", error_str);
                                } else {
                                    log::warn!("[OPENGOLFSIM] Failed to send shot: {}", e);
                                }
                            }
                        }
                    } else {
                        log::warn!("[OPENGOLFSIM] Failed to acquire client lock");
                    }
                });
            });
        }
    }
}
