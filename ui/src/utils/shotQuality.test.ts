import { describe, expect, it } from 'vitest';
import { getRanges, inRange, hLaunchQuality, DEFAULT_RANGES } from './shotQuality';

describe('inRange', () => {
  const range = { min: 10, max: 20 };

  it('classifies below/within/above the range', () => {
    expect(inRange(5, range)).toBe('low');
    expect(inRange(15, range)).toBe('medium');
    expect(inRange(25, range)).toBe('high');
  });

  it('treats the boundaries as in-range (medium)', () => {
    expect(inRange(10, range)).toBe('medium');
    expect(inRange(20, range)).toBe('medium');
  });
});

describe('getRanges', () => {
  it('falls back to DEFAULT_RANGES for an unknown club', () => {
    expect(getRanges('not-a-club')).toBe(DEFAULT_RANGES);
  });
});

describe('hLaunchQuality', () => {
  const range = { min: 0, max: 3 };

  it('returns null when the angle is unknown', () => {
    expect(hLaunchQuality(null, range)).toBeNull();
  });

  it('uses the absolute value so left and right are treated equally', () => {
    expect(hLaunchQuality(-5, range)).toBe('high');
    expect(hLaunchQuality(2, range)).toBe('medium');
  });
});
