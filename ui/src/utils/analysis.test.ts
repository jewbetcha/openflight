import { describe, expect, it } from 'vitest';
import { mean, stdDev, getBenchmark, computeStrikeQuality } from './analysis';
import { makeShot } from '../test/shotFactory';

describe('analysis math helpers', () => {
  it('mean averages the array', () => {
    expect(mean([10, 20, 30])).toBe(20);
  });

  it('stdDev is the sample standard deviation (divides by n-1), 0 for <2 values', () => {
    // mean 5, sum-sq 32, n-1 = 7 → sqrt(32/7) ≈ 2.138
    expect(stdDev([2, 4, 4, 4, 5, 5, 7, 9])).toBeCloseTo(2.138, 2);
    expect(stdDev([5])).toBe(0);
  });
});

describe('getBenchmark', () => {
  it('resolves a known club and normalises formatting', () => {
    expect(getBenchmark('driver')).not.toBeNull();
    expect(getBenchmark('7 IRON')).toEqual(getBenchmark('7-iron'));
  });

  it('returns null for an unknown club', () => {
    expect(getBenchmark('spoon')).toBeNull();
  });
});

describe('computeStrikeQuality', () => {
  it('returns null when there are no usable shots', () => {
    expect(computeStrikeQuality([])).toBeNull();
  });

  it('produces a result for a set of shots', () => {
    const shots = Array.from({ length: 6 }, (_, i) =>
      makeShot({ smash_factor: 1.4 + i * 0.02 }),
    );
    const result = computeStrikeQuality(shots);
    expect(result).not.toBeNull();
  });
});
