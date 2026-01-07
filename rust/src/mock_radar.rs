use anyhow::Result;
use rand::Rng;
use std::collections::HashMap;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use crate::shot::{Direction, SpeedReading};

/// Mock radar that simulates realistic golf shot readings for testing.
pub struct MockRadar {
    shot_tx: mpsc::Sender<()>,
    reading_rx: mpsc::Receiver<SpeedReading>,
    shot_interval: Duration,
    auto_shot: bool,
}

impl MockRadar {
    pub fn new(shot_interval_secs: f64, auto_shot: bool) -> Self {
        let (shot_tx, shot_rx) = mpsc::channel();
        let (reading_tx, reading_rx) = mpsc::channel();

        // Background thread that generates readings
        thread::spawn(move || {
            let mut rng = rand::thread_rng();
            let mut shot_number = 0;

            loop {
                // Wait for shot trigger or auto-generate
                if auto_shot {
                    thread::sleep(Duration::from_secs_f64(shot_interval_secs));
                } else {
                    match shot_rx.recv() {
                        Ok(_) => {}
                        Err(_) => break, // Channel closed
                    }
                }

                shot_number += 1;
                println!("\n[MOCK] Simulating shot #{}...", shot_number);

                // Generate a realistic shot sequence
                Self::generate_shot_sequence(&mut rng, &reading_tx, shot_number);
            }
        });

        Self {
            shot_tx,
            reading_rx,
            shot_interval: Duration::from_secs_f64(shot_interval_secs),
            auto_shot,
        }
    }

    fn generate_shot_sequence(
        rng: &mut impl Rng,
        tx: &mpsc::Sender<SpeedReading>,
        shot_number: i32,
    ) {
        // Generate realistic shot parameters
        // Ball speed: 80-180 mph (typical range)
        // Club speed: 60-120 mph (typically 60-70% of ball speed)
        let ball_speed = if shot_number % 5 == 0 {
            // Every 5th shot is a "big hit"
            rng.gen_range(150.0..180.0)
        } else if shot_number % 3 == 0 {
            // Every 3rd shot is a "weak hit"
            rng.gen_range(80.0..110.0)
        } else {
            // Normal shot
            rng.gen_range(110.0..150.0)
        };

        let smash_factor = rng.gen_range(1.35..1.55); // Typical range
        let club_speed = ball_speed / smash_factor;

        // Base timestamp for the shot (time of first club reading)
        let base_timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();

        // Generate club readings first (before impact)
        // Club appears 30-50ms before ball (reduced to stay under 300ms total)
        let club_duration_ms = rng.gen_range(30..50);
        let club_duration = Duration::from_millis(club_duration_ms);
        let club_readings = rng.gen_range(2..3); // Reduced to 2-3 readings

        // Generate all club readings and send them quickly
        let mut club_reading_list = Vec::new();
        for i in 0..club_readings {
            let elapsed_ms = i * 20; // 20ms between readings
            if elapsed_ms < club_duration_ms {
                let elapsed = Duration::from_millis(elapsed_ms);
                let t = elapsed.as_secs_f64() / club_duration.as_secs_f64();
                // Club speed ramps up during downswing
                let speed = club_speed * (0.7 + 0.3 * t) + rng.gen_range(-2.0..2.0);
                let magnitude = rng.gen_range(800.0..1500.0); // Club has higher RCS

                // Timestamp is base + elapsed time from first club reading
                let timestamp = base_timestamp + elapsed_ms as f64 / 1000.0;

                club_reading_list.push(SpeedReading {
                    speed: speed.max(15.0),
                    direction: Direction::Outbound,
                    magnitude: Some(magnitude),
                    timestamp,
                });
            }
        }

        // Small gap before ball (impact moment) - 10ms
        let gap_ms = 10;

        // Generate ball readings (after impact)
        // Total shot must be < 300ms, so: club (max 50ms) + gap (10ms) + ball (max 240ms) = 300ms
        let ball_duration_ms = rng.gen_range(100..240);
        let ball_duration = Duration::from_millis(ball_duration_ms);
        let ball_readings = rng.gen_range(4..7); // Reduced to 4-7 readings

        // Generate all ball readings
        let mut ball_reading_list = Vec::new();
        for i in 0..ball_readings {
            let elapsed_ms = i * 20; // 20ms between readings
            if elapsed_ms < ball_duration_ms {
                let elapsed = Duration::from_millis(elapsed_ms);
                let t = elapsed.as_secs_f64() / ball_duration.as_secs_f64();
                // Ball speed starts high and decays slightly (drag)
                let speed = ball_speed * (1.0 - 0.05 * t) + rng.gen_range(-3.0..3.0);
                let magnitude = rng.gen_range(200.0..600.0); // Ball has lower RCS

                // Timestamp is base + club_duration + gap + elapsed ball time
                let timestamp = base_timestamp + (club_duration_ms + gap_ms + elapsed_ms) as f64 / 1000.0;

                ball_reading_list.push(SpeedReading {
                    speed: speed.max(15.0),
                    direction: Direction::Outbound,
                    magnitude: Some(magnitude),
                    timestamp,
                });
            }
        }

        // Send all readings immediately with correct timestamps
        // The timestamps represent simulated time, but we send them all at once
        // to keep wall-clock duration minimal
        for reading in club_reading_list {
            if tx.send(reading).is_err() {
                return; // Receiver dropped
            }
        }

        for reading in ball_reading_list {
            if tx.send(reading).is_err() {
                return; // Receiver dropped
            }
        }

        // Gap after shot (no readings for >0.5s triggers shot processing)
        thread::sleep(Duration::from_millis(600));
    }

    pub fn trigger_shot(&self) {
        let _ = self.shot_tx.send(());
    }
}

impl Drop for MockRadar {
    fn drop(&mut self) {
        // Close channel to stop background thread
        drop(&self.shot_tx);
    }
}

impl crate::launch_monitor::RadarInterface for MockRadar {
    fn connect(&mut self) -> Result<()> {
        Ok(())
    }

    fn disconnect(&mut self) {
        // No-op for mock
    }

    fn get_info(&mut self) -> Result<HashMap<String, String>> {
        let mut info = HashMap::new();
        info.insert("Product".to_string(), "OPS243-MOCK".to_string());
        info.insert("Version".to_string(), "1.0.0-MOCK".to_string());
        info.insert("Mode".to_string(), "Simulation".to_string());
        Ok(info)
    }

    fn configure_for_golf(&mut self) -> Result<()> {
        Ok(())
    }

    fn read_speed(&mut self) -> Result<Option<SpeedReading>> {
        // Non-blocking read from channel
        match self.reading_rx.try_recv() {
            Ok(reading) => Ok(Some(reading)),
            Err(mpsc::TryRecvError::Empty) => Ok(None),
            Err(mpsc::TryRecvError::Disconnected) => {
                Err(anyhow::anyhow!("Mock radar channel disconnected"))
            }
        }
    }
}
