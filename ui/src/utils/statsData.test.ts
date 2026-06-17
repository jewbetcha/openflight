import { describe, expect, it } from 'vitest';
import {
  medianOf,
  stdDev,
  computeBoxStats,
  computeTrendsSummary,
  getGroupShots,
  getClubColors,
  CLUB_PALETTE,
} from './statsData';
import { makeShot } from '../test/shotFactory';

describe('statsData math helpers', () => {
  it('medianOf handles odd, even, and empty arrays', () => {
    expect(medianOf([3, 1, 2])).toBe(2);
    expect(medianOf([1, 2, 3, 4])).toBe(2.5);
    expect(medianOf([])).toBe(0);
  });

  it('stdDev is population standard deviation, 0 for <2 values', () => {
    // mean 5, variance 32/8 = 4, sqrt = 2 (divides by n, not n-1)
    expect(stdDev([2, 4, 4, 4, 5, 5, 7, 9])).toBe(2);
    expect(stdDev([5])).toBe(0);
    expect(stdDev([])).toBe(0);
  });

  it('computeBoxStats returns quartiles, null for <3 values', () => {
    const box = computeBoxStats([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(box).toEqual({ min: 1, q1: 3, median: 5, q3: 7, max: 9 });
    expect(computeBoxStats([1, 2])).toBeNull();
    expect(computeBoxStats([])).toBeNull();
  });
});

describe('getGroupShots', () => {
  const shots = [
    makeShot({ club: 'driver' }),
    makeShot({ club: '7-iron' }),
    makeShot({ club: 'pw' }),
  ];

  it('returns all shots for the "all" group', () => {
    expect(getGroupShots(shots, 'all')).toHaveLength(3);
  });

  it('filters to clubs in the requested group', () => {
    expect(getGroupShots(shots, 'iron').map((s) => s.club)).toEqual(['7-iron']);
    expect(getGroupShots(shots, 'wedge').map((s) => s.club)).toEqual(['pw']);
    expect(getGroupShots(shots, 'driver').map((s) => s.club)).toEqual(['driver']);
  });
});

describe('getClubColors', () => {
  it('assigns a palette colour to each club and cycles when exhausted', () => {
    const clubs = ['driver', '7-iron', 'pw'];
    const colors = getClubColors(clubs);
    expect(Object.keys(colors)).toEqual(clubs);
    expect(colors.driver).toBe(CLUB_PALETTE[0]);
    expect(colors['7-iron']).toBe(CLUB_PALETTE[1]);
  });

  it('uses a different palette in colour-blind mode', () => {
    const normal = getClubColors(['driver'], false);
    const cb = getClubColors(['driver'], true);
    expect(cb.driver).not.toBe(normal.driver);
  });
});

describe('computeTrendsSummary', () => {
  it('returns null for fewer than 3 shots', () => {
    expect(computeTrendsSummary([makeShot(), makeShot()], 'yards')).toBeNull();
  });

  it('computes averages across metrics for enough shots', () => {
    const shots = [
      makeShot({ ball_speed_mph: 140 }),
      makeShot({ ball_speed_mph: 150 }),
      makeShot({ ball_speed_mph: 160 }),
    ];
    const summary = computeTrendsSummary(shots, 'yards');
    expect(summary).not.toBeNull();
    expect(summary!.ball.avg).toBeCloseTo(150);
  });

  it('reports no trend until there are at least 6 samples', () => {
    const three = [makeShot(), makeShot(), makeShot()];
    expect(computeTrendsSummary(three, 'yards')!.ball.trend).toBeNull();
  });
});
