import { useMemo } from 'react';
import type { Shot, SpinQuality } from '../types/shot';
import { computeSwingSpeedStats, getSwingSpeedMph, isSwingSpeedShot } from '../types/shot';
import { useUnitPreference } from '../state/useUnitPreference';
import { formatCarryRange, formatDistance, formatSpeed, getDistanceUnit, getSpeedUnit } from '../utils/units';
import './ShotDisplay.css';

interface ShotDisplayProps {
  shot: Shot | null;
  shots?: Shot[];
  animate?: boolean;
  activePlayerName?: string;
  activeTrainingImplement?: string;
}

const GAUGE_MIN = 0;
const GAUGE_MAX = 200; // mph
const GAUGE_START_ANGLE = -140;
const GAUGE_END_ANGLE = 140;

function SpeedGauge({
  speedMph,
  label,
  displayValue,
  unit,
}: {
  speedMph: number;
  label: string;
  displayValue: string;
  unit: string;
}) {
  const percentage = Math.min(Math.max((speedMph - GAUGE_MIN) / (GAUGE_MAX - GAUGE_MIN), 0), 1);
  const angle = GAUGE_START_ANGLE + (GAUGE_END_ANGLE - GAUGE_START_ANGLE) * percentage;

  const radius = 85;
  const cx = 100;
  const cy = 100;

  const polarToCartesian = (centerX: number, centerY: number, r: number, angleInDegrees: number) => {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
    return {
      x: centerX + r * Math.cos(angleInRadians),
      y: centerY + r * Math.sin(angleInRadians),
    };
  };

  const describeArc = (startAngle: number, endAngle: number) => {
    const start = polarToCartesian(cx, cy, radius, endAngle);
    const end = polarToCartesian(cx, cy, radius, startAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';
    return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
  };

  const backgroundArc = describeArc(GAUGE_START_ANGLE, GAUGE_END_ANGLE);
  const valueArc = describeArc(GAUGE_START_ANGLE, angle);

  return (
    <div className="speed-gauge">
      <svg viewBox="0 0 200 140" className="speed-gauge__svg">
        <path d={backgroundArc} fill="none" stroke="var(--gauge-track)" strokeWidth="12" strokeLinecap="round" />
        <path
          d={valueArc}
          fill="none"
          stroke="url(#goldGradient)"
          strokeWidth="12"
          strokeLinecap="round"
          className="speed-gauge__value-arc"
        />
        <defs>
          <linearGradient id="goldGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="var(--color-gold-dim)" />
            <stop offset="100%" stopColor="var(--color-gold-bright)" />
          </linearGradient>
        </defs>
      </svg>
      <div className="speed-gauge__content">
        <span className="speed-gauge__value">{displayValue}</span>
        <span className="speed-gauge__unit">{unit}</span>
        <span className="speed-gauge__label">{label}</span>
      </div>
    </div>
  );
}

function MetricCard({
  value,
  unit,
  label,
  subtext,
  variant = 'default',
  confidence,
}: {
  value: string | number;
  unit?: string;
  label: string;
  subtext?: string;
  variant?: 'default' | 'primary' | 'secondary' | 'spin';
  confidence?: SpinQuality | null;
}) {
  return (
    <div className={`metric-card metric-card--${variant}`}>
      <div className="metric-card__value-row">
        <span className="metric-card__value">{value}</span>
        {unit && <span className="metric-card__unit">{unit}</span>}
      </div>
      <span className="metric-card__label">{label}</span>
      {subtext && <span className="metric-card__subtext">{subtext}</span>}
      {confidence && (
        <div className={`metric-card__confidence metric-card__confidence--${confidence}`}>
          {confidence !== 'experimental' && (
            <span className="metric-card__confidence-dots">
              <span className="dot filled" />
              <span className={`dot ${confidence === 'medium' || confidence === 'high' ? 'filled' : ''}`} />
              <span className={`dot ${confidence === 'high' ? 'filled' : ''}`} />
            </span>
          )}
          <span className="metric-card__confidence-label">{confidence}</span>
        </div>
      )}
    </div>
  );
}

function formatSpinRpm(rpm: number): string {
  return rpm.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function getLaunchAngleQuality(confidence: number | null): 'high' | 'medium' | 'low' | null {
  if (confidence === null) return null;
  if (confidence >= 0.7) return 'high';
  if (confidence >= 0.4) return 'medium';
  return 'low';
}

export function ShotDisplay({
  shot,
  shots = [],
  animate = false,
  activePlayerName,
  activeTrainingImplement,
}: ShotDisplayProps) {
  const { unitSystem } = useUnitPreference();
  const carryRange = useMemo(() => {
    if (!shot) return null;
    return formatCarryRange(shot.carry_range, unitSystem);
  }, [shot, unitSystem]);
  const swingStats = useMemo(
    () =>
      computeSwingSpeedStats(shots, {
        playerName: activePlayerName,
        trainingImplement: activeTrainingImplement,
      }),
    [shots, activePlayerName, activeTrainingImplement]
  );

  const displayCarry = shot?.carry_spin_adjusted ?? shot?.estimated_carry_yards ?? 0;
  const carrySubtext = shot?.carry_spin_adjusted ? 'spin-adjusted' : carryRange || undefined;

  if (!shot) {
    return (
      <div className="shot-display shot-display--empty">
        <div className="shot-display__waiting">
          <div className="golf-ball-indicator">
            <div className="golf-ball-indicator__ball">
              <div className="golf-ball-indicator__dimple" />
              <div className="golf-ball-indicator__dimple" />
              <div className="golf-ball-indicator__dimple" />
            </div>
            <div className="golf-ball-indicator__shadow" />
          </div>
          <p className="shot-display__waiting-text">Ready</p>
          <p className="shot-display__waiting-hint">Start a shot or swing speed session</p>
        </div>
      </div>
    );
  }

  if (isSwingSpeedShot(shot)) {
    const lastSpeed = getSwingSpeedMph(shot);
    const readingDetail =
      shot.swing_speed_reading_count !== undefined ? `${shot.swing_speed_reading_count} radar readings` : undefined;

    return (
      <div className={`shot-display shot-display--swing-speed ${animate ? 'shot-display--animate' : ''}`}>
        <div className="shot-display__layout">
          <div className="shot-display__primary">
            <SpeedGauge
              speedMph={lastSpeed}
              label="Last Swing"
              displayValue={formatSpeed(lastSpeed, unitSystem, 1)}
              unit={getSpeedUnit(unitSystem)}
            />
          </div>

          <div className="shot-display__metrics shot-display__metrics--swing-speed">
            <MetricCard
              value={formatSpeed(swingStats.best_speed_mph, unitSystem, 1)}
              unit={getSpeedUnit(unitSystem)}
              label="Best"
              subtext="player + implement"
              variant="primary"
            />
            <MetricCard
              value={formatSpeed(swingStats.avg_speed_mph, unitSystem, 1)}
              unit={getSpeedUnit(unitSystem)}
              label="Average"
              subtext={`${swingStats.count} swings`}
              variant="secondary"
            />
            <MetricCard value={swingStats.count} label="Swing Count" subtext={readingDetail} variant="secondary" />
            <MetricCard
              value={shot.training_implement_label ?? shot.club}
              label="Implement"
              subtext={
                shot.swing_speed_trigger_mph !== undefined
                  ? `${formatSpeed(shot.swing_speed_trigger_mph, unitSystem, 1)} ${getSpeedUnit(unitSystem)} trigger`
                  : 'selected'
              }
              variant="secondary"
            />
          </div>
        </div>
      </div>
    );
  }

  const hasSpin = shot.spin_rpm !== null;
  const hasLaunchAngle = shot.launch_angle_vertical !== null;

  return (
    <div className={`shot-display ${animate ? 'shot-display--animate' : ''}`}>
      <div className="shot-display__layout">
        <div className="shot-display__primary">
          <SpeedGauge
            speedMph={shot.ball_speed_mph}
            label="Ball Speed"
            displayValue={formatSpeed(shot.ball_speed_mph, unitSystem, 1)}
            unit={getSpeedUnit(unitSystem)}
          />
        </div>

        <div className="shot-display__metrics">
          <MetricCard
            value={formatDistance(displayCarry, unitSystem, 0)}
            unit={getDistanceUnit(unitSystem)}
            label="Est. Carry"
            subtext={carrySubtext}
            variant="primary"
          />
          <MetricCard
            value={shot.club_speed_mph ? formatSpeed(shot.club_speed_mph, unitSystem, 1) : '—'}
            unit={shot.club_speed_mph ? getSpeedUnit(unitSystem) : undefined}
            label="Club Speed"
            subtext={shot.smash_factor ? `${shot.smash_factor.toFixed(2)} smash` : undefined}
            variant="secondary"
          />
          <MetricCard
            value={hasLaunchAngle ? shot.launch_angle_vertical!.toFixed(1) : '—'}
            unit={hasLaunchAngle ? '°' : undefined}
            label="V. Launch"
            subtext={hasLaunchAngle ? (shot.angle_source ?? undefined) : undefined}
            variant="secondary"
            confidence={hasLaunchAngle ? getLaunchAngleQuality(shot.launch_angle_confidence) : null}
          />
          {shot.club_angle_deg !== null && (
            <MetricCard
              value={shot.club_angle_deg.toFixed(1)}
              unit="°"
              label="Club AoA"
              subtext="radar"
              variant="secondary"
            />
          )}
          {shot.club_path_deg !== null && (
            <MetricCard
              value={(shot.club_path_deg >= 0 ? '+' : '') + shot.club_path_deg.toFixed(1)}
              unit="°"
              label="Club Path"
              subtext="radar"
              variant="secondary"
            />
          )}
          {shot.spin_axis_deg !== null && (
            <MetricCard
              value={(shot.spin_axis_deg >= 0 ? '+' : '') + shot.spin_axis_deg.toFixed(1)}
              unit="°"
              label="Spin Axis"
              subtext={shot.spin_axis_deg > 2 ? 'fade' : shot.spin_axis_deg < -2 ? 'draw' : 'straight'}
              variant="secondary"
            />
          )}
          {shot.launch_angle_horizontal !== null && (
            <MetricCard
              value={(shot.launch_angle_horizontal >= 0 ? '+' : '') + shot.launch_angle_horizontal.toFixed(1)}
              unit="°"
              label="H. Launch"
              subtext={shot.angle_source ?? undefined}
              variant="secondary"
              confidence={getLaunchAngleQuality(shot.launch_angle_confidence)}
            />
          )}
          <MetricCard
            value={hasSpin ? formatSpinRpm(shot.spin_rpm!) : '—'}
            unit={hasSpin ? 'rpm' : undefined}
            label="Spin Rate"
            subtext={
              hasSpin && shot.spin_source ? (shot.spin_source === 'calculated' ? 'estimated' : 'radar') : undefined
            }
            variant="spin"
            confidence={hasSpin ? shot.spin_quality : null}
          />
        </div>
      </div>
    </div>
  );
}
