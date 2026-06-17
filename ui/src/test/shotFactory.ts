import type { Shot } from '../types/shot';

/** Build a Shot with sensible defaults; override only the fields a test cares about. */
export function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    ball_speed_mph: 150,
    club_speed_mph: 100,
    smash_factor: 1.5,
    estimated_carry_yards: 250,
    carry_range: [240, 260],
    club: 'driver',
    timestamp: '2026-01-01T00:00:00Z',
    peak_magnitude: 40,
    launch_angle_vertical: 13,
    launch_angle_horizontal: 0,
    launch_angle_confidence: 0.8,
    angle_source: 'radar',
    club_angle_deg: 0,
    club_path_deg: 0,
    spin_axis_deg: 0,
    spin_rpm: 2500,
    spin_confidence: 0.8,
    spin_quality: 'high',
    carry_spin_adjusted: 255,
    ...overrides,
  };
}
