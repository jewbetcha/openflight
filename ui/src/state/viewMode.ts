// View mode: which UI this screen renders.
//   'interactive' → the full kiosk (hit shots, navigate, settings); used on the
//                   7" touchscreen and scaled up on a TV.
//   'scoreboard'  → the passive stats display (formerly /display); glanceable,
//                   still operable by remote/voiceover/touch.
//
// Chosen once at first run (a chooser is shown on larger screens; the 7" kiosk
// panel defaults to Interactive without asking), seeded by the Pi's EDID/CEC
// auto-detection (passed as ?viewmode=…), persisted, and switchable in Settings.
// ViewModeProvider holds it as reactive state and applies the mode live.

export type ViewMode = 'interactive' | 'scoreboard';

const KEY = 'openflight.viewMode';

/** The saved view mode, or null if the user hasn't chosen yet. */
export function readSavedMode(): ViewMode | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const v = localStorage.getItem(KEY);
    return v === 'interactive' || v === 'scoreboard' ? v : null;
  } catch {
    return null;
  }
}

export function isModeChosen(): boolean {
  return readSavedMode() !== null;
}

/**
 * Auto-detection hint from `start-kiosk.sh` (EDID/CEC): `?viewmode=interactive`
 * or `?viewmode=scoreboard`. Used only to seed the first-run chooser's default -
 * a saved choice always wins. `search` is injectable for testing.
 */
export function hintMode(
  search: string = typeof window !== 'undefined' ? window.location.search : '',
): ViewMode | null {
  const h = new URLSearchParams(search).get('viewmode');
  return h === 'interactive' || h === 'scoreboard' ? h : null;
}

/** Persist the chosen mode. No reload - ViewModeProvider applies it live. */
export function saveMode(mode: ViewMode): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, mode);
  } catch {
    /* ignore storage failures - the live state still updates this session */
  }
}
