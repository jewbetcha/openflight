import { hintMode, type ViewMode } from './viewMode';

/**
 * Pure view-mode detectors. The reactive mode state + the `tv`/`low-power`
 * <html> class application live in ViewModeProvider; this module only provides
 * the detection helpers it (and the first-run chooser) build on.
 */

/** Pure: is this user-agent a known 10-foot TV browser (Tizen / webOS)? */
export function isTVUserAgent(ua: string): boolean {
  return /Tizen/i.test(ua) || /Web0S|webOS/i.test(ua);
}

/** Pure: does the query string request low-power mode (?lowpower=1)? */
export function isLowPowerSearch(search: string): boolean {
  return new URLSearchParams(search).get('lowpower') === '1';
}

/**
 * The small built-in kiosk touchscreen (e.g. the 7" HMTECH 1024×600). It's the
 * operator's control surface, so it defaults to Interactive and skips the
 * first-run chooser - only larger external screens are asked.
 */
export function isSmallKioskScreen(): boolean {
  if (typeof window === 'undefined' || typeof window.screen === 'undefined') return false;
  const w = window.screen.width;
  const h = window.screen.height;
  return Math.max(w, h) <= 1024 && Math.min(w, h) <= 600;
}

/**
 * Best guess for the first-run chooser's default - the small kiosk panel is
 * always Interactive; otherwise the EDID/CEC hint (from start-kiosk.sh), then a
 * TV user-agent, else Scoreboard. Ignores any saved choice.
 */
export function suggestedViewMode(): ViewMode {
  if (isSmallKioskScreen()) return 'interactive';
  const hint = hintMode();
  if (hint) return hint;
  if (typeof navigator !== 'undefined' && isTVUserAgent(navigator.userAgent)) return 'interactive';
  if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('tv')) return 'interactive';
  return 'scoreboard';
}
