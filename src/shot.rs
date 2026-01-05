use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub enum Direction {
    Inbound,
    Outbound,
    Unknown,
}

#[derive(Debug, Clone, Serialize)]
pub struct SpeedReading {
    pub speed: f64,           // Speed in mph
    pub direction: Direction,
    pub magnitude: Option<f64>,
    pub timestamp: f64,       // Unix timestamp
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum ClubType {
    Driver,
    Wood3,
    Wood5,
    Hybrid,
    Iron3,
    Iron4,
    Iron5,
    Iron6,
    Iron7,
    Iron8,
    Iron9,
    Pw,
    Unknown,
}

#[derive(Debug, Clone, Serialize)]
pub struct Shot {
    pub ball_speed_mph: f64,
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub club_speed_mph: Option<f64>,
    pub peak_magnitude: Option<f64>,
    pub readings: Vec<SpeedReading>,
    pub club: ClubType,
}

impl Shot {
    pub fn ball_speed_ms(&self) -> f64 {
        self.ball_speed_mph * 0.44704
    }

    pub fn club_speed_ms(&self) -> Option<f64> {
        self.club_speed_mph.map(|s| s * 0.44704)
    }

    pub fn smash_factor(&self) -> Option<f64> {
        match self.club_speed_mph {
            Some(club) if club > 0.0 => Some(self.ball_speed_mph / club),
            _ => None,
        }
    }

    pub fn estimated_carry_yards(&self) -> f64 {
        estimate_carry_distance(self.ball_speed_mph, self.club)
    }

    pub fn estimated_carry_range(&self) -> (f64, f64) {
        let base = self.estimated_carry_yards();
        // ±10% uncertainty without launch angle/spin data
        (base * 0.90, base * 1.10)
    }
}

/// Estimate carry distance from ball speed using TrackMan-derived data.
///
/// This uses interpolation from real-world data assuming optimal launch
/// conditions (10-14° launch angle, appropriate spin for ball speed).
fn estimate_carry_distance(ball_speed_mph: f64, club: ClubType) -> f64 {
    // Driver ball speed to carry distance lookup table
    // Based on TrackMan data assuming optimal launch conditions
    // Format: (ball_speed_mph, carry_yards_low, carry_yards_high)
    const DRIVER_TABLE: &[(f64, f64, f64)] = &[
        (100.0, 130.0, 142.0),
        (110.0, 157.0, 170.0),
        (120.0, 183.0, 197.0),
        (130.0, 207.0, 223.0),
        (140.0, 231.0, 249.0),
        (150.0, 254.0, 275.0),
        (160.0, 276.0, 301.0),
        (167.0, 275.0, 285.0),  // PGA Tour average
        (170.0, 298.0, 325.0),
        (180.0, 320.0, 349.0),
        (190.0, 342.0, 372.0),
        (200.0, 360.0, 389.0),
        (210.0, 383.0, 408.0),
    ];

    // Adjustment factors for different clubs (relative to driver)
    let club_factor = match club {
        ClubType::Driver => 1.0,
        ClubType::Wood3 => 0.96,
        ClubType::Wood5 => 0.93,
        ClubType::Hybrid => 0.90,
        ClubType::Iron3 => 0.87,
        ClubType::Iron4 => 0.85,
        ClubType::Iron5 => 0.82,
        ClubType::Iron6 => 0.79,
        ClubType::Iron7 => 0.76,
        ClubType::Iron8 => 0.73,
        ClubType::Iron9 => 0.70,
        ClubType::Pw => 0.67,
        ClubType::Unknown => 1.0,
    };

    // Interpolate from driver table
    let carry = if ball_speed_mph <= DRIVER_TABLE[0].0 {
        // Below minimum - extrapolate linearly
        let ratio = ball_speed_mph / DRIVER_TABLE[0].0;
        let base_carry = (DRIVER_TABLE[0].1 + DRIVER_TABLE[0].2) / 2.0;
        base_carry * ratio
    } else if ball_speed_mph >= DRIVER_TABLE.last().unwrap().0 {
        // Above maximum - extrapolate conservatively
        let base_carry = (DRIVER_TABLE.last().unwrap().1 + DRIVER_TABLE.last().unwrap().2) / 2.0;
        base_carry + (ball_speed_mph - DRIVER_TABLE.last().unwrap().0) * 1.8
    } else {
        // Interpolate between table entries
        let mut carry = 0.0;
        for i in 0..DRIVER_TABLE.len() - 1 {
            if DRIVER_TABLE[i].0 <= ball_speed_mph && ball_speed_mph < DRIVER_TABLE[i + 1].0 {
                let (speed_low, carry_low_min, carry_low_max) = DRIVER_TABLE[i];
                let (speed_high, carry_high_min, carry_high_max) = DRIVER_TABLE[i + 1];

                // Use midpoint of ranges
                let carry_low = (carry_low_min + carry_low_max) / 2.0;
                let carry_high = (carry_high_min + carry_high_max) / 2.0;

                // Interpolate
                let t = (ball_speed_mph - speed_low) / (speed_high - speed_low);
                carry = carry_low + t * (carry_high - carry_low);
                break;
            }
        }
        if carry == 0.0 {
            // Fallback
            ball_speed_mph * 1.65
        } else {
            carry
        }
    };

    carry * club_factor
}

