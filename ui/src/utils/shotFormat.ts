// Shared, pure shot-display formatters. Single source of truth for the kiosk
// live view (ShotDisplay) and the passive /display scoreboard (DisplayMode) so
// the two surfaces can never drift on how a value is rendered.

export const PLACEHOLDER = '--';

/** Signed fixed-decimal formatting: +2.3 / -1.1 / -- (for non-finite/null). */
export function fmtSigned(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return PLACEHOLDER;
  return (value >= 0 ? '+' : '') + value.toFixed(digits);
}

/** Spin rate with thousands separators: 2,450 / -- */
export function fmtSpin(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return PLACEHOLDER;
  return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

/**
 * Shot-shape translation key derived from the spin axis (degrees).
 * Negative = draw/hook side, positive = fade/slice side. Returns a key the
 * caller passes to t(), keeping this module i18n-agnostic and easy to test.
 */
export type ShotShapeKey =
  | 'strongDraw'
  | 'draw'
  | 'straight'
  | 'slightFade'
  | 'strongFade';

export function shapeKeyFromSpinAxis(deg: number | null | undefined): ShotShapeKey | null {
  if (deg == null || !Number.isFinite(deg)) return null;
  if (deg < -4) return 'strongDraw'; // Pull Hook  (< -4°)
  if (deg < -1) return 'draw'; // Pull Draw  (-4° to -1°)
  if (deg <= 1) return 'straight'; // Straight   (-1° to +1°)
  if (deg <= 4) return 'slightFade'; // Fade       (+1° to +4°)
  return 'strongFade'; // Slice      (> +4°)
}
