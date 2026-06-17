import { useThemeColors } from '../state/useThemeColors';
import './SpeedGauge.css';

const GAUGE_RADAR_MIN = 35; // mph - radar's minimum detected speed
const GAUGE_START_ANGLE = -140;
const GAUGE_END_ANGLE = 140;

/** Radial speed gauge with a gold value arc. Shared by the kiosk live view and the TV /display. */
export function SpeedGauge({
  speedMph,
  gaugeMax,
  label,
  displayValue,
  unit,
}: {
  speedMph: number;
  gaugeMax: number;
  label: string;
  displayValue: string;
  unit: string;
}) {
  const theme = useThemeColors();
  // Guard against non-finite speed (bad payload) and a degenerate range
  // (gaugeMax === min) so the SVG arc can never receive NaN and blank out.
  const span = gaugeMax - GAUGE_RADAR_MIN;
  const fraction = Number.isFinite(speedMph) && span > 0 ? (speedMph - GAUGE_RADAR_MIN) / span : 0;
  const percentage = Math.min(Math.max(fraction, 0), 1);
  const angle = GAUGE_START_ANGLE + (GAUGE_END_ANGLE - GAUGE_START_ANGLE) * percentage;
  const safeSpeed = Number.isFinite(speedMph) ? speedMph : GAUGE_RADAR_MIN;

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
    <div
      className="speed-gauge"
      role="meter"
      aria-label={label}
      aria-valuenow={safeSpeed}
      aria-valuemin={GAUGE_RADAR_MIN}
      aria-valuemax={gaugeMax}
      aria-valuetext={`${displayValue} ${unit}`}
    >
      <svg viewBox="0 0 200 140" className="speed-gauge__svg" aria-hidden="true">
        <path d={backgroundArc} fill="none" stroke="rgba(245, 240, 230, 0.1)" strokeWidth="12" strokeLinecap="round" />
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
            <stop offset="0%" stopColor={theme.goldDim} />
            <stop offset="100%" stopColor={theme.gold} />
          </linearGradient>
        </defs>
      </svg>
      <div className="speed-gauge__content" aria-hidden="true">
        <span className="speed-gauge__value">{displayValue}</span>
        <span className="speed-gauge__unit">{unit}</span>
        <span className="speed-gauge__label">{label}</span>
      </div>
    </div>
  );
}
