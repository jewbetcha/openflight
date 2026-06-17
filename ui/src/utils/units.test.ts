import { describe, expect, it } from 'vitest';
import {
  convertDistanceFromYards,
  convertSpeedFromMph,
  formatCarryRange,
  formatDistance,
  formatSpeed,
  getDistanceUnit,
  getSpeedUnit,
} from './units';

describe('units helpers', () => {
  it('preserves mph speed values', () => {
    expect(convertSpeedFromMph(150, 'mph')).toBe(150);
    expect(formatSpeed(150, 'mph', 1)).toBe('150.0');
    expect(getSpeedUnit('mph')).toBe('mph');
  });

  it('converts mph to km/h with stable rounding', () => {
    expect(convertSpeedFromMph(100, 'kmh')).toBeCloseTo(160.934, 3);
    expect(formatSpeed(100, 'kmh', 1)).toBe('160.9');
    expect(getSpeedUnit('kmh')).toBe('km/h');
  });

  it('preserves yards distance values', () => {
    expect(convertDistanceFromYards(250, 'yards')).toBe(250);
    expect(formatDistance(250, 'yards', 0)).toBe('250');
    expect(getDistanceUnit('yards')).toBe('yds');
  });

  it('converts yards to meters with stable rounding', () => {
    expect(convertDistanceFromYards(100, 'meters')).toBeCloseTo(91.44, 2);
    expect(formatDistance(100, 'meters', 0)).toBe('91');
    expect(getDistanceUnit('meters')).toBe('m');
  });

  it('formats carry ranges in the selected unit system', () => {
    expect(formatCarryRange([200, 220], 'yards')).toBe('200–220 yds');
    expect(formatCarryRange([200, 220], 'meters')).toBe('183–201 m');
  });
});
