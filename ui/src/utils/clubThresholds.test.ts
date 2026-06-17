import { describe, expect, it } from 'vitest';
import { getClubCategory, getClubTarget } from './clubThresholds';

describe('getClubCategory', () => {
  it('maps clubs to their fault-window category', () => {
    expect(getClubCategory('driver')).toBe('driver');
    expect(getClubCategory('3-wood')).toBe('fairway-wood');
    expect(getClubCategory('5-hybrid')).toBe('hybrid');
    expect(getClubCategory('3-iron')).toBe('long-iron');
    expect(getClubCategory('7-iron')).toBe('mid-iron');
    expect(getClubCategory('9-iron')).toBe('short-iron');
    expect(getClubCategory('pw')).toBe('wedge');
  });

  it('normalises spaces/underscores and casing', () => {
    expect(getClubCategory('7 IRON')).toBe('mid-iron');
    expect(getClubCategory('3_wood')).toBe('fairway-wood');
  });
});

describe('getClubTarget', () => {
  it('returns a target for a known club and null otherwise', () => {
    expect(getClubTarget('driver')).not.toBeNull();
    expect(getClubTarget('totally-made-up')).toBeNull();
  });
});
