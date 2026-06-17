import { useMemo, useState } from 'react';
import { useUnitPreference } from '../state/useUnitPreference';
import { useLanguage } from '../state/useLanguage';
import { useThemeColors } from '../state/useThemeColors';
import { useStatsData } from '../state/useStatsData';
import type { Shot } from '../types/shot';
import { getUniqueClubs } from '../types/shot';
import {
  convertDistanceFromYards,
  formatDistance,
  formatSpeed,
  getDistanceUnit,
  getSpeedUnit,
  type DistanceUnit,
} from '../utils/units';
import { ALL_CLUBS } from '../data/clubs';
import {
  MA_WINDOW,
  getClubColors,
  medianOf,
  carryVal,
  formatDate,
  computeBoxStats,
  computeTrendsSummary,
  getGroupShots,
  TREND_CLUB_GROUPS,
  type BoxStats,
  type MetricStats,
  type TrendsSummary,
  type ClubGroupKey,
} from '../utils/statsData';
import { StatsAnalysis } from './StatsAnalysis';
import { ShotList } from './ShotList';
import { DispersionChart, TrajectoryChart } from './charts/clubCharts';
import './StatsAnalysis.css';
import './StatsView.css';

interface StatsViewProps {
  shots: Shot[];
  onClearSession: () => void;
}

type SubView = 'home' | 'clubs' | 'trends' | 'coaching' | 'shots';

const CLUB_LABEL = Object.fromEntries(ALL_CLUBS.map((c) => [c.id, c.label]));

// Pure stats helpers (palettes, getClubColors, medianOf, carryVal, formatDate,
// box-plot + trends computation, club groups) now live in ../utils/statsData.

// ── Overview charts (unchanged from prior version) ────────────────────────────

function CarryHistogram({ shots, distanceUnit }: { shots: Shot[]; distanceUnit: DistanceUnit }) {
  const theme = useThemeColors();
  const carries = shots
    .map((s) => convertDistanceFromYards(s.carry_spin_adjusted ?? s.estimated_carry_yards, distanceUnit))
    .filter((v) => v > 0);
  if (carries.length < 3) return null;

  const min = Math.min(...carries);
  const max = Math.max(...carries);
  const range = max - min || 1;
  const binCount = Math.min(10, Math.max(4, Math.ceil(carries.length / 3)));
  const binSize = range / binCount;
  const bins = Array.from({ length: binCount }, (_, i) => ({
    lo: min + i * binSize, hi: min + (i + 1) * binSize, count: 0,
  }));
  carries.forEach((c) => { const idx = Math.min(Math.floor((c - min) / binSize), binCount - 1); bins[idx].count++; });
  const peak = Math.max(...bins.map((b) => b.count));

  const W = 500, H = 80, PAD_X = 2, PAD_TOP = 6, PAD_BOT = 22;
  const chartH = H - PAD_TOP - PAD_BOT;
  const slotW = (W - PAD_X * 2) / binCount;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="carry-histogram__svg">
      <defs>
        <linearGradient id="bar-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={theme.goldA(0.7)} />
          <stop offset="100%" stopColor={theme.goldA(0.2)} />
        </linearGradient>
      </defs>
      {bins.map((bin, i) => {
        const barH = peak > 0 ? (bin.count / peak) * chartH : 0;
        const x = PAD_X + i * slotW;
        const y = PAD_TOP + chartH - barH;
        const isMax = bin.count === peak && bin.count > 0;
        return (
          <g key={i}>
            {bin.count > 0 && (
              <rect x={x + 1.5} y={y} width={slotW - 3} height={barH}
                fill={isMax ? 'url(#bar-grad)' : theme.goldA(0.22)} rx="2" />
            )}
            <text x={x + slotW / 2} y={H - 6} textAnchor="middle" fontSize="7.5"
              fill="rgba(245,240,230,0.38)" fontFamily="inherit">{Math.round(bin.lo)}</text>
          </g>
        );
      })}
      <line x1={PAD_X} y1={H - PAD_BOT} x2={W - PAD_X} y2={H - PAD_BOT} stroke="rgba(245,240,230,0.08)" strokeWidth="0.75" />
    </svg>
  );
}

function ClubBars({ shots, clubs, distanceUnit }: { shots: Shot[]; clubs: string[]; distanceUnit: DistanceUnit }) {
  if (clubs.length < 2) return null;
  const avgs = clubs.map((club) => {
    const cs = shots.filter((s) => s.club === club);
    const carries = cs.map((s) => convertDistanceFromYards(s.carry_spin_adjusted ?? s.estimated_carry_yards, distanceUnit));
    return { club, avg: carries.reduce((a, b) => a + b, 0) / carries.length };
  });
  const maxAvg = Math.max(...avgs.map((a) => a.avg));
  const unit = getDistanceUnit(distanceUnit);
  return (
    <div className="club-bars">
      {avgs.map(({ club, avg }) => (
        <div key={club} className="club-bars__row">
          <span className="club-bars__label">{club.toUpperCase()}</span>
          <div className="club-bars__track">
            <div className="club-bars__fill" style={{ width: `${(avg / maxAvg) * 100}%` }} />
          </div>
          <span className="club-bars__value">{Math.round(avg)} {unit}</span>
        </div>
      ))}
    </div>
  );
}

// Dispersion + Trajectory charts now live in ./charts/clubCharts (shared with
// the /display no-camera visualizer). Imported at the top of this file.

// ── Clubs view ────────────────────────────────────────────────────────────────

function ClubsView({ shots, distUnit }: { shots: Shot[]; distUnit: DistanceUnit }) {
  const theme = useThemeColors();
  const { t } = useLanguage();
  const clubs = useMemo(() => getUniqueClubs(shots), [shots]);
  const clubColors = useMemo(() => getClubColors(clubs, theme.isColorBlind), [clubs, theme.isColorBlind]);
  const unit = getDistanceUnit(distUnit);

  // Per-club stats, sorted by median carry descending
  const clubStats = useMemo(() => {
    const rows = clubs.map((club) => {
      const cs = shots.filter((s) => s.club === club);
      const carries = cs.map((s) => carryVal(s, distUnit)).filter((v) => v > 0);
      const med = Math.round(medianOf(carries));
      const longest = carries.length > 0 ? Math.round(Math.max(...carries)) : 0;
      return { club, med, longest, count: cs.length };
    });
    return rows.sort((a, b) => b.med - a.med);
  }, [clubs, shots, distUnit]);

  // Gapping: distance between consecutive clubs by median
  const gappedRows = useMemo(
    () => clubStats.map((row, i) => ({
      ...row,
      gap: i < clubStats.length - 1 ? row.med - clubStats[i + 1].med : null,
    })),
    [clubStats],
  );

  if (shots.length === 0) {
    return (
      <div className="clubs-view stats-analysis--empty">
        <p>{t('chartNoShotData')}</p>
      </div>
    );
  }

  return (
    <div className="clubs-view">
      {/* Club table */}
      <div className="analysis-card clubs-card">
        <span className="analysis-card__title">{t('clubsOverview')}</span>
        <div className="distance-table-wrap">
          <table className="distance-table" aria-label={t('a11yClubCarryStats')}>
            <thead>
              <tr>
                <th className="dt__h dt__h--club">{t('clubLabel')}</th>
                <th className="dt__h dt__h--num">{t('colMedian')} ({unit})</th>
                <th className="dt__h dt__h--num">{t('colGapping')}</th>
                <th className="dt__h dt__h--num">{t('colLongest')}</th>
                <th className="dt__h dt__h--num">{t('colCount')}</th>
              </tr>
            </thead>
            <tbody>
              {gappedRows.map((row) => (
                <tr key={row.club} className="dt__row">
                  <td className="dt__d dt__d--club">
                    <span
                      className="club-color-dot"
                      style={{ background: clubColors[row.club] }}
                      aria-hidden="true"
                    />
                    {row.club.toUpperCase()}
                  </td>
                  <td className="dt__d dt__d--primary">{row.med}</td>
                  <td className="dt__d dt__d--muted">
                    {row.gap != null ? `+${row.gap}` : '-'}
                  </td>
                  <td className="dt__d">{row.longest}</td>
                  <td className="dt__d dt__d--muted">{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Charts row */}
      <div className="clubs-charts-row">
        <div className="analysis-card clubs-chart-card">
          <DispersionChart shots={shots} clubColors={clubColors} distUnit={distUnit} />
        </div>
        <div className="analysis-card clubs-chart-card">
          <TrajectoryChart shots={shots} clubColors={clubColors} distUnit={distUnit} />
        </div>
      </div>

      {/* Club legend */}
      {clubs.length > 1 && (
        <div className="club-legend">
          {clubs.map((club) => (
            <span key={club} className="club-legend__item">
              <span className="club-legend__dot" style={{ background: clubColors[club] }} aria-hidden="true" />
              {club.toUpperCase()}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Trend line chart ──────────────────────────────────────────────────────────

interface TrendPoint { idx: number; value: number; club: string; }

function TrendLineChart({
  points, clubColors,
}: { points: TrendPoint[]; clubColors: Record<string, string> }) {
  const theme = useThemeColors();

  // Build per-club groups in encounter order, re-indexed 0..N locally
  const clubGroups = useMemo(() => {
    const order: string[] = [];
    const groups: Record<string, TrendPoint[]> = {};
    for (const p of points) {
      if (!groups[p.club]) { order.push(p.club); groups[p.club] = []; }
      groups[p.club].push(p);
    }
    return order
      .filter((c) => groups[c].length >= 1)
      .map((club) => ({ club, pts: groups[club] }));
  }, [points]);

  if (points.length < 2 || clubGroups.length === 0) return null;

  // Shared Y scale across ALL clubs so facets are comparable
  const vals = points.map((p) => p.value);
  const minV = Math.min(...vals), maxV = Math.max(...vals);
  const span = maxV - minV || 1;

  // Layout: one panel per club, side-by-side
  const AXIS_W = 28;       // left y-axis column (labels only on first panel)
  const GAP = 8;            // gap between panels
  const PT = 14, PB = 22, PR = 4;
  const PANEL_H = 96;
  const CH = PANEL_H - PT - PB;
  const nPanels = clubGroups.length;
  // Total SVG width: axis + panels + gaps
  const PANEL_W = Math.max(80, Math.floor((500 - AXIS_W - GAP * (nPanels - 1) - PR) / nPanels));
  const TOTAL_W = AXIS_W + nPanels * PANEL_W + GAP * (nPanels - 1) + PR;

  const toY = (v: number) => PT + CH - ((v - minV) / span) * CH;
  const yTicks = [minV, minV + span * 0.5, maxV];

  return (
    <svg viewBox={`0 0 ${TOTAL_W} ${PANEL_H}`} preserveAspectRatio="none" className="trend-chart__svg">
      {/* Shared y-axis labels on the left */}
      {yTicks.map((v) => (
        <text key={v} x={AXIS_W - 3} y={toY(v) + 3} textAnchor="end"
          fontSize="7" fill="rgba(245,240,230,0.55)" fontFamily="inherit">
          {Math.round(v)}
        </text>
      ))}

      {clubGroups.map(({ club, pts }, panelIdx) => {
        const color = clubColors[club] ?? theme.goldA(0.9);
        const px0 = AXIS_W + panelIdx * (PANEL_W + GAP);
        const n = pts.length;
        const toX = (i: number) => px0 + (n <= 1 ? PANEL_W / 2 : (i / (n - 1)) * PANEL_W);

        // MA path (normalized local index)
        const maPath = n >= 3
          ? pts.map((_p, i) => {
              const w = pts.slice(Math.max(0, i - MA_WINDOW + 1), i + 1);
              const mavg = w.reduce((s, x) => s + x.value, 0) / w.length;
              return `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(mavg).toFixed(1)}`;
            }).join(' ')
          : null;

        return (
          <g key={club}>
            {/* Panel background grid lines */}
            {yTicks.map((v) => (
              <line key={v} x1={px0} y1={toY(v)} x2={px0 + PANEL_W} y2={toY(v)}
                stroke="rgba(245,240,230,0.12)" strokeWidth="0.75" />
            ))}
            {/* Bottom baseline */}
            <line x1={px0} y1={PT + CH} x2={px0 + PANEL_W} y2={PT + CH}
              stroke="rgba(245,240,230,0.22)" strokeWidth="0.75" />
            {/* Left border */}
            <line x1={px0} y1={PT} x2={px0} y2={PT + CH}
              stroke="rgba(245,240,230,0.15)" strokeWidth="0.75" />
            {/* Club label above panel */}
            <text x={px0 + PANEL_W / 2} y={PT - 4} textAnchor="middle"
              fontSize="7" fill={color} fontFamily="inherit" opacity={0.9}>
              {CLUB_LABEL[club] ?? club}
            </text>
            {/* Shot count below panel */}
            <text x={px0 + PANEL_W / 2} y={PT + CH + 11} textAnchor="middle"
              fontSize="6" fill="rgba(245,240,230,0.3)" fontFamily="inherit">
              {n} shots
            </text>
            {/* MA dashed line */}
            {maPath && (
              <path d={maPath} fill="none" stroke={color} strokeWidth="1.75"
                strokeDasharray="4 2" opacity={0.85} />
            )}
            {/* Shot dots */}
            {pts.map((p, i) => (
              <circle key={i} cx={toX(i)} cy={toY(p.value)} r={2.5}
                fill={color} opacity={0.88} />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// Box-plot utilities, trends summary, and club-group helpers now live in
// ../utils/statsData (imported above).

function ClubSelector({
  shots, selectedGroup, onSelect,
}: {
  shots: Shot[];
  selectedGroup: ClubGroupKey | 'all';
  onSelect: (g: ClubGroupKey | 'all') => void;
}) {
  const { t } = useLanguage();
  const presentIds = useMemo(() => new Set(shots.map((s) => s.club)), [shots]);
  const visibleGroups = useMemo(
    () => TREND_CLUB_GROUPS.filter((g) => g.ids.some((id) => presentIds.has(id))),
    [presentIds],
  );
  return (
    <div className="trends-club-selector" role="group" aria-label={t('a11yFilterByClub')}>
      <button
        className={`trends-club-pill${selectedGroup === 'all' ? ' trends-club-pill--active' : ''}`}
        onClick={() => onSelect('all')}
        aria-pressed={selectedGroup === 'all'}
      >
        All
      </button>
      {visibleGroups.map((g) => (
        <button
          key={g.key}
          className={`trends-club-pill${selectedGroup === g.key ? ' trends-club-pill--active' : ''}`}
          onClick={() => onSelect(g.key)}
          aria-pressed={selectedGroup === g.key}
        >
          {g.label}
        </button>
      ))}
    </div>
  );
}

// ── Stats summary table ───────────────────────────────────────────────────────

function TrendIndicator({ value }: { value: number | null }) {
  const theme = useThemeColors();
  if (value == null) return <span className="trends-trend-flat">-</span>;
  if (value > 1)  return <span style={{ color: theme.pos }}>▲ {value.toFixed(1)}%</span>;
  if (value < -1) return <span style={{ color: theme.neg }}>▼ {Math.abs(value).toFixed(1)}%</span>;
  return <span className="trends-trend-flat">~ {Math.abs(value).toFixed(1)}%</span>;
}

function StatsSummaryTable({ summary, distUnit, showTrend = true }: { summary: TrendsSummary; distUnit: DistanceUnit; showTrend?: boolean }) {
  const { t } = useLanguage();
  const { speedUnit } = useUnitPreference();
  const dUnit = getDistanceUnit(distUnit);
  const sUnit = getSpeedUnit(speedUnit);

  const fD    = (v: number | null) => v == null ? '-' : formatDistance(v, distUnit, 0);
  const fS    = (v: number | null) => v == null ? '-' : formatSpeed(v, speedUnit, 1);
  const fN2   = (v: number | null) => v == null ? '-' : v.toFixed(2);
  const fA    = (v: number | null) => v == null ? '-' : `${v.toFixed(1)}°`;
  const fSpin = (v: number | null) => v == null ? '-' : `${(v / 1000).toFixed(1)}k`;
  const fDev  = (v: number | null) => {
    if (v == null) return '-';
    return `${Math.abs(v).toFixed(1)} ${v >= 0 ? 'R' : 'L'}`;
  };

  const cols: Array<{ key: string; hd: string; fmt: (v: number | null) => string; m: MetricStats }> = [
    { key: 'carry',  hd: `Carry (${dUnit})`, fmt: fD,    m: summary.carry  },
    { key: 'total',  hd: `Total (${dUnit})`, fmt: fD,    m: summary.total  },
    { key: 'apex',   hd: `Apex (${dUnit})`,  fmt: fD,    m: summary.apex   },
    { key: 'ball',   hd: `Ball (${sUnit})`,  fmt: fS,    m: summary.ball   },
    { key: 'club',   hd: `Club (${sUnit})`,  fmt: fS,    m: summary.club   },
    { key: 'smash',  hd: 'Smash',            fmt: fN2,   m: summary.smash  },
    { key: 'launch', hd: 'Launch',           fmt: fA,    m: summary.launch },
    { key: 'spin',   hd: 'Spin',             fmt: fSpin, m: summary.spin   },
    { key: 'dev',    hd: `Dev (${dUnit})`,   fmt: fDev,  m: summary.dev    },
    { key: 'path',   hd: 'Path',             fmt: fA,    m: summary.path   },
  ];

  return (
    <div className="analysis-card trends-stats-card">
      <span className="analysis-card__title">{t('trendsStatsTitle')}</span>
      <div className="distance-table-wrap">
        <table className="distance-table trends-stats-table" aria-label={t('a11ySessionStats')}>
          <thead>
            <tr>
              <th className="dt__h dt__h--club trends-stats-table__sticky" />
              {cols.map((c) => <th key={c.key} className="dt__h dt__h--num">{c.hd}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr className="dt__row">
              <td className="dt__d dt__d--club trends-stats-table__sticky">{t('colAvg')}</td>
              {cols.map((c) => <td key={c.key} className="dt__d dt__d--primary">{c.fmt(c.m.avg)}</td>)}
            </tr>
            <tr className="dt__row">
              <td className="dt__d dt__d--club trends-stats-table__sticky">{t('colMedian')}</td>
              {cols.map((c) => <td key={c.key} className="dt__d">{c.fmt(c.m.med)}</td>)}
            </tr>
            {showTrend && (
              <tr className="dt__row">
                <td className="dt__d dt__d--club trends-stats-table__sticky">{t('trendsTrendRow')}</td>
                {cols.map((c) => (
                  <td key={c.key} className="dt__d"><TrendIndicator value={c.m.trend} /></td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Box plots ─────────────────────────────────────────────────────────────────

function CarryBoxPlot({ stats }: { stats: BoxStats }) {
  const { t } = useLanguage();
  const theme = useThemeColors();
  const W = 120, H = 180, PL = 30, PR = 8, PT = 10, PB = 14;
  const CW = W - PL - PR, CH = H - PT - PB;
  const span = Math.max(stats.max - stats.min, 1);
  const toY = (v: number) => PT + CH - ((v - stats.min) / span) * CH;
  const bx = PL + CW * 0.2, bw = CW * 0.6;
  const yQ1 = toY(stats.q1), yQ3 = toY(stats.q3), yMed = toY(stats.median);
  const yMin = toY(stats.min), yMax = toY(stats.max);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="trends-box-svg" aria-label={t('a11yCarryBoxPlot')}>
      {[stats.min, stats.q1, stats.median, stats.q3, stats.max].map((v, i) => (
        <text key={i} x={PL - 3} y={toY(v) + 3} textAnchor="end" fontSize="7"
          fill="rgba(245,240,230,0.45)" fontFamily="inherit">{Math.round(v)}</text>
      ))}
      <line x1={bx + bw / 2} y1={yMin} x2={bx + bw / 2} y2={yQ1}
        stroke={theme.goldA(0.4)} strokeWidth="1.5" />
      <line x1={bx + bw / 2} y1={yQ3} x2={bx + bw / 2} y2={yMax}
        stroke={theme.goldA(0.4)} strokeWidth="1.5" />
      <line x1={bx + bw * 0.28} y1={yMin} x2={bx + bw * 0.72} y2={yMin}
        stroke={theme.goldA(0.55)} strokeWidth="1.5" />
      <line x1={bx + bw * 0.28} y1={yMax} x2={bx + bw * 0.72} y2={yMax}
        stroke={theme.goldA(0.55)} strokeWidth="1.5" />
      <rect x={bx} y={yQ3} width={bw} height={Math.max(yQ1 - yQ3, 1)}
        fill={theme.goldA(0.1)} stroke={theme.goldA(0.45)} strokeWidth="1.25" rx="2" />
      <line x1={bx} y1={yMed} x2={bx + bw} y2={yMed}
        stroke={theme.gold} strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function DeviationBoxPlot({ stats, distUnit }: { stats: BoxStats; distUnit: DistanceUnit }) {
  const { t } = useLanguage();
  const theme = useThemeColors();
  const unit = getDistanceUnit(distUnit);
  const W = 220, H = 84, PL = 22, PR = 22, PT = 18, PB = 22;
  const CW = W - PL - PR, CH = H - PT - PB;
  const absMax = Math.max(Math.abs(stats.min), Math.abs(stats.max), 2);
  const toX = (v: number) => PL + CW / 2 + (v / absMax) * (CW / 2);
  const by = PT, bh = CH;
  const xQ1 = toX(stats.q1), xQ3 = toX(stats.q3), xMed = toX(stats.median);
  const xMin = toX(stats.min), xMax = toX(stats.max);
  const cx = toX(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="trends-box-svg" aria-label={t('a11yDeviationBoxPlot')}>
      <line x1={cx} y1={PT - 4} x2={cx} y2={PT + CH + 2}
        stroke="rgba(245,240,230,0.2)" strokeWidth="0.75" strokeDasharray="3 2" />
      <line x1={PL} y1={PT + CH} x2={W - PR} y2={PT + CH}
        stroke="rgba(245,240,230,0.15)" strokeWidth="0.75" />
      <text x={PL} y={H - 5} textAnchor="middle" fontSize="7" fill="rgba(245,240,230,0.5)" fontFamily="inherit">L</text>
      <text x={cx}  y={H - 5} textAnchor="middle" fontSize="7" fill="rgba(245,240,230,0.35)" fontFamily="inherit">0</text>
      <text x={W - PR} y={H - 5} textAnchor="middle" fontSize="7" fill="rgba(245,240,230,0.5)" fontFamily="inherit">R</text>
      <text x={xMin} y={PT - 3} textAnchor="middle" fontSize="6.5" fill="rgba(245,240,230,0.4)" fontFamily="inherit">
        {Math.abs(stats.min).toFixed(1)}
      </text>
      <text x={xMax} y={PT - 3} textAnchor="middle" fontSize="6.5" fill="rgba(245,240,230,0.4)" fontFamily="inherit">
        {Math.abs(stats.max).toFixed(1)}
      </text>
      <line x1={xMin} y1={by + bh / 2} x2={xQ1} y2={by + bh / 2}
        stroke={theme.goldA(0.4)} strokeWidth="1.5" />
      <line x1={xQ3} y1={by + bh / 2} x2={xMax} y2={by + bh / 2}
        stroke={theme.goldA(0.4)} strokeWidth="1.5" />
      <line x1={xMin} y1={by + bh * 0.25} x2={xMin} y2={by + bh * 0.75}
        stroke={theme.goldA(0.55)} strokeWidth="1.5" />
      <line x1={xMax} y1={by + bh * 0.25} x2={xMax} y2={by + bh * 0.75}
        stroke={theme.goldA(0.55)} strokeWidth="1.5" />
      <rect x={Math.min(xQ1, xQ3)} y={by} width={Math.max(Math.abs(xQ3 - xQ1), 1)} height={bh}
        fill={theme.goldA(0.1)} stroke={theme.goldA(0.45)} strokeWidth="1.25" rx="2" />
      <line x1={xMed} y1={by} x2={xMed} y2={by + bh}
        stroke={theme.gold} strokeWidth="2.5" strokeLinecap="round" />
      <text x={xMed} y={by + bh / 2 + 3} textAnchor="middle" fontSize="6.5"
        fill={theme.gold} fontFamily="inherit">
        {stats.median >= 0 ? '+' : ''}{stats.median.toFixed(1)}
      </text>
      <text x={W / 2} y={H - 13} textAnchor="middle" fontSize="6" fill="rgba(245,240,230,0.28)" fontFamily="inherit">
        {unit}
      </text>
    </svg>
  );
}

// ── Club grouped deviation box plot ───────────────────────────────────────────

function ClubDeviationBoxPlot({
  shots, clubColors, distUnit,
}: { shots: Shot[]; clubColors: Record<string, string>; distUnit: DistanceUnit }) {
  const theme = useThemeColors();
  const unit = getDistanceUnit(distUnit);

  const entries = useMemo(() => {
    const byClub: Record<string, number[]> = {};
    for (const s of shots) {
      if (s.carry_side_yards != null && Number.isFinite(s.carry_side_yards)) {
        const v = convertDistanceFromYards(s.carry_side_yards, distUnit);
        (byClub[s.club] ??= []).push(v);
      }
    }
    return Object.entries(byClub)
      .map(([club, vals]) => ({ club, stats: computeBoxStats(vals) }))
      .filter((e): e is { club: string; stats: BoxStats } => e.stats !== null);
  }, [shots, distUnit]);

  if (entries.length === 0) return null;

  const W = 220;
  const rowH = 22;
  const PL = 40, PR = 8, PT = 14, PB = 18;
  const H = PT + entries.length * rowH + PB;
  const CW = W - PL - PR;

  const allVals = entries.flatMap(({ stats: s }) => [s.min, s.max]);
  const absMax = Math.max(Math.abs(Math.min(...allVals)), Math.abs(Math.max(...allVals)), 2);
  const cx0 = PL + CW / 2;
  const toX = (v: number) => cx0 + (v / absMax) * (CW / 2);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="trends-box-svg">
      {/* axis labels */}
      <text x={PL} y={PT - 4} textAnchor="middle" fontSize="6" fill="rgba(245,240,230,0.4)" fontFamily="inherit">L</text>
      <text x={PL + CW} y={PT - 4} textAnchor="middle" fontSize="6" fill="rgba(245,240,230,0.4)" fontFamily="inherit">R</text>
      <text x={cx0} y={PT - 4} textAnchor="middle" fontSize="6" fill="rgba(245,240,230,0.3)" fontFamily="inherit">0</text>
      {/* zero center line */}
      <line x1={cx0} y1={PT - 2} x2={cx0} y2={PT + entries.length * rowH} stroke="rgba(245,240,230,0.15)" strokeWidth="0.75" />

      {entries.map(({ club, stats: s }, i) => {
        const color = clubColors[club] ?? theme.goldA(0.9);
        const cy = PT + i * rowH + rowH / 2;
        const bh = Math.max(rowH * 0.52, 7);
        const q1x = toX(s.q1), q3x = toX(s.q3), medx = toX(s.median);
        const minx = toX(s.min), maxx = toX(s.max);
        return (
          <g key={club}>
            {/* whiskers */}
            <line x1={minx} y1={cy} x2={q1x} y2={cy} stroke={color} strokeWidth="1" opacity={0.45} strokeDasharray="2 1.5" />
            <line x1={q3x} y1={cy} x2={maxx} y2={cy} stroke={color} strokeWidth="1" opacity={0.45} strokeDasharray="2 1.5" />
            <line x1={minx} y1={cy - bh * 0.38} x2={minx} y2={cy + bh * 0.38} stroke={color} strokeWidth="1" opacity={0.6} />
            <line x1={maxx} y1={cy - bh * 0.38} x2={maxx} y2={cy + bh * 0.38} stroke={color} strokeWidth="1" opacity={0.6} />
            {/* IQR box */}
            <rect x={Math.min(q1x, q3x)} y={cy - bh / 2}
              width={Math.max(Math.abs(q3x - q1x), 1)} height={bh}
              fill={`${color}22`} stroke={color} strokeWidth="1.25" strokeOpacity={0.55} rx="1.5" />
            {/* median */}
            <line x1={medx} y1={cy - bh / 2} x2={medx} y2={cy + bh / 2} stroke={color} strokeWidth="1.75" opacity={0.95} />
            {/* club label */}
            <text x={PL - 4} y={cy + 3} textAnchor="end" fontSize="6.5" fill={color} fontFamily="inherit" opacity={0.85}>
              {CLUB_LABEL[club] ?? club}
            </text>
          </g>
        );
      })}
      <text x={cx0} y={H - 3} textAnchor="middle" fontSize="6" fill="rgba(245,240,230,0.28)" fontFamily="inherit">
        {unit}
      </text>
    </svg>
  );
}

// ── Club grouped carry box plot ────────────────────────────────────────────────

function ClubCarryBoxPlot({
  shots, clubColors, distUnit,
}: { shots: Shot[]; clubColors: Record<string, string>; distUnit: DistanceUnit }) {
  const theme = useThemeColors();

  const entries = useMemo(() => {
    const byClub: Record<string, number[]> = {};
    for (const s of shots) {
      const v = carryVal(s, distUnit);
      if (v > 0) {
        (byClub[s.club] ??= []).push(v);
      }
    }
    return Object.entries(byClub)
      .map(([club, vals]) => ({ club, stats: computeBoxStats(vals) }))
      .filter((e): e is { club: string; stats: BoxStats } => e.stats !== null);
  }, [shots, distUnit]);

  if (entries.length === 0) return null;

  const W = 220, H = 180;
  const PL = 28, PR = 8, PT = 12, PB = 20;
  const CW = W - PL - PR;
  const CH = H - PT - PB;
  const allVals = entries.flatMap(({ stats: s }) => [s.min, s.max]);
  const minV = Math.min(...allVals), maxV = Math.max(...allVals);
  const span = maxV - minV || 1;
  const toY = (v: number) => PT + CH - ((v - minV) / span) * CH;

  const colW = CW / entries.length;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="trends-box-svg">
      {[0, 0.5, 1].map((f) => {
        const y = PT + f * CH;
        return (
          <g key={f}>
            <line x1={PL} y1={y} x2={PL + CW} y2={y} stroke="rgba(245,240,230,0.12)" strokeWidth="0.75" />
            <text x={PL - 3} y={y + 3} textAnchor="end" fontSize="7" fill="rgba(245,240,230,0.45)" fontFamily="inherit">
              {Math.round(maxV - f * span)}
            </text>
          </g>
        );
      })}
      {entries.map(({ club, stats: s }, i) => {
        const color = clubColors[club] ?? theme.goldA(0.9);
        const cx = PL + i * colW + colW / 2;
        const bw = Math.max(colW * 0.45, 8);
        const q1y = toY(s.q1), q3y = toY(s.q3), medy = toY(s.median);
        const miny = toY(s.min), maxy = toY(s.max);
        return (
          <g key={club}>
            {/* whiskers */}
            <line x1={cx} y1={miny} x2={cx} y2={q3y} stroke={color} strokeWidth="1" opacity={0.5} strokeDasharray="2 1.5" />
            <line x1={cx} y1={q1y} x2={cx} y2={maxy} stroke={color} strokeWidth="1" opacity={0.5} strokeDasharray="2 1.5" />
            <line x1={cx - bw * 0.35} y1={miny} x2={cx + bw * 0.35} y2={miny} stroke={color} strokeWidth="1" opacity={0.6} />
            <line x1={cx - bw * 0.35} y1={maxy} x2={cx + bw * 0.35} y2={maxy} stroke={color} strokeWidth="1" opacity={0.6} />
            {/* IQR box */}
            <rect x={cx - bw / 2} y={q3y} width={bw} height={Math.max(q1y - q3y, 1)}
              fill={`${color}22`} stroke={color} strokeWidth="1.25" strokeOpacity={0.55} rx="1.5" />
            {/* median */}
            <line x1={cx - bw / 2} y1={medy} x2={cx + bw / 2} y2={medy} stroke={color} strokeWidth="1.75" opacity={0.95} />
            {/* label */}
            <text x={cx} y={PT + CH + 12} textAnchor="middle" fontSize="6.5" fill={color} fontFamily="inherit" opacity={0.85}>
              {CLUB_LABEL[club] ?? club}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Trends view ───────────────────────────────────────────────────────────────

function TrendsView({ shots, distUnit }: { shots: Shot[]; distUnit: DistanceUnit }) {
  const { t } = useLanguage();
  const theme = useThemeColors();
  const unit = getDistanceUnit(distUnit);

  const [selectedGroup, setSelectedGroup] = useState<ClubGroupKey | 'all'>('all');

  const groupedShots = useMemo(
    () => getGroupShots(shots, selectedGroup),
    [shots, selectedGroup],
  );

  const clubs = useMemo(() => getUniqueClubs(groupedShots), [groupedShots]);
  const clubColors = useMemo(
    () => getClubColors(clubs, theme.isColorBlind),
    [clubs, theme.isColorBlind],
  );

  const summary = useMemo(
    () => computeTrendsSummary(groupedShots, distUnit),
    [groupedShots, distUnit],
  );

  const carryBoxStats = useMemo(() => {
    const vals = groupedShots.map((s) => carryVal(s, distUnit)).filter((v) => v > 0);
    return computeBoxStats(vals);
  }, [groupedShots, distUnit]);

  const devBoxStats = useMemo(() => {
    const vals = groupedShots
      .map((s) => s.carry_side_yards != null
        ? convertDistanceFromYards(s.carry_side_yards, distUnit)
        : null)
      .filter((v): v is number => v != null && Number.isFinite(v));
    return computeBoxStats(vals);
  }, [groupedShots, distUnit]);

  const carryTrendPts = useMemo<TrendPoint[]>(
    () => groupedShots
      .map((s, i) => ({ idx: i, value: carryVal(s, distUnit), club: s.club }))
      .filter((p) => p.value > 0),
    [groupedShots, distUnit],
  );

  if (shots.length < 3) {
    return (
      <div className="trends-view stats-analysis--empty">
        <p>{t('trendsMinShots')}</p>
      </div>
    );
  }

  return (
    <div className="trends-view">
      <ClubSelector shots={shots} selectedGroup={selectedGroup} onSelect={setSelectedGroup} />

      {groupedShots.length < 3 ? (
        <div className="stats-analysis--empty">
          <p>{t('trendsMinShots')}</p>
        </div>
      ) : (
        <>
          {summary && <StatsSummaryTable summary={summary} distUnit={distUnit} showTrend={selectedGroup !== 'all'} />}

          <div className="trends-box-row">
            {selectedGroup === 'all' && clubs.length > 1 ? (
              <div className="analysis-card trends-box-card">
                <span className="analysis-card__title">{t('trendsBoxCarryTitle')} ({unit})</span>
                <ClubCarryBoxPlot shots={groupedShots} clubColors={clubColors} distUnit={distUnit} />
              </div>
            ) : carryBoxStats ? (
              <div className="analysis-card trends-box-card">
                <span className="analysis-card__title">{t('trendsBoxCarryTitle')} ({unit})</span>
                <CarryBoxPlot stats={carryBoxStats} />
              </div>
            ) : null}
            <div className="analysis-card trends-box-card">
              <span className="analysis-card__title">{t('trendsBoxDevTitle')}</span>
              {selectedGroup === 'all' && clubs.length > 1
                ? <ClubDeviationBoxPlot shots={groupedShots} clubColors={clubColors} distUnit={distUnit} />
                : devBoxStats
                  ? <DeviationBoxPlot stats={devBoxStats} distUnit={distUnit} />
                  : <p className="chart-note">{t('trendsNoDeviation')}</p>
              }
            </div>
          </div>

          {carryTrendPts.length >= 2 && (
            <div className="analysis-card trend-card">
              <span className="analysis-card__title">{t('trendsCarry')} - {unit}</span>
              <TrendLineChart points={carryTrendPts} clubColors={clubColors} />
              <p className="chart-note">{t('trendsMaNote')}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Icons ─────────────────────────────────────────────────────────────────────

const FilterIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>
);

const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

// ── Main Component ─────────────────────────────────────────────────────────────

export function StatsView({ shots, onClearSession }: StatsViewProps) {
  const [subView, setSubView] = useState<SubView>('home');
  const [filterOpen, setFilterOpen] = useState(false);

  const {
    sessionList,
    selectedSessionId,
    setSelectedSessionId,
    selectedClub,
    setSelectedClub,
    activeShots,
    isHistorical,
    activeSession,
    availableClubs,
    clubCounts,
    filteredShots,
    stats,
    loadingSession,
  } = useStatsData(shots);

  const { speedUnit, distanceUnit } = useUnitPreference();
  const { t } = useLanguage();
  const distUnit = distanceUnit as DistanceUnit;
  const speedLabel = getSpeedUnit(speedUnit);
  const distLabel = getDistanceUnit(distUnit);

  const hasActiveFilters = selectedClub !== null || isHistorical;
  const showClubBars = selectedClub === null && availableClubs.length >= 2;

  if (shots.length === 0 && !isHistorical) {
    return (
      <div className="stats-view stats-view--empty">
        <p>{t('noShots')}</p>
      </div>
    );
  }

  return (
    <div className="stats-view">

      {/* ── Filter bar ── */}
      <div className="stats-filter-bar">
        <div className="stats-filter-bar__context">
          <span className="stats-filter-bar__count">{filteredShots.length}</span>
          <span className="stats-filter-bar__label">
            {filteredShots.length === 1 ? t('shotSingular') : t('shotCount')}
            {selectedClub ? ` · ${selectedClub.toUpperCase()}` : ''}
            {activeSession ? ` · ${formatDate(activeSession.started_at)}` : ''}
          </span>
        </div>
        <button
          className={`stats-filter-btn${hasActiveFilters ? ' stats-filter-btn--active' : ''}`}
          onClick={() => setFilterOpen((o) => !o)}
          aria-expanded={filterOpen}
          aria-label={t('a11yToggleFilters')}
        >
          <FilterIcon />
          <span>{t('filtersLabel')}</span>
          <ChevronIcon open={filterOpen} />
          {hasActiveFilters && (
            <span className="stats-filter-btn__badge">
              {(selectedClub ? 1 : 0) + (isHistorical ? 1 : 0)}
            </span>
          )}
        </button>
      </div>

      {/* ── Filter panel ── */}
      {filterOpen && (
        <>
          <div className="stats-filter-backdrop" onClick={() => setFilterOpen(false)} aria-hidden="true" />
          <div className="stats-filter-panel" role="dialog" aria-label={t('filtersLabel')}>
            <div className="stats-filter-section">
              <span className="stats-filter-section__title">{t('filterSession')}</span>
              <div className="stats-filter-scroll-wrap">
                <div className="stats-filter-chips">
                  <button
                    className={`stats-filter-chip${selectedSessionId === null ? ' stats-filter-chip--active' : ''}`}
                    onClick={() => { setSelectedSessionId(null); setSelectedClub(null); }}
                  >
                    {t('currentSession')} ({shots.length})
                  </button>
                  {sessionList.map((s) => (
                    <button key={s.id}
                      className={`stats-filter-chip${selectedSessionId === s.id ? ' stats-filter-chip--active' : ''}`}
                      onClick={() => setSelectedSessionId(s.id)}>
                      {formatDate(s.started_at)} ({s.shot_count})
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="stats-filter-divider" />

            <div className="stats-filter-section">
              <span className="stats-filter-section__title">{t('clubLabel')}</span>
              <div className="stats-filter-scroll-wrap">
                <div className="stats-filter-chips">
                  <button
                    className={`stats-filter-chip${selectedClub === null ? ' stats-filter-chip--active' : ''}`}
                    onClick={() => setSelectedClub(null)}
                  >
                    {t('all')} ({activeShots.length})
                  </button>
                  {availableClubs.map((club) => (
                    <button key={club}
                      className={`stats-filter-chip${selectedClub === club ? ' stats-filter-chip--active' : ''}`}
                      onClick={() => setSelectedClub(club)}>
                      {club.toUpperCase()} ({clubCounts[club] || 0})
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button className="stats-filter-done" onClick={() => setFilterOpen(false)}>{t('doneBtn')}</button>
          </div>
        </>
      )}

      {/* ── Sub-navigation ── */}
      <div className="stats-view-tabs" role="tablist" aria-label={t('statsTabsLabel')}>
        {(['home', 'clubs', 'trends', 'coaching', 'shots'] as SubView[]).map((v) => (
          <button key={v} role="tab" aria-selected={subView === v}
            className={`stats-view-tab${subView === v ? ' stats-view-tab--active' : ''}`}
            onClick={() => setSubView(v)}>
            {v === 'home' ? t('statsTabHome') : v === 'clubs' ? t('statsTabClubs') : v === 'trends' ? t('statsTabTrends') : v === 'coaching' ? t('statsTabCoaching') : t('statsTabShots')}
          </button>
        ))}
      </div>

      {/* ── Coaching sub-view ── */}
      {subView === 'coaching' && (
        <StatsAnalysis shots={filteredShots} allShots={activeShots} distUnit={distUnit} />
      )}

      {/* ── Shots sub-view ── */}
      {subView === 'shots' && (
        <ShotList shots={filteredShots} />
      )}

      {/* ── Clubs sub-view ── */}
      {subView === 'clubs' && (
        loadingSession ? (
          <div className="stats-loading">{t('loadingSession')}</div>
        ) : (
          <ClubsView shots={filteredShots.length > 0 ? filteredShots : activeShots} distUnit={distUnit} />
        )
      )}

      {/* ── Trends sub-view ── */}
      {subView === 'trends' && (
        loadingSession ? (
          <div className="stats-loading">{t('loadingSession')}</div>
        ) : (
          <TrendsView shots={filteredShots} distUnit={distUnit} />
        )
      )}

      {/* ── Home sub-view ── */}
      {subView === 'home' && (loadingSession ? (
        <div className="stats-loading">{t('loadingSession')}</div>
      ) : (
        <div className="stats-dashboard">
          {/* Hero KPIs */}
          <div className="stats-hero-row">
            <div className="stat-card stat-card--hero">
              <span className="stat-card__value">{formatDistance(stats.avg_carry_est, distUnit, 0)}</span>
              <span className="stat-card__unit">{distLabel}</span>
              <span className="stat-card__label">{t('avgCarry')}</span>
            </div>
            <div className="stat-card stat-card--hero">
              <span className="stat-card__value">{formatSpeed(stats.avg_ball_speed, speedUnit, 1)}</span>
              <span className="stat-card__unit">{speedLabel}</span>
              <span className="stat-card__label">{t('avgBall')}</span>
            </div>
            {stats.avg_club_speed != null && (
              <div className="stat-card stat-card--hero">
                <span className="stat-card__value">{formatSpeed(stats.avg_club_speed, speedUnit, 1)}</span>
                <span className="stat-card__unit">{speedLabel}</span>
                <span className="stat-card__label">{t('avgClub')}</span>
              </div>
            )}
          </div>

          {/* Chart row - full width, no sidebar */}
          <div className="stats-chart-row stats-chart-row--full">
            {showClubBars ? (
              <div className="stat-card stat-card--chart">
                <span className="stat-card__chart-title">{t('avgCarryByClub')}</span>
                <ClubBars shots={filteredShots} clubs={availableClubs} distanceUnit={distUnit} />
              </div>
            ) : (
              filteredShots.length >= 3 && (
                <div className="stat-card stat-card--chart">
                  <span className="stat-card__chart-title">{t('carryDistribution')}</span>
                  <div className="carry-histogram">
                    <CarryHistogram shots={filteredShots} distanceUnit={distUnit} />
                  </div>
                </div>
              )
            )}
          </div>

          {/* Secondary metrics - spreads evenly */}
          <div className="stats-secondary-row">
            {stats.avg_smash_factor != null && (
              <div className="stat-card stat-card--small">
                <span className="stat-card__value">{stats.avg_smash_factor.toFixed(2)}</span>
                <span className="stat-card__label">{t('avgSmash')}</span>
              </div>
            )}
            {stats.avg_launch_angle != null && (
              <div className="stat-card stat-card--small">
                <span className="stat-card__value">{stats.avg_launch_angle.toFixed(1)}°</span>
                <span className="stat-card__label">{t('statAvgLaunch')}</span>
              </div>
            )}
            {stats.avg_spin_rpm != null && (
              <div className="stat-card stat-card--small">
                <span className="stat-card__value">{Math.round(stats.avg_spin_rpm).toLocaleString()}</span>
                <span className="stat-card__unit">rpm</span>
                <span className="stat-card__label">{t('statAvgSpin')}</span>
              </div>
            )}
            {stats.std_dev_carry != null && stats.shot_count > 2 && (
              <div className="stat-card stat-card--small">
                <span className="stat-card__value">±{formatDistance(stats.std_dev_carry, distUnit, 0)}</span>
                <span className="stat-card__unit">{distLabel}</span>
                <span className="stat-card__label">{t('statConsistency')}</span>
              </div>
            )}
            <div className="stat-card stat-card--small">
              <span className="stat-card__value">{stats.shot_count}</span>
              <span className="stat-card__label">{t('shots')}</span>
            </div>
          </div>
        </div>
      ))}

      {!isHistorical && subView === 'home' && (
        <button className="clear-button" onClick={onClearSession} aria-label={t('clearSession')}>
          {t('clearSession')}
        </button>
      )}
    </div>
  );
}
