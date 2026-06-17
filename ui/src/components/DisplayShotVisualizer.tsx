import { useMemo } from 'react';
import { useLanguage } from '../state/useLanguage';
import { useThemeColors } from '../state/useThemeColors';
import type { Shot } from '../types/shot';
import type { DistanceUnit } from '../utils/units';
import { getClubColors } from '../utils/statsData';
import { DispersionChart, TrajectoryChart } from './charts/clubCharts';
import './DisplayShotVisualizer.css';

interface Props {
  shots: Shot[];
  latestShot: Shot | null;
  distUnit: DistanceUnit;
  /** When true, the shot-in animation is suppressed (a11y Reduce Motion). */
  reduceMotion: boolean;
}

/**
 * The /display camera area's stand-in when no camera is streaming: a stacked
 * side-view trajectory (top) over a top-down dispersion chart (bottom), scoped
 * to the CURRENT club (the latest shot's club). On each new shot the newest
 * arc sweeps left→right while its dispersion dot slams in at the sweep's end
 * (animation lives in clubCharts.css; CSS-only so it stays smooth on the Pi).
 */
export function DisplayShotVisualizer({ shots, latestShot, distUnit, reduceMotion }: Props) {
  const { t } = useLanguage();
  const theme = useThemeColors();
  const club = latestShot?.club ?? null;

  const clubShots = useMemo(
    () => (club ? shots.filter((s) => s.club === club) : []),
    [shots, club],
  );
  const clubColors = useMemo(
    () => getClubColors(club ? [club] : [], theme.isColorBlind),
    [club, theme.isColorBlind],
  );

  // Replay token - combine timestamp with the running shot count so the
  // animation re-fires for every new shot even if two share a timestamp.
  const animateKey = !reduceMotion && latestShot ? `${latestShot.timestamp}-${shots.length}` : null;

  if (!latestShot || clubShots.length === 0) {
    return (
      <div className="display-viz display-viz--empty">
        <span>{t('displayReady')}</span>
      </div>
    );
  }

  return (
    <div className="display-viz">
      <div className="display-viz__panel">
        <TrajectoryChart shots={clubShots} clubColors={clubColors} distUnit={distUnit} animateKey={animateKey} />
      </div>
      <div className="display-viz__panel">
        <DispersionChart shots={clubShots} clubColors={clubColors} distUnit={distUnit} animateKey={animateKey} />
      </div>
    </div>
  );
}
