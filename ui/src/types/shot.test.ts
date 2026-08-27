import { describe, expect, it } from 'vitest';
import type { Shot } from './shot';
import { filterShotsByPlayer, excludeShotsByPlayer } from './shot';

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    ball_speed_mph: 90,
    club_speed_mph: 67,
    smash_factor: 1.34,
    estimated_carry_yards: 200,
    carry_range: [195, 205],
    club: 'driver',
    timestamp: 'a',
    peak_magnitude: 100,
    launch_angle_vertical: 13,
    launch_angle_horizontal: 0,
    launch_angle_confidence: 0.8,
    angle_source: 'radar',
    club_angle_deg: null,
    club_path_deg: null,
    spin_axis_deg: null,
    spin_rpm: 2600,
    spin_confidence: 0.9,
    spin_quality: 'high',
    spin_source: 'measured',
    spin_method: null,
    carry_spin_adjusted: null,
    ...overrides,
  };
}

describe('filterShotsByPlayer', () => {
  it('keeps shots whose player matches, ignoring case and padding', () => {
    const shots = [
      makeShot({ player_name: 'James', timestamp: 'a' }),
      makeShot({ player_name: 'james ', timestamp: 'b' }),
      makeShot({ player_name: 'Alex', timestamp: 'c' }),
    ];

    expect(filterShotsByPlayer(shots, ' JAMES').map((shot) => shot.timestamp)).toEqual(['a', 'b']);
  });

  it('treats a missing player name as Player 1', () => {
    const shots = [makeShot({ timestamp: 'a' }), makeShot({ player_name: 'James', timestamp: 'b' })];

    expect(filterShotsByPlayer(shots, 'Player 1').map((shot) => shot.timestamp)).toEqual(['a']);
  });
});

describe('excludeShotsByPlayer', () => {
  it('drops matching shots and keeps everyone else', () => {
    const shots = [
      makeShot({ player_name: 'James', timestamp: 'a' }),
      makeShot({ player_name: 'Alex', timestamp: 'b' }),
      makeShot({ player_name: 'james', timestamp: 'c' }),
    ];

    expect(excludeShotsByPlayer(shots, 'James').map((shot) => shot.timestamp)).toEqual(['b']);
  });
});
