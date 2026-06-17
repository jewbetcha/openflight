import { useMemo } from 'react';
import type { Shot } from '../types/shot';
import { useUnitPreference } from '../state/useUnitPreference';
import { useLanguage } from '../state/useLanguage';
import { formatCarryRange, formatDistance, formatSpeed, getDistanceUnit, getSpeedUnit } from '../utils/units';
import { fmtSigned, fmtSpin, shapeKeyFromSpinAxis } from '../utils/shotFormat';
import { directionalLabels, getShotQualities, magnitudeLabels } from '../utils/shotMetrics';
import { ConfidenceDots } from './ConfidenceDots';
import { SpeedGauge } from './SpeedGauge';
import { getGaugeMax, getClubHeadGaugeMax } from '../utils/gaugeRanges';
import './ShotDisplay.css';

interface ShotDisplayProps {
  shot: Shot | null;
  animate?: boolean;
}

function MetricCard({
  value,
  unit,
  label,
  subtext,
  variant = 'default',
  confidence,
  qualityLabels,
}: {
  value: string | number;
  unit?: string;
  label: string;
  subtext?: string;
  variant?: 'default' | 'primary' | 'secondary' | 'spin';
  confidence?: 'high' | 'medium' | 'low' | null;
  qualityLabels?: { low: string; medium: string; high: string };
}) {
  const { t: tq } = useLanguage();
  const labels = qualityLabels ?? magnitudeLabels(tq);
  return (
    <div className={`metric-card metric-card--${variant}`}>
      <div className="metric-card__value-row">
        <span className="metric-card__value">{value}</span>
        {unit && (
          <span className={`metric-card__unit${unit === '°' ? ' metric-card__unit--degree' : ''}`}>
            {unit}
          </span>
        )}
      </div>
      <span className="metric-card__label">{label}</span>
      {subtext && <span className="metric-card__subtext">{subtext}</span>}
      {confidence && <ConfidenceDots quality={confidence} labels={labels} scope="card" />}
    </div>
  );
}

export function ShotDisplay({ shot, animate = false }: ShotDisplayProps) {
  const { speedUnit, distanceUnit } = useUnitPreference();
  const { t } = useLanguage();
  const carryRange = useMemo(() => {
    if (!shot) return null;
    return formatCarryRange(shot.carry_range, distanceUnit);
  }, [shot, distanceUnit]);

  const displayCarry = shot?.carry_spin_adjusted ?? shot?.estimated_carry_yards ?? 0;
  const carrySubtext = shot?.carry_spin_adjusted ? t('spinAdj') : carryRange || undefined;

  if (!shot) {
    return (
      <div className="shot-display shot-display--empty">
        <div className="shot-display__waiting">
          <div className="logo-waiting">
            <img src="/golf-ball.png" alt="" className="golf-ball-img" />
          </div>
          <p className="shot-display__waiting-text">{t('readyTitle')}</p>
          <p className="shot-display__waiting-hint">{t('readyHint')}</p>
        </div>
      </div>
    );
  }

  const hasSpin = shot.spin_rpm !== null;
  const hasLaunchAngle = shot.launch_angle_vertical !== null;
  const quality = getShotQualities(shot);
  const shapeKey = shapeKeyFromSpinAxis(shot.spin_axis_deg);
  const spinDir = shapeKey ? t(shapeKey) : null;

  return (
    <div
      className={`shot-display ${animate ? 'shot-display--animate' : ''}`}
      aria-live="polite"
      aria-atomic="true"
      aria-label={`Shot: ${shot.club}, carry ${formatDistance(displayCarry, distanceUnit, 0)} ${getDistanceUnit(distanceUnit)}, ball speed ${formatSpeed(shot.ball_speed_mph, speedUnit, 1)} ${getSpeedUnit(speedUnit)}`}
    >
      <div className="shot-display__layout">

        {/* Quad: 2×2 - carry + total (top), speed gauges (bottom) */}
        <div className="shot-display__quad">

          {/* Top-left: Est. Carry */}
          <div className="quad-stat">
            <div className="quad-stat__value-row">
              <span className="quad-stat__value">{formatDistance(displayCarry, distanceUnit, 0)}</span>
              <span className="quad-stat__unit">{getDistanceUnit(distanceUnit)}</span>
            </div>
            <span className="quad-stat__label">{t('estCarry')}</span>
            {carrySubtext && <span className="quad-stat__subtext">{carrySubtext}</span>}
          </div>

          {/* Top-right: Total w/ roll */}
          <div className="quad-stat">
            <div className="quad-stat__value-row">
              <span className="quad-stat__value">
                {shot.total_distance_yards != null ? formatDistance(shot.total_distance_yards, distanceUnit, 0) : '-'}
              </span>
              {shot.total_distance_yards != null && (
                <span className="quad-stat__unit">{getDistanceUnit(distanceUnit)}</span>
              )}
            </div>
            <span className="quad-stat__label">{t('totalDist')}</span>
            <span className="quad-stat__subtext">{t('withRoll')}</span>
          </div>

          {/* Bottom-left: Ball speed gauge */}
          <div className="quad-gauge">
            <SpeedGauge
              speedMph={shot.ball_speed_mph}
              gaugeMax={getGaugeMax(shot.club)}
              label={t('ballSpeed')}
              displayValue={formatSpeed(shot.ball_speed_mph, speedUnit, 1)}
              unit={getSpeedUnit(speedUnit)}
            />
          </div>

          {/* Bottom-right: Club speed gauge (or dash if unavailable) */}
          <div className="quad-gauge">
            {shot.club_speed_mph != null ? (
              <SpeedGauge
                speedMph={shot.club_speed_mph}
                gaugeMax={getClubHeadGaugeMax(shot.club)}
                label={t('clubSpeed')}
                displayValue={formatSpeed(shot.club_speed_mph, speedUnit, 1)}
                unit={getSpeedUnit(speedUnit)}
              />
            ) : (
              <div className="quad-stat quad-stat--empty">
                <div className="quad-stat__value-row">
                  <span className="quad-stat__value">-</span>
                </div>
                <span className="quad-stat__label">{t('clubSpeed')}</span>
              </div>
            )}
          </div>
        </div>

        {/* Metric cards - all other stats, horizontal scroll */}
        <div className="shot-display__metrics">
          <MetricCard
            value={hasLaunchAngle ? shot.launch_angle_vertical!.toFixed(1) : '-'}
            unit={hasLaunchAngle ? '°' : undefined}
            label={t('vLaunch')}
            subtext={hasLaunchAngle ? (shot.angle_source ?? undefined) : undefined}
            variant="secondary"
            confidence={quality.vLaunch}
          />
          <MetricCard
            value={shot.launch_angle_horizontal !== null ? fmtSigned(shot.launch_angle_horizontal) : '-'}
            unit={shot.launch_angle_horizontal !== null ? '°' : undefined}
            label={t('hLaunch')}
            subtext={shot.angle_source ?? undefined}
            variant="secondary"
            confidence={quality.hLaunch}
          />
          {shot.club_angle_deg !== null && (
            <MetricCard
              value={shot.club_angle_deg.toFixed(1)}
              unit="°"
              label={t('clubAoA')}
              subtext={shot.angle_source ?? undefined}
              variant="secondary"
              confidence={quality.aoa}
            />
          )}
          {shot.club_path_deg !== null && (
            <MetricCard
              value={fmtSigned(shot.club_path_deg)}
              unit="°"
              label={t('clubPath')}
              subtext={shot.angle_source ?? undefined}
              variant="secondary"
              confidence={quality.clubPath}
              qualityLabels={directionalLabels(t)}
            />
          )}
          <MetricCard
            value={hasSpin ? fmtSpin(shot.spin_rpm) : '-'}
            unit={hasSpin ? 'rpm' : undefined}
            label={t('spinRate')}
            subtext={
              hasSpin && shot.spin_source
                ? shot.spin_source === 'calculated'
                  ? t('estimated')
                  : t('radar')
                : undefined
            }
            variant="spin"
            confidence={quality.spin}
          />
          {shot.spin_axis_deg !== null && (
            <MetricCard
              value={fmtSigned(shot.spin_axis_deg)}
              unit="°"
              label={t('spinAxis')}
              subtext={spinDir ? `${t('ball')} · ${spinDir}` : undefined}
              variant="secondary"
            />
          )}
          {shot.smash_factor != null && (
            <MetricCard
              value={shot.smash_factor.toFixed(2)}
              label={t('smash')}
              variant="secondary"
            />
          )}
          {shot.apex_height_yards != null && (
            <MetricCard
              value={formatDistance(shot.apex_height_yards, distanceUnit, 0)}
              unit={getDistanceUnit(distanceUnit)}
              label={t('apexHeight')}
              variant="secondary"
            />
          )}
          {shot.carry_side_yards != null && (
            <MetricCard
              value={formatDistance(Math.abs(shot.carry_side_yards), distanceUnit, 0)}
              unit={getDistanceUnit(distanceUnit)}
              label={t('sideCarry')}
              subtext={shot.carry_side_yards >= 0 ? t('dirRight') : t('dirLeft')}
              variant="secondary"
            />
          )}
          {shot.curve_yards != null && (
            <MetricCard
              value={formatDistance(Math.abs(shot.curve_yards), distanceUnit, 0)}
              unit={getDistanceUnit(distanceUnit)}
              label={t('curveLabel')}
              subtext={shot.curve_yards >= 0 ? t('dirRight') : t('dirLeft')}
              variant="secondary"
            />
          )}
        </div>
      </div>
    </div>
  );
}
