import { afterEach, describe, expect, it } from 'vitest';
import { hintMode, isModeChosen, readSavedMode, saveMode } from './viewMode';

afterEach(() => {
  localStorage.clear();
});

describe('readSavedMode / saveMode / isModeChosen', () => {
  it('returns null and not-chosen when nothing is saved', () => {
    expect(readSavedMode()).toBeNull();
    expect(isModeChosen()).toBe(false);
  });

  it('round-trips a saved mode', () => {
    saveMode('interactive');
    expect(readSavedMode()).toBe('interactive');
    expect(isModeChosen()).toBe(true);

    saveMode('scoreboard');
    expect(readSavedMode()).toBe('scoreboard');
  });

  it('ignores a corrupt/legacy stored value', () => {
    localStorage.setItem('openflight.viewMode', 'tv');
    expect(readSavedMode()).toBeNull();
    expect(isModeChosen()).toBe(false);
  });
});

describe('hintMode', () => {
  it('reads ?viewmode=interactive|scoreboard', () => {
    expect(hintMode('?viewmode=interactive')).toBe('interactive');
    expect(hintMode('?viewmode=scoreboard')).toBe('scoreboard');
  });

  it('returns null for missing or unknown hints', () => {
    expect(hintMode('')).toBeNull();
    expect(hintMode('?viewmode=tv')).toBeNull();
    expect(hintMode('?foo=bar')).toBeNull();
  });
});
