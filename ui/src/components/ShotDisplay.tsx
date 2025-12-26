import { useMemo } from 'react';
import type { Shot } from '../types/shot';
import './ShotDisplay.css';

interface ShotDisplayProps {
  shot: Shot | null;
  isLatest?: boolean;
}

// Speed gauge configuration
const GAUGE_MIN = 0;
const GAUGE_MAX = 200; // mph
const GAUGE_START_ANGLE = -140;
const GAUGE_END_ANGLE = 140;

function SpeedGauge({ speed, label }: { speed: number; label: string }) {
  const percentage = Math.min(Math.max((speed - GAUGE_MIN) / (GAUGE_MAX - GAUGE_MIN), 0), 1);
  const angle = GAUGE_START_ANGLE + (GAUGE_END_ANGLE - GAUGE_START_ANGLE) * percentage;

  // SVG arc path calculation
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
        {/* Background arc */}
        <path
          d={backgroundArc}
          fill="none"
          stroke="rgba(245, 240, 230, 0.1)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Value arc */}
        <path
          d={valueArc}
          fill="none"
          stroke="url(#goldGradient)"
          strokeWidth="12"
          strokeLinecap="round"
          className="speed-gauge__value-arc"
        />
        {/* Gradient definition */}
        <defs>
          <linearGradient id="goldGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#A68B2A" />
            <stop offset="100%" stopColor="#F4CF47" />
          </linearGradient>
        </defs>
      </svg>
      <div className="speed-gauge__content">
        <span className="speed-gauge__value">{speed.toFixed(1)}</span>
        <span className="speed-gauge__unit">mph</span>
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
}: {
  value: string | number;
  unit?: string;
  label: string;
  subtext?: string;
  variant?: 'default' | 'primary' | 'secondary';
}) {
  return (
    <div className={`metric-card metric-card--${variant}`}>
      <div className="metric-card__value-row">
        <span className="metric-card__value">{value}</span>
        {unit && <span className="metric-card__unit">{unit}</span>}
      </div>
      <span className="metric-card__label">{label}</span>
      {subtext && <span className="metric-card__subtext">{subtext}</span>}
    </div>
  );
}

export function ShotDisplay({ shot, isLatest = true }: ShotDisplayProps) {
  const carryRange = useMemo(() => {
    if (!shot) return null;
    return `${shot.carry_range[0]}–${shot.carry_range[1]} yds`;
  }, [shot]);

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
          <p className="shot-display__waiting-text">Ready for your shot</p>
          <p className="shot-display__waiting-hint">Position ball in front of radar</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`shot-display ${isLatest ? 'shot-display--latest' : ''}`}>
      <div className="shot-display__layout">
        {/* Left: Ball Speed Gauge */}
        <div className="shot-display__primary">
          <SpeedGauge speed={shot.ball_speed_mph} label="Ball Speed" />
        </div>

        {/* Right: Secondary Metrics */}
        <div className="shot-display__metrics">
          <MetricCard
            value={shot.estimated_carry_yards}
            unit="yds"
            label="Est. Carry"
            subtext={carryRange || undefined}
            variant="primary"
          />
          <MetricCard
            value={shot.club_speed_mph ? shot.club_speed_mph.toFixed(1) : '—'}
            unit={shot.club_speed_mph ? 'mph' : undefined}
            label="Club Speed"
            variant="secondary"
          />
          <MetricCard
            value={shot.smash_factor ? shot.smash_factor.toFixed(2) : '—'}
            label="Smash Factor"
            variant="secondary"
          />
        </div>
      </div>
    </div>
  );
}
