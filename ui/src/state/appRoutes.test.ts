import { describe, expect, it } from 'vitest';
import { isRemotePath, isScoreboardPath } from './appRoutes';
import { isLowPowerSearch, isTVUserAgent } from './displayDetect';

describe('isScoreboardPath', () => {
  it('matches /scoreboard with or without a trailing slash', () => {
    expect(isScoreboardPath('/scoreboard')).toBe(true);
    expect(isScoreboardPath('/scoreboard/')).toBe(true);
  });

  it('does not match other paths', () => {
    expect(isScoreboardPath('/')).toBe(false);
    expect(isScoreboardPath('/scoreboards')).toBe(false);
    expect(isScoreboardPath('/remote')).toBe(false);
  });
});

describe('isRemotePath', () => {
  it('matches /remote with or without a trailing slash', () => {
    expect(isRemotePath('/remote')).toBe(true);
    expect(isRemotePath('/remote/')).toBe(true);
  });

  it('does not match other paths', () => {
    expect(isRemotePath('/')).toBe(false);
    expect(isRemotePath('/scoreboard')).toBe(false);
  });
});

describe('isTVUserAgent', () => {
  it('detects Tizen and webOS 10-foot browsers', () => {
    expect(isTVUserAgent('Mozilla/5.0 (SMART-TV; Tizen 6.0)')).toBe(true);
    expect(isTVUserAgent('Mozilla/5.0 (Web0S)')).toBe(true);
  });

  it('is false for desktop/mobile browsers', () => {
    expect(isTVUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X)')).toBe(false);
  });
});

describe('isLowPowerSearch', () => {
  it('detects ?lowpower=1', () => {
    expect(isLowPowerSearch('?lowpower=1')).toBe(true);
    expect(isLowPowerSearch('?lowpower=0')).toBe(false);
    expect(isLowPowerSearch('')).toBe(false);
  });
});
