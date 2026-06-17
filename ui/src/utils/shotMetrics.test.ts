import { describe, expect, it } from 'vitest';
import type { Shot } from '../types/shot';
import { getShotQualities } from './shotMetrics';

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    ball_speed_mph: 150,
    club_speed_mph: 100,
    smash_factor: 1.5,
    estimated_carry_yards: 250,
    carry_range: [240, 260],
    club: 'driver',
    timestamp: '2026-06-16T00:00:00Z',
    peak_magnitude: 40,
    launch_angle_vertical: null,
    launch_angle_horizontal: null,
    launch_angle_confidence: null,
    angle_source: null,
    club_angle_deg: null,
    club_path_deg: null,
    spin_axis_deg: null,
    spin_rpm: null,
    spin_confidence: null,
    spin_quality: null,
    carry_spin_adjusted: null,
    ...overrides,
  };
}

describe('getShotQualities', () => {
  it('returns null for every metric that is absent', () => {
    expect(getShotQualities(makeShot())).toEqual({
      vLaunch: null,
      hLaunch: null,
      aoa: null,
      clubPath: null,
      spin: null,
    });
  });

  it('treats horizontal launch as a magnitude metric (never directional)', () => {
    // driver hLaunch range is {0, 1}; |deg| > 1 => 'high', never 'low'
    expect(getShotQualities(makeShot({ launch_angle_horizontal: -5 })).hLaunch).toBe('high');
    expect(getShotQualities(makeShot({ launch_angle_horizontal: 5 })).hLaunch).toBe('high');
    expect(getShotQualities(makeShot({ launch_angle_horizontal: 0.5 })).hLaunch).toBe('medium');
  });

  it('classifies club path directionally around ±3°', () => {
    expect(getShotQualities(makeShot({ club_path_deg: -5 })).clubPath).toBe('low');
    expect(getShotQualities(makeShot({ club_path_deg: 0 })).clubPath).toBe('medium');
    expect(getShotQualities(makeShot({ club_path_deg: 5 })).clubPath).toBe('high');
  });

  it('classifies vertical launch and spin against the club range', () => {
    const q = getShotQualities(makeShot({ launch_angle_vertical: 13.5, spin_rpm: 2300 }));
    expect(q.vLaunch).toBe('medium'); // driver vLaunch {12,15}
    expect(q.spin).toBe('medium'); // driver spin {2000,2600}
    expect(getShotQualities(makeShot({ spin_rpm: 5000 })).spin).toBe('high');
  });
});
