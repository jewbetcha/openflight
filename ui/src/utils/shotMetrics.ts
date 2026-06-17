// Single source of truth for per-metric shot QUALITY and the label set each
// metric uses. Both the kiosk live view (ShotDisplay) and the passive /display
// scoreboard (DisplayMode) derive quality from here so they cannot drift.
//
// Quality semantics (decided in review): magnitude metrics read Low/Perfect/High
// and directional metrics read Left/Perfect/Right. Horizontal launch is a
// MAGNITUDE metric (matches the kiosk - "how far offline", not which side).

import type { TKey } from '../i18n/translations';
import type { Shot } from '../types/shot';
import { getRanges, hLaunchQuality, inRange, type Quality } from './shotQuality';

export type QualityLabels = { low: string; medium: string; high: string };

const CLUB_PATH_RANGE = { min: -3, max: 3 };

export interface ShotQualities {
  vLaunch: Quality | null;
  hLaunch: Quality | null;
  aoa: Quality | null;
  clubPath: Quality | null;
  spin: Quality | null;
}

/** Compute every quality indicator for a shot from one place. */
export function getShotQualities(shot: Shot): ShotQualities {
  const r = getRanges(shot.club);
  return {
    vLaunch: shot.launch_angle_vertical != null ? inRange(shot.launch_angle_vertical, r.vLaunch) : null,
    hLaunch: hLaunchQuality(shot.launch_angle_horizontal, r.hLaunch),
    aoa: shot.club_angle_deg != null ? inRange(shot.club_angle_deg, r.aoa) : null,
    clubPath: shot.club_path_deg != null ? inRange(shot.club_path_deg, CLUB_PATH_RANGE) : null,
    spin: shot.spin_rpm != null ? inRange(shot.spin_rpm, r.spin) : null,
  };
}

export function magnitudeLabels(t: (key: TKey) => string): QualityLabels {
  return { low: t('qualityLow'), medium: t('qualityPerfect'), high: t('qualityHigh') };
}

export function directionalLabels(t: (key: TKey) => string): QualityLabels {
  return { low: t('qualityLeft'), medium: t('qualityPerfect'), high: t('qualityRight') };
}
