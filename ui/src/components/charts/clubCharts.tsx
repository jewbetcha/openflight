import { memo, useMemo } from 'react';
import { useLanguage } from '../../state/useLanguage';
import { useThemeColors } from '../../state/useThemeColors';
import type { Shot } from '../../types/shot';
import type { DistanceUnit } from '../../utils/units';
import { carryVal, stdDev } from '../../utils/statsData';
import './clubCharts.css';

/**
 * Shared club charts, extracted from StatsView so both the Stats "Clubs" tab
 * and the passive /display no-camera visualizer render from one source.
 *
 * Both are wrapped in React.memo: on /display the parent re-renders on every
 * incoming shot, but an unchanged `shots` reference skips the SVG math - the
 * derivations are also useMemo'd (P1A: keep the Pi off the recompute treadmill).
 *
 * When `animateKey` is set, the MOST RECENT shot's mark animates in (the arc
 * sweeps for the trajectory, the dot slams for the dispersion). Changing the
 * key replays it. Stats passes no key, so its behaviour is unchanged.
 */
export interface ClubChartProps {
  shots: Shot[];
  clubColors: Record<string, string>;
  distUnit: DistanceUnit;
  /** Replay token - when it changes, the latest shot's mark animates in. */
  animateKey?: string | null;
  /** Total sweep duration (ms). The dispersion slam is timed to land at the end. */
  animationMs?: number;
}

const SLAM_MS = 260;

// ── Dispersion chart (top-down polar) ─────────────────────────────────────────

const CHART_W = 300;
const CHART_H = 260;
const CHART_CX = CHART_W / 2; // 150 - lateral centre
const CHART_CY = CHART_H - 12; // 248 - golfer position (bottom)

export const DispersionChart = memo(function DispersionChart({
  shots,
  clubColors,
  distUnit,
  animateKey = null,
  animationMs = 1200,
}: ClubChartProps) {
  const { t } = useLanguage();
  const theme = useThemeColors();
  // Value-stable string (depends only on colour-blind mode), so the heavy memo
  // below doesn't re-run just because useThemeColors() returns a fresh object.
  const ellipseFallback = theme.goldA(0.5);

  const derived = useMemo(() => {
    const carries = shots.map((s) => carryVal(s, distUnit)).filter((v) => v > 0);
    if (carries.length === 0) return null;

    const maxCarry = Math.max(...carries, 10);
    const SCALE = (CHART_H - 28) / maxCarry; // px per yard/metre

    const step = maxCarry <= 120 ? 25 : maxCarry <= 250 ? 50 : 75;
    const rings: number[] = [];
    for (let d = step; d <= maxCarry + step; d += step) rings.push(d);

    const hasHAngle = shots.some((s) => s.launch_angle_horizontal != null);

    const clubs = Array.from(new Set(shots.map((s) => s.club)));
    const clubEllipses = clubs
      .map((club) => {
        const cs = shots.filter((s) => s.club === club);
        if (cs.length < 3) return null;
        const svgPts = cs
          .map((s) => {
            const c = carryVal(s, distUnit);
            if (c <= 0) return null;
            const aRad = ((s.launch_angle_horizontal ?? 0) * Math.PI) / 180;
            return { x: CHART_CX + c * Math.sin(aRad) * SCALE, y: CHART_CY - c * Math.cos(aRad) * SCALE };
          })
          .filter((p): p is { x: number; y: number } => p !== null);
        if (svgPts.length < 3) return null;
        const xs = svgPts.map((p) => p.x);
        const ys = svgPts.map((p) => p.y);
        const cx = xs.reduce((a, b) => a + b, 0) / xs.length;
        const cy = ys.reduce((a, b) => a + b, 0) / ys.length;
        const rx = Math.max(stdDev(xs), 2);
        const ry = Math.max(stdDev(ys), 2);
        return { club, cx, cy, rx, ry, color: clubColors[club] ?? ellipseFallback };
      })
      .filter((e): e is NonNullable<typeof e> => e !== null);

    return { maxCarry, SCALE, rings, hasHAngle, clubEllipses };
  }, [shots, distUnit, clubColors, ellipseFallback]);

  if (!derived) return <div className="chart-empty">{t('chartNoCarry')}</div>;
  const { SCALE, rings, hasHAngle, clubEllipses } = derived;
  const lastIdx = shots.length - 1;

  return (
    <div className="dispersion-chart">
      <span className="dispersion-chart__title">{t('dispersionTitle')}</span>
      {/* Decorative: the same numbers are in the metric grid / club table, so
          the SVG is hidden from screen readers (it would otherwise announce
          dozens of unlabeled tick/ring numbers). */}
      <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} className="dispersion-chart__svg" aria-hidden="true" focusable="false">
        <defs>
          <clipPath id="polar-clip">
            <rect x={0} y={0} width={CHART_W} height={CHART_H} />
          </clipPath>
        </defs>

        {/* Concentric semicircle rings */}
        {rings.map((d) => {
          const r = d * SCALE;
          if (r > CHART_CY + 10) return null;
          return (
            <g key={d}>
              <path
                d={`M ${CHART_CX - r} ${CHART_CY} A ${r} ${r} 0 0 1 ${CHART_CX + r} ${CHART_CY}`}
                fill="none" stroke="rgba(245,240,230,0.22)" strokeWidth="0.75" clipPath="url(#polar-clip)"
              />
              <text x={CHART_CX + 3} y={CHART_CY - r + 7}
                fontSize="7" fill="rgba(245,240,230,0.55)" fontFamily="inherit">
                {d}
              </text>
            </g>
          );
        })}

        {/* Centre line */}
        <line x1={CHART_CX} y1={CHART_CY} x2={CHART_CX} y2={10}
          stroke="rgba(245,240,230,0.2)" strokeWidth="0.75" />

        {/* Per-club 1-sigma dispersion ellipses */}
        {clubEllipses.map(({ club, cx, cy, rx, ry, color }) => (
          <ellipse key={`ell-${club}`} cx={cx} cy={cy} rx={rx} ry={ry}
            fill="none" stroke={color} strokeWidth="1.25" strokeDasharray="4 2"
            opacity={0.45} clipPath="url(#polar-clip)" />
        ))}

        {/* Origin point */}
        <circle cx={CHART_CX} cy={CHART_CY} r={3} fill="rgba(245,240,230,0.15)" />

        {/* Shot dots */}
        {shots.map((shot, i) => {
          const c = carryVal(shot, distUnit);
          if (c <= 0) return null;
          const aRad = ((shot.launch_angle_horizontal ?? 0) * Math.PI) / 180;
          const x = CHART_CX + c * Math.sin(aRad) * SCALE;
          const y = CHART_CY - c * Math.cos(aRad) * SCALE;
          const color = clubColors[shot.club] ?? theme.goldA(0.9);
          const animate = animateKey != null && i === lastIdx;
          return (
            <circle
              key={animate ? `slam-${animateKey}` : i}
              cx={x} cy={y} r={animate ? 4.5 : 3.5} fill={color} opacity={0.9}
              clipPath="url(#polar-clip)"
              className={animate ? 'disp-dot--slam' : undefined}
              style={animate ? { animationDuration: `${SLAM_MS}ms`, animationDelay: `${Math.max(animationMs - SLAM_MS, 0)}ms` } : undefined}
            />
          );
        })}
      </svg>
      {!hasHAngle && <p className="chart-note">{t('needKLD7')}</p>}
    </div>
  );
});

// ── Trajectory chart (side view) ──────────────────────────────────────────────

const TRAJ_W = 340;
const TRAJ_H = 220;
const TRAJ_PAD_L = 22;
const TRAJ_PAD_R = 8;
const TRAJ_PAD_T = 16;
const TRAJ_PAD_B = 20;
const TRAJ_CW = TRAJ_W - TRAJ_PAD_L - TRAJ_PAD_R;
const TRAJ_CH = TRAJ_H - TRAJ_PAD_T - TRAJ_PAD_B;

export const TrajectoryChart = memo(function TrajectoryChart({
  shots,
  clubColors,
  distUnit,
  animateKey = null,
  animationMs = 1200,
}: ClubChartProps) {
  const { t } = useLanguage();
  const theme = useThemeColors();

  const derived = useMemo(() => {
    const carries = shots.map((s) => carryVal(s, distUnit)).filter((v) => v > 0);
    if (carries.length === 0) return null;

    const maxCarry = Math.max(...carries, 10);
    const carryScale = TRAJ_CW / maxCarry;

    const estimatedApexes = shots.map((s) => {
      const angle = (s.launch_angle_vertical ?? 15) * (Math.PI / 180);
      return (carryVal(s, distUnit) * Math.tan(angle)) / 4;
    });
    const maxApex = Math.max(...estimatedApexes, 10);
    const apexScale = TRAJ_CH / maxApex;

    const useDefaultAngle = shots.filter((s) => s.launch_angle_vertical != null).length === 0;

    return { maxCarry, carryScale, apexScale, useDefaultAngle };
  }, [shots, distUnit]);

  if (!derived) return <div className="chart-empty">{t('chartNoCarry')}</div>;
  const { maxCarry, carryScale, apexScale, useDefaultAngle } = derived;
  const lastIdx = shots.length - 1;

  return (
    <div className="trajectory-chart">
      <span className="trajectory-chart__title">{t('trajectoryTitle')}</span>
      {/* Decorative duplicate of the grid data - hidden from screen readers. */}
      <svg viewBox={`0 0 ${TRAJ_W} ${TRAJ_H}`} className="trajectory-chart__svg" aria-hidden="true" focusable="false">
        {/* Gridlines */}
        {[0.25, 0.5, 0.75].map((f) => {
          const y = TRAJ_PAD_T + TRAJ_CH - f * TRAJ_CH;
          return (
            <line key={f} x1={TRAJ_PAD_L} y1={y} x2={TRAJ_PAD_L + TRAJ_CW} y2={y}
              stroke="rgba(245,240,230,0.18)" strokeWidth="0.75" />
          );
        })}

        {/* Ground line */}
        <line x1={TRAJ_PAD_L} y1={TRAJ_PAD_T + TRAJ_CH}
          x2={TRAJ_PAD_L + TRAJ_CW} y2={TRAJ_PAD_T + TRAJ_CH}
          stroke="rgba(245,240,230,0.35)" strokeWidth="1" />

        {/* Distance labels */}
        {[0.25, 0.5, 0.75, 1.0].map((f) => {
          const x = TRAJ_PAD_L + f * TRAJ_CW;
          return (
            <text key={f} x={x} y={TRAJ_H - 4} textAnchor="middle"
              fontSize="7" fill="rgba(245,240,230,0.55)" fontFamily="inherit">
              {Math.round(f * maxCarry)}
            </text>
          );
        })}

        {/* Trajectory arcs (quadratic bezier parabola) */}
        {shots.map((shot, i) => {
          const c = carryVal(shot, distUnit);
          if (c <= 0) return null;
          const angle = shot.launch_angle_vertical ?? (useDefaultAngle ? 15 : null);
          if (angle == null) return null;

          const aRad = angle * (Math.PI / 180);
          const apex = (c * Math.tan(aRad)) / 4;

          const x0 = TRAJ_PAD_L;
          const y0 = TRAJ_PAD_T + TRAJ_CH;
          const x1 = TRAJ_PAD_L + (c / 2) * carryScale;
          const y1 = TRAJ_PAD_T + TRAJ_CH - Math.min(apex * apexScale, TRAJ_CH - 4);
          const x2 = TRAJ_PAD_L + c * carryScale;
          const y2 = TRAJ_PAD_T + TRAJ_CH;

          const color = clubColors[shot.club] ?? theme.goldA(0.85);
          const animate = animateKey != null && i === lastIdx;
          return (
            <path
              key={animate ? `draw-${animateKey}` : i}
              d={`M ${x0} ${y0} Q ${x1} ${y1} ${x2} ${y2}`}
              fill="none" stroke={color} strokeWidth={animate ? 2.5 : 1.75} opacity={0.85}
              className={animate ? 'traj-arc--animate' : undefined}
              pathLength={animate ? 100 : undefined}
              style={animate ? { animationDuration: `${animationMs}ms` } : undefined}
            />
          );
        })}

        {/* Origin dot */}
        <circle cx={TRAJ_PAD_L} cy={TRAJ_PAD_T + TRAJ_CH} r={2.5}
          fill="rgba(245,240,230,0.3)" />
      </svg>
      {useDefaultAngle && <p className="chart-note">{t('trajectoryDefaultAngle')}</p>}
    </div>
  );
});
