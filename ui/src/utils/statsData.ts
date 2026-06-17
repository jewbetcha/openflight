// Pure statistics helpers for the Stats view. Extracted from StatsView.tsx so
// the computation is unit-testable in isolation and the component file stays
// focused on rendering. No React, no DOM - pure functions only.
import type { Shot } from '../types/shot';
import { convertDistanceFromYards, type DistanceUnit } from './units';

/** Moving-average window used for trend smoothing. */
export const MA_WINDOW = 5;

// ── Club colours ──────────────────────────────────────────────────────────────

export const CLUB_PALETTE = [
  '#34d399', '#60a5fa', '#a78bfa', '#f472b6',
  '#fb923c', '#fbbf24', '#22d3ee', '#4ade80',
  '#f87171', '#c084fc', '#38bdf8', '#a3e635',
  '#f97316', '#e879f9',
];

// Colorblind-safe palette: avoids adjacent red/green, uses blue/orange/purple/yellow anchors
export const CB_CLUB_PALETTE = [
  '#4E8CF5', '#F28C00', '#9B72F5', '#E8B830',
  '#22d3ee', '#f472b6', '#60a5fa', '#e879f9',
  '#38bdf8', '#fb923c', '#c084fc', '#818cf8',
  '#fdba74', '#f472b6',
];

export function getClubColors(clubs: string[], colorBlind = false): Record<string, string> {
  const palette = colorBlind ? CB_CLUB_PALETTE : CLUB_PALETTE;
  return Object.fromEntries(clubs.map((c, i) => [c, palette[i % palette.length]]));
}

// ── Math helpers ──────────────────────────────────────────────────────────────

export function medianOf(arr: number[]): number {
  if (arr.length === 0) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[m - 1] + s[m]) / 2 : s[m];
}

export function carryVal(shot: Shot, distUnit: DistanceUnit): number {
  return convertDistanceFromYards(
    shot.carry_spin_adjusted ?? shot.estimated_carry_yards,
    distUnit,
  );
}

export function stdDev(vals: number[]): number {
  if (vals.length < 2) return 0;
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  return Math.sqrt(vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length);
}

export function formatDate(iso: string | null): string {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ── Box-plot utilities ────────────────────────────────────────────────────────

export interface BoxStats {
  min: number; q1: number; median: number; q3: number; max: number;
}

export function computeBoxStats(vals: number[]): BoxStats | null {
  const sorted = [...vals].filter(Number.isFinite).sort((a, b) => a - b);
  if (sorted.length < 3) return null;
  const n = sorted.length;
  const lerp = (f: number) => {
    const pos = f * (n - 1);
    const lo = Math.floor(pos);
    return sorted[lo] + (sorted[Math.ceil(pos)] - sorted[lo]) * (pos - lo);
  };
  return { min: sorted[0], q1: lerp(0.25), median: lerp(0.5), q3: lerp(0.75), max: sorted[n - 1] };
}

export interface MetricStats { avg: number | null; med: number | null; trend: number | null; }
export interface TrendsSummary {
  carry: MetricStats; total: MetricStats; apex: MetricStats;
  ball: MetricStats; club: MetricStats; smash: MetricStats;
  launch: MetricStats; spin: MetricStats; dev: MetricStats; path: MetricStats;
}

export function computeTrendsSummary(shots: Shot[], distUnit: DistanceUnit): TrendsSummary | null {
  if (shots.length < 3) return null;
  const pick = (fn: (s: Shot) => number | null | undefined): number[] =>
    shots.map(fn).filter((v): v is number => v != null && Number.isFinite(v as number));
  const avg = (a: number[]) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
  const med = (a: number[]): number | null => {
    if (!a.length) return null;
    const s = [...a].sort((x, y) => x - y);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const trendPct = (a: number[]): number | null => {
    if (a.length < 6) return null;
    const seg = Math.floor(a.length / 3);
    const early = avg(a.slice(0, seg));
    const late = avg(a.slice(-seg));
    if (!early || !late) return null;
    return ((late - early) / Math.abs(early)) * 100;
  };
  const stat = (a: number[]): MetricStats => ({ avg: avg(a), med: med(a), trend: trendPct(a) });

  return {
    carry:  stat(pick((s) => convertDistanceFromYards(s.carry_spin_adjusted ?? s.estimated_carry_yards, distUnit))),
    total:  stat(pick((s) => s.total_distance_yards != null ? convertDistanceFromYards(s.total_distance_yards, distUnit) : null)),
    apex:   stat(pick((s) => s.apex_height_yards != null ? convertDistanceFromYards(s.apex_height_yards, distUnit) : null)),
    ball:   stat(pick((s) => s.ball_speed_mph)),
    club:   stat(pick((s) => s.club_speed_mph)),
    smash:  stat(pick((s) => s.smash_factor)),
    launch: stat(pick((s) => s.launch_angle_vertical)),
    spin:   stat(pick((s) => s.spin_rpm)),
    dev:    stat(pick((s) => s.carry_side_yards != null ? convertDistanceFromYards(s.carry_side_yards, distUnit) : null)),
    path:   stat(pick((s) => s.club_path_deg)),
  };
}

// ── Club group selector ───────────────────────────────────────────────────────

export const TREND_CLUB_GROUPS = [
  { key: 'driver' as const, label: 'Driver', ids: ['driver'] as string[] },
  { key: 'wood'   as const, label: '3W',     ids: ['3-wood', '5-wood', '7-wood'] as string[] },
  { key: 'hybrid' as const, label: 'Hybrid', ids: ['3-hybrid', '5-hybrid', '7-hybrid', '9-hybrid'] as string[] },
  { key: 'iron'   as const, label: 'Irons',  ids: ['2-iron', '3-iron', '4-iron', '5-iron', '6-iron', '7-iron', '8-iron', '9-iron'] as string[] },
  { key: 'wedge'  as const, label: 'Wedge',  ids: ['pw', 'gw', 'sw', 'lw'] as string[] },
];

export type ClubGroupKey = 'driver' | 'wood' | 'hybrid' | 'iron' | 'wedge';

export function getGroupShots(shots: Shot[], group: ClubGroupKey | 'all'): Shot[] {
  if (group === 'all') return shots;
  const def = TREND_CLUB_GROUPS.find((g) => g.key === group);
  return def ? shots.filter((s) => def.ids.includes(s.club)) : shots;
}
