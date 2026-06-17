import { convertDistanceFromYards, type DistanceUnit } from './units';
import type { Shot } from '../types/shot';
import { type TKey } from '../i18n/translations';
import {
  getClubCategory,
  getClubTarget,
  FAULT_WINDOWS,
  FAULT_DRILLS,
  CHAIN_TEMPLATES,
  GAP_CONVERSIONS,
  type ClubCategory,
  type DrillMapping,
} from './clubThresholds';

type TFn = (key: TKey) => string;
type TiFn = (key: TKey, vars?: Record<string, string | number>) => string;

// ── Tour benchmarks (PGA Tour averages by club) ────────────────────────────────
// Sources: TrackMan industry averages, Shot Scope data

export interface ClubBenchmark {
  smash: number;
  launch: number;  // degrees optimal
  spin: number;    // rpm optimal
  carry: number;   // yards PGA Tour avg
  yardsPerSmashPoint: number; // carry yards gained per 0.01 smash improvement
}

const BENCHMARKS: Record<string, ClubBenchmark> = {
  driver:   { smash: 1.48, launch: 12.0, spin: 2700,  carry: 275, yardsPerSmashPoint: 3.8 },
  '3-wood': { smash: 1.44, launch: 12.6, spin: 3655,  carry: 243, yardsPerSmashPoint: 3.2 },
  '5-wood': { smash: 1.43, launch: 14.0, spin: 4350,  carry: 230, yardsPerSmashPoint: 2.9 },
  '3-iron': { smash: 1.41, launch: 14.1, spin: 4630,  carry: 212, yardsPerSmashPoint: 2.5 },
  '4-iron': { smash: 1.40, launch: 14.7, spin: 5030,  carry: 203, yardsPerSmashPoint: 2.3 },
  '5-iron': { smash: 1.39, launch: 15.1, spin: 5500,  carry: 194, yardsPerSmashPoint: 2.1 },
  '6-iron': { smash: 1.38, launch: 17.1, spin: 6200,  carry: 183, yardsPerSmashPoint: 1.9 },
  '7-iron': { smash: 1.38, launch: 17.2, spin: 7100,  carry: 172, yardsPerSmashPoint: 1.8 },
  '8-iron': { smash: 1.36, launch: 18.1, spin: 8000,  carry: 160, yardsPerSmashPoint: 1.6 },
  '9-iron': { smash: 1.35, launch: 19.5, spin: 8750,  carry: 148, yardsPerSmashPoint: 1.4 },
  pw:       { smash: 1.33, launch: 21.4, spin: 9300,  carry: 136, yardsPerSmashPoint: 1.2 },
  gw:       { smash: 1.30, launch: 24.0, spin: 9800,  carry: 120, yardsPerSmashPoint: 1.0 },
  sw:       { smash: 1.27, launch: 26.0, spin: 10200, carry: 100, yardsPerSmashPoint: 0.9 },
  lw:       { smash: 1.24, launch: 28.0, spin: 10500, carry: 85,  yardsPerSmashPoint: 0.8 },
};

export function getBenchmark(club: string): ClubBenchmark | null {
  const key = club.toLowerCase().replace(/[\s_]+/g, '-');
  return BENCHMARKS[key] ?? null;
}

// ── Math helpers ──────────────────────────────────────────────────────────────

export function mean(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

export function stdDev(arr: number[]): number {
  if (arr.length < 2) return 0;
  const m = mean(arr);
  return Math.sqrt(arr.reduce((sum, x) => sum + (x - m) ** 2, 0) / (arr.length - 1));
}

function dominantClub(shots: Shot[]): string {
  const counts: Record<string, number> = {};
  shots.forEach((s) => { counts[s.club] = (counts[s.club] || 0) + 1; });
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'driver';
}

// ── Strike Quality ────────────────────────────────────────────────────────────

export interface StrikeQuality {
  score: number;         // 0–100
  label: string;         // 'Elite' | 'Solid' | 'Developing' | 'Opportunity'
  smashAvg: number;
  smashTarget: number;
  smashGap: number;      // positive = above target (good)
  distanceLostYds: number; // estimated carry yards leaking
  consistencyPct: number;  // coefficient of variation, lower = better
}

export function computeStrikeQuality(shots: Shot[]): StrikeQuality | null {
  const smashes = shots.map((s) => s.smash_factor).filter((v): v is number => v != null);
  if (smashes.length === 0) return null;

  const club = dominantClub(shots);
  const bm = getBenchmark(club);
  const smashTarget = bm?.smash ?? 1.38;
  const yardsPerPoint = bm?.yardsPerSmashPoint ?? 2.0;

  const smashAvg = mean(smashes);
  const smashGap = smashAvg - smashTarget;  // negative = below target

  // Smash score: linear from (target - 0.08) to target → 0 to 100
  const smashFloor = smashTarget - 0.08;
  const smashScore = Math.min(100, Math.max(0,
    ((smashAvg - smashFloor) / (smashTarget - smashFloor)) * 100
  ));

  // Consistency score: CV < 3% = 100, CV > 20% = 0
  const carries = shots.map((s) => s.carry_spin_adjusted ?? s.estimated_carry_yards);
  const cv = carries.length > 1 ? stdDev(carries) / mean(carries) : 0;
  const consistScore = Math.min(100, Math.max(0, (1 - cv / 0.20) * 100));

  const score = Math.round(smashScore * 0.6 + consistScore * 0.4);
  const distanceLostYds = smashGap < 0 ? Math.round(Math.abs(smashGap) * 100 * yardsPerPoint) : 0;

  const label =
    score >= 85 ? 'Elite' :
    score >= 68 ? 'Solid' :
    score >= 50 ? 'Developing' :
    'Opportunity';

  return {
    score,
    label,
    smashAvg,
    smashTarget,
    smashGap,
    distanceLostYds,
    consistencyPct: Math.round(cv * 100),
  };
}

// ── Distance Profile ──────────────────────────────────────────────────────────

export interface DistanceProfile {
  club: string;
  count: number;
  avg: number;
  sd: number;
  reliable: number;   // avg − 1σ  (~84th percentile)
  conservative: number; // avg − 2σ (~97th percentile)
}

export function buildDistanceProfiles(
  shots: Shot[],
  distUnit: DistanceUnit,
): DistanceProfile[] {
  const byClub: Record<string, number[]> = {};
  for (const s of shots) {
    const carry = convertDistanceFromYards(
      s.carry_spin_adjusted ?? s.estimated_carry_yards,
      distUnit,
    );
    if (!byClub[s.club]) byClub[s.club] = [];
    byClub[s.club].push(carry);
  }

  return Object.entries(byClub)
    .filter(([, carries]) => carries.length >= 2)
    .map(([club, carries]) => {
      const avg = mean(carries);
      const sd = stdDev(carries);
      return {
        club,
        count: carries.length,
        avg: Math.round(avg),
        sd: Math.round(sd),
        reliable: Math.round(avg - sd),
        conservative: Math.round(avg - 2 * sd),
      };
    })
    .sort((a, b) => b.avg - a.avg);
}

// ── Insights ──────────────────────────────────────────────────────────────────

export type InsightPriority = 'high' | 'medium' | 'low';

export interface Insight {
  id: string;
  priority: InsightPriority;
  category: string;
  headline: string;
  detail: string;
  metric?: string;
  opportunity?: string;
}

export function generateInsights(shots: Shot[], distUnit: DistanceUnit, ti: TiFn = (k) => k): Insight[] {
  if (shots.length < 3) return [];

  const insights: Insight[] = [];
  const club = dominantClub(shots);
  const bm = getBenchmark(club);
  const category = getClubCategory(club);
  const thresholds = FAULT_WINDOWS[category];
  const minShots = thresholds.minShots;
  const clubLabel = club.toUpperCase();

  const smashes  = shots.map((s) => s.smash_factor).filter((v): v is number => v != null);
  const spins    = shots.map((s) => s.spin_rpm).filter((v): v is number => v != null);
  const launches = shots.map((s) => s.launch_angle_vertical).filter((v): v is number => v != null);
  const aoAs     = shots.map((s) => s.club_angle_deg).filter((v): v is number => v != null);
  const carries  = shots.map((s) =>
    convertDistanceFromYards(s.carry_spin_adjusted ?? s.estimated_carry_yards, distUnit)
  );
  const paths    = shots.map((s) => s.club_path_deg).filter((v): v is number => v != null);
  const axes     = shots.map((s) => s.spin_axis_deg).filter((v): v is number => v != null);

  const avgSmash  = smashes.length  >= minShots ? mean(smashes)  : null;
  const avgSpin   = spins.length    >= minShots ? mean(spins)    : null;
  const avgLaunch = launches.length >= minShots ? mean(launches) : null;
  const avgAoA    = aoAs.length     >= minShots ? mean(aoAs)     : null;
  const avgCarry  = mean(carries);
  const sdCarry   = stdDev(carries);
  const avgPath   = paths.length    >= minShots ? mean(paths.map(Math.abs)) : null;
  const avgAxis   = axes.length     >= minShots ? mean(axes.map(Math.abs)) : null;

  const clubSpeeds  = shots.map((s) => s.club_speed_mph).filter((v): v is number => v != null);
  const avgClubSpeed = clubSpeeds.length > 0 ? mean(clubSpeeds) : GAP_CONVERSIONS.defaultClubSpeedMph;
  const clubTarget  = getClubTarget(club);

  // ── Attack angle (requires K-LD7 horizontal radar) ───────────────────────
  const aoaThreshold = thresholds.attackAngle?.steepFault;
  if (avgAoA !== null && aoaThreshold !== undefined && avgAoA < aoaThreshold) {
    // Driver only: quantify yds from per-degree config; other clubs show qualitative copy
    const aoaYds = (category === 'driver' && clubTarget?.aoa)
      ? Math.round(Math.max(0, clubTarget.aoa[0] - avgAoA) * GAP_CONVERSIONS.driverAoaYdsPerDegree)
      : 0;
    insights.push({
      id: 'attack-steep',
      priority: 'high',
      category: 'launchConditions',
      headline: ti('insightAoaSteepHead', { club: clubLabel, deg: avgAoA.toFixed(1) }),
      detail: ti('insightAoaSteepDetail'),
      opportunity: aoaYds > 0 ? ti('insightAoaSteepOpp', { yds: aoaYds }) : undefined,
    });
  }

  // ── Strike quality / smash ────────────────────────────────────────────────
  // Yardage formula: smash_gap × avg_club_speed_mph × ydsPerMphBallSpeed (defensible, tunable)
  const smashGapThreshold = thresholds.smashFactor?.lowGap ?? 0.04;
  if (avgSmash !== null && bm) {
    const smashTarget = clubTarget?.smash[0] ?? bm.smash;
    const gap = avgSmash - smashTarget;
    const yardsLost = gap < 0
      ? Math.round(Math.abs(gap) * avgClubSpeed * GAP_CONVERSIONS.ydsPerMphBallSpeed)
      : 0;

    if (gap < -smashGapThreshold) {
      insights.push({
        id: 'smash-low',
        priority: 'high',
        category: 'strikeQuality',
        headline: ti('insightSmashLowHead', { club: clubLabel, smash: avgSmash.toFixed(2), yds: yardsLost }),
        detail: ti('insightSmashLowDetail', { club: clubLabel, smash: avgSmash.toFixed(2), gap: Math.abs(gap).toFixed(2), target: smashTarget.toFixed(2), yds: yardsLost }),
        metric: avgSmash.toFixed(2),
        opportunity: ti('insightSmashLowOpp', { yds: yardsLost }),
      });
    } else if (gap >= 0) {
      insights.push({
        id: 'smash-good',
        priority: 'low',
        category: 'strikeQuality',
        headline: ti('insightSmashGoodHead', { club: clubLabel }),
        detail: ti('insightSmashGoodDetail', { smash: avgSmash.toFixed(2), target: smashTarget.toFixed(2) }),
        metric: avgSmash.toFixed(2),
      });
    }
  }

  // ── Spin rate ─────────────────────────────────────────────────────────────
  const spinHigh = thresholds.spinRate?.highFactor ?? 1.20;
  const spinLow  = thresholds.spinRate?.lowFactor;
  if (avgSpin !== null && bm) {
    const spinRatio = avgSpin / bm.spin;
    if (spinRatio > spinHigh) {
      const spinBenchmark = clubTarget?.spin[1] ?? bm.spin;
      const excessRpm = Math.round(avgSpin - spinBenchmark);
      const distLoss = Math.round(excessRpm / 500 * GAP_CONVERSIONS.driverSpinYdsPer500Rpm);
      insights.push({
        id: 'spin-high',
        priority: 'high',
        category: 'ballFlight',
        headline: ti('insightSpinHighHead', { rpm: Math.round(avgSpin).toLocaleString(), yds: distLoss }),
        detail: ti('insightSpinHighDetail', { club: clubLabel, target: bm.spin.toLocaleString(), excess: excessRpm.toLocaleString() }),
        metric: `${Math.round(avgSpin).toLocaleString()} rpm`,
        opportunity: ti('insightSpinHighOpp', { excess: excessRpm.toLocaleString() }),
      });
    } else if (spinLow !== undefined && spinRatio < spinLow && bm.spin > 5000) {
      insights.push({
        id: 'spin-low',
        priority: 'medium',
        category: 'ballFlight',
        headline: ti('insightSpinLowHead', { rpm: Math.round(avgSpin).toLocaleString() }),
        detail: ti('insightSpinLowDetail', { club: clubLabel, rpm: Math.round(avgSpin).toLocaleString(), target: bm.spin.toLocaleString() }),
        metric: `${Math.round(avgSpin).toLocaleString()} rpm`,
      });
    }
  }

  // ── Launch angle ──────────────────────────────────────────────────────────
  const launchLowGap  = thresholds.launchAngle?.lowGap  ?? 3;
  const launchHighGap = thresholds.launchAngle?.highGap ?? 4;
  if (avgLaunch !== null && bm) {
    const launchGap = avgLaunch - bm.launch;
    if (launchGap < -launchLowGap) {
      insights.push({
        id: 'launch-low',
        priority: 'medium',
        category: 'launchConditions',
        headline: ti('insightLaunchLowHead', { deg: avgLaunch.toFixed(1), gap: Math.abs(launchGap).toFixed(1) }),
        detail: ti('insightLaunchLowDetail', { club: clubLabel, target: bm.launch, deg: avgLaunch.toFixed(1) }),
        metric: `${avgLaunch.toFixed(1)}°`,
        opportunity: ti('insightLaunchLowOpp', { gap: Math.abs(launchGap).toFixed(1) }),
      });
    } else if (launchGap > launchHighGap) {
      insights.push({
        id: 'launch-high',
        priority: 'low',
        category: 'launchConditions',
        headline: ti('insightLaunchHighHead', { deg: avgLaunch.toFixed(1) }),
        detail: ti('insightLaunchHighDetail', { deg: avgLaunch.toFixed(1), target: bm.launch, club: clubLabel }),
        metric: `${avgLaunch.toFixed(1)}°`,
      });
    }
  }

  // ── Consistency ───────────────────────────────────────────────────────────
  const cvThreshold = thresholds.consistencyCV;
  const cv = sdCarry / avgCarry;
  if (sdCarry > 0 && cv > cvThreshold && shots.length >= minShots) {
    const sdLabel = Math.round(sdCarry);
    const distUnitLabel = distUnit === 'meters' ? 'm' : 'yds';
    insights.push({
      id: 'consistency',
      priority: cv > cvThreshold * 1.5 ? 'high' : 'medium',
      category: 'statConsistency',
      headline: ti('insightConsistHead', { sd: sdLabel, unit: distUnitLabel }),
      detail: ti('insightConsistDetail', { sd: sdLabel, unit: distUnitLabel, sd2: sdLabel * 2, target: Math.round(avgCarry * 0.05) }),
      metric: `±${sdLabel} ${distUnitLabel}`,
    });
  }

  // ── Club path ─────────────────────────────────────────────────────────────
  const pathFault = thresholds.clubPath?.absFault ?? 4;
  if (avgPath !== null && avgPath > pathFault) {
    insights.push({
      id: 'path',
      priority: avgPath > pathFault * 1.5 ? 'high' : 'medium',
      category: 'clubPath',
      headline: ti('insightPathHead', { deg: avgPath.toFixed(1) }),
      detail: ti('insightPathDetail', { deg: avgPath.toFixed(1) }),
      metric: `${avgPath.toFixed(1)}°`,
      opportunity: ti('insightPathOpp'),
    });
  }

  // ── Spin axis (face-to-path mismatch) ─────────────────────────────────────
  const axisFault = thresholds.spinAxis?.absFault;
  if (avgAxis !== null && axisFault !== undefined && avgAxis > axisFault) {
    // Only surface if path insight not already covering this
    if (!insights.find((i) => i.id === 'path')) {
      insights.push({
        id: 'spin-axis',
        priority: 'medium',
        category: 'clubPath',
        headline: ti('insightPathHead', { deg: avgAxis.toFixed(1) }),
        detail: ti('insightPathDetail', { deg: avgAxis.toFixed(1) }),
        metric: `${avgAxis.toFixed(1)}° axis`,
      });
    }
  }

  // Sort: high → medium → low; within same priority consistency comes first
  return insights.sort((a, b) => {
    const order = { high: 0, medium: 1, low: 2 };
    const pDiff = order[a.priority] - order[b.priority];
    if (pDiff !== 0) return pDiff;
    return (a.id === 'consistency' ? 0 : 1) - (b.id === 'consistency' ? 0 : 1);
  });
}

// ── Root Cause Chain ──────────────────────────────────────────────────────────

export interface CauseNode {
  label: string;
  sub?: string;
}

export interface RootCauseResult {
  chain: CauseNode[];
  fix: string;
}

export function buildRootCause(shots: Shot[], t: TFn = (k) => k): RootCauseResult | null {
  if (shots.length < 3) return null;

  const club       = dominantClub(shots);
  const bm         = getBenchmark(club);
  const category   = getClubCategory(club);
  const clubTarget = getClubTarget(club);
  const { minShots, smashFactor, spinRate, attackAngle, launchAngle, clubPath, spinAxis, consistencyCV } =
    FAULT_WINDOWS[category];

  const smashes    = shots.map((s) => s.smash_factor).filter((v): v is number => v != null);
  const spins      = shots.map((s) => s.spin_rpm).filter((v): v is number => v != null);
  const launches   = shots.map((s) => s.launch_angle_vertical).filter((v): v is number => v != null);
  const aoAs       = shots.map((s) => s.club_angle_deg).filter((v): v is number => v != null);
  const carries    = shots.map((s) => s.carry_spin_adjusted ?? s.estimated_carry_yards);
  const paths      = shots.map((s) => s.club_path_deg).filter((v): v is number => v != null);
  const axes       = shots.map((s) => s.spin_axis_deg).filter((v): v is number => v != null);
  const clubSpeeds = shots.map((s) => s.club_speed_mph).filter((v): v is number => v != null);

  const avgSmash    = smashes.length  >= minShots ? mean(smashes)             : null;
  const avgSpin     = spins.length    >= minShots ? mean(spins)               : null;
  const avgLaunch   = launches.length >= minShots ? mean(launches)            : null;
  const avgAoA      = aoAs.length     >= minShots ? mean(aoAs)                : null;
  const avgPath     = paths.length    >= minShots ? mean(paths.map(Math.abs)) : null;
  const avgAxis     = axes.length     >= minShots ? mean(axes.map(Math.abs))  : null;
  const avgCarry    = mean(carries);
  const sdCarry     = stdDev(carries);
  const cv          = avgCarry > 0 ? sdCarry / avgCarry : 0;
  const avgClubSpeed = clubSpeeds.length > 0 ? mean(clubSpeeds) : GAP_CONVERSIONS.defaultClubSpeedMph;

  const smashTarget   = clubTarget?.smash[0]  ?? bm?.smash  ?? 1.38;
  const spinBenchmark = clubTarget?.spin[1]   ?? bm?.spin   ?? 2700;

  // ── Fault flags (mirrors generateInsights thresholds for single source of truth) ──
  const hasAoA        = avgAoA   !== null && !!attackAngle  && avgAoA   < attackAngle.steepFault;
  const hasSmashLow   = avgSmash !== null && !!bm && !!smashFactor && avgSmash < smashTarget - smashFactor.lowGap;
  const hasSpinHigh   = avgSpin  !== null && !!bm && !!spinRate    && avgSpin  > bm.spin * spinRate.highFactor;
  const hasLaunchHigh = avgLaunch!== null && !!bm && !!launchAngle && avgLaunch > bm.launch + launchAngle.highGap;
  const hasPath       = avgPath  !== null && !!clubPath             && avgPath  > clubPath.absFault;
  const hasAxis       = avgAxis  !== null && spinAxis !== undefined && avgAxis  > spinAxis.absFault;
  const hasConsist    = sdCarry  > 0 && cv > (consistencyCV ?? 0.08) && shots.length >= minShots;

  // ── Chain selection: upstream faults take priority ──────────────────────────
  let templateId: string | null = null;
  if      (hasAoA)                       templateId = 'attack-steep';
  else if (hasSmashLow && hasSpinHigh)   templateId = 'low-face-spin';
  else if (hasSmashLow && hasLaunchHigh) templateId = 'casting';
  else if (hasSmashLow)                  templateId = 'smash-low';
  else if (hasSpinHigh && hasLaunchHigh) templateId = 'stalled-hips';
  else if (hasSpinHigh)                  templateId = 'spin-high';
  else if (hasPath && hasAxis)           templateId = 'out-to-in-slice';
  else if (hasAxis)                      templateId = 'face-path-mismatch';
  else if (hasPath)                      templateId = 'path';
  else if (hasConsist)                   templateId = 'consistency';
  else if (hasLaunchHigh)                templateId = 'launch-high';
  else                                   return null;

  const template = CHAIN_TEMPLATES[templateId];
  if (!template) return null;

  // ── Pre-format slot values ────────────────────────────────────────────────
  const excessRpm  = avgSpin   != null ? Math.max(0, Math.round(avgSpin - spinBenchmark)) : 0;
  const distSpin   = Math.round(excessRpm / 500 * GAP_CONVERSIONS.driverSpinYdsPer500Rpm);
  const smashGap   = avgSmash  != null ? Math.abs(avgSmash - smashTarget) : 0;
  const distSmash  = Math.round(smashGap * avgClubSpeed * GAP_CONVERSIONS.ydsPerMphBallSpeed);
  const launchLo   = (clubTarget?.launch ?? [bm?.launch ?? 12, 0])[0];
  // Spin loft ≈ dynamic loft − AoA; dynamic loft ≈ launch / launchToDynamicLoftRatio
  const spinLoftDeg = avgLaunch != null
    ? Math.round(Math.abs((avgLaunch / GAP_CONVERSIONS.launchToDynamicLoftRatio) - (avgAoA ?? -4)))
    : 0;

  const vals: Record<string, string> = {
    aoa:         avgAoA   != null ? `${avgAoA.toFixed(1)}°`                         : '?',
    spinLoft:    spinLoftDeg.toString(),
    spin:        avgSpin  != null ? `${Math.round(avgSpin).toLocaleString()} rpm`   : '?',
    spinTarget:  `${Math.round(spinBenchmark).toLocaleString()} rpm`,
    excessRpm:   `${excessRpm.toLocaleString()} rpm`,
    distSpin:    distSpin.toString(),
    smash:       avgSmash != null ? avgSmash.toFixed(2)                             : '?',
    smashTarget: smashTarget.toFixed(2),
    distSmash:   distSmash.toString(),
    launch:      avgLaunch!= null ? `${avgLaunch.toFixed(1)}°`                      : '?',
    launchTarget:`${launchLo}°`,
    path:        avgPath  != null ? `${avgPath.toFixed(1)}°`                        : '?',
    axisTilt:    avgAxis  != null ? `${avgAxis.toFixed(1)}°`                        : '?',
    sd:          Math.round(sdCarry).toString(),
    cv:          `${Math.round(cv * 100)}%`,
  };

  const fill = (s: string) => s.replace(/\{(\w+)\}/g, (_, k: string) => vals[k] ?? `{${k}}`);

  const chain: CauseNode[] = template.nodes.map((n) => ({
    label: fill(t(n.labelKey as TKey)),
    ...(n.subKey ? { sub: fill(t(n.subKey as TKey)) } : {}),
  }));

  // ── Resolve drill respecting per-club applicability ───────────────────────
  let drillKey = template.drillKey;
  const primary = DRILL_LIBRARY[drillKey];
  const primaryApplies = primary && (
    primary.clubs === 'all' || (primary.clubs as ClubCategory[]).includes(category)
  );
  if (!primaryApplies && template.fallbackDrillKey) {
    drillKey = template.fallbackDrillKey;
  }

  const resolvedDrill = DRILL_LIBRARY[drillKey];
  const drillTitle    = resolvedDrill ? t(resolvedDrill.titleKey) : drillKey;

  return { chain, fix: `${drillTitle} - ${t(template.fixCueKey as TKey)}` };
}

// ── Practice Drills ───────────────────────────────────────────────────────────

export interface Drill {
  number: number;
  title: string;
  description: string;
  keyThought: string;
}

interface DrillDef {
  titleKey: TKey;
  descKey: TKey;
  tipKey: TKey;
  /** Club categories this drill applies to; 'all' = no restriction */
  clubs: ClubCategory[] | 'all';
}

const DRILL_LIBRARY: Record<string, DrillDef> = {
  // From playbook Drill 1
  'shallow-aoa':    { titleKey: 'drillShallowTitle',    descKey: 'drillShallowDesc',    tipKey: 'drillShallowTip',    clubs: ['driver', 'fairway-wood', 'hybrid'] },
  // From playbook Drill 4
  'low-face':       { titleKey: 'drillLowFaceTitle',    descKey: 'drillLowFaceDesc',    tipKey: 'drillLowFaceTip',    clubs: ['driver', 'fairway-wood'] },
  // From playbook Drill 3
  'impact-board':   { titleKey: 'drillImpactTitle',     descKey: 'drillImpactDesc',     tipKey: 'drillImpactTip',     clubs: 'all' },
  // From playbook Drill 2
  'shaft-lean':     { titleKey: 'drillShaftTitle',      descKey: 'drillShaftDesc',      tipKey: 'drillShaftTip',      clubs: ['long-iron', 'mid-iron', 'short-iron', 'wedge'] },
  // From playbook Drill 5
  'tempo-drill':    { titleKey: 'drillTempoTitle',      descKey: 'drillTempoDesc',      tipKey: 'drillTempoTip',      clubs: 'all' },
  // From playbook Drill 6
  'wall-drill':     { titleKey: 'drillWallTitle',       descKey: 'drillWallDesc',       tipKey: 'drillWallTip',       clubs: 'all' },
  // From playbook Drill 7
  'step-through':   { titleKey: 'drillStepTitle',       descKey: 'drillStepDesc',       tipKey: 'drillStepTip',       clubs: 'all' },
  // From playbook Drill 8
  'lag-pump':       { titleKey: 'drillLagTitle',        descKey: 'drillLagDesc',        tipKey: 'drillLagTip',        clubs: 'all' },
  // From playbook Drill 9
  'headcover-path': { titleKey: 'drillHeadcoverTitle',  descKey: 'drillHeadcoverDesc',  tipKey: 'drillHeadcoverTip',  clubs: 'all' },
  // From playbook Drill 10
  'gate-drill':     { titleKey: 'drillGateTitle',       descKey: 'drillGateDesc',       tipKey: 'drillGateTip',       clubs: 'all' },
  // From playbook Drill 11
  'face-control':   { titleKey: 'drillFaceCtrlTitle',   descKey: 'drillFaceCtrlDesc',   tipKey: 'drillFaceCtrlTip',   clubs: 'all' },
  // From playbook Drill 12
  'low-point':      { titleKey: 'drillLowPointTitle',   descKey: 'drillLowPointDesc',   tipKey: 'drillLowPointTip',   clubs: 'all' },
  // From playbook Drill 14
  'connection':     { titleKey: 'drillConnTitle',       descKey: 'drillConnDesc',       tipKey: 'drillConnTip',       clubs: 'all' },
  // General
  'half-swing':     { titleKey: 'drillHalfTitle',       descKey: 'drillHalfDesc',       tipKey: 'drillHalfTip',       clubs: 'all' },
};

function resolveDrills(
  faultIds: string[],
  category: ClubCategory,
  t: TFn,
  limit = 3,
): Drill[] {
  const seen = new Set<string>();
  const keys: string[] = [];

  for (const faultId of faultIds) {
    const candidates: DrillMapping[] = FAULT_DRILLS[faultId] ?? [];
    for (const { clubs, key } of candidates) {
      if (seen.has(key)) continue;
      if (clubs !== 'all' && !(clubs as ClubCategory[]).includes(category)) continue;
      const def = DRILL_LIBRARY[key];
      if (!def) continue;
      if (def.clubs !== 'all' && !(def.clubs as ClubCategory[]).includes(category)) continue;
      seen.add(key);
      keys.push(key);
      if (keys.length >= limit) break;
    }
    if (keys.length >= limit) break;
  }

  // Fallback: ensure at least 2 drills even with no faults
  if (keys.length === 0) { keys.push('impact-board', 'tempo-drill'); }
  if (keys.length === 1) { keys.push(keys[0] === 'tempo-drill' ? 'half-swing' : 'tempo-drill'); }

  return keys.slice(0, limit).map((key, i) => {
    const dk = DRILL_LIBRARY[key];
    return { number: i + 1, title: t(dk.titleKey), description: t(dk.descKey), keyThought: t(dk.tipKey) };
  });
}

export function suggestDrills(shots: Shot[], t: TFn = (k) => k): Drill[] {
  if (shots.length < 3) return [];

  const club    = dominantClub(shots);
  const category = getClubCategory(club);
  const bm      = getBenchmark(club);
  const { minShots, smashFactor, spinRate, clubPath, consistencyCV, attackAngle } = FAULT_WINDOWS[category];

  const smashes = shots.map((s) => s.smash_factor).filter((v): v is number => v != null);
  const spins   = shots.map((s) => s.spin_rpm).filter((v): v is number => v != null);
  const carries = shots.map((s) => s.carry_spin_adjusted ?? s.estimated_carry_yards);
  const paths   = shots.map((s) => s.club_path_deg).filter((v): v is number => v != null);
  const aoAs    = shots.map((s) => s.club_angle_deg).filter((v): v is number => v != null);

  const avgSmash = smashes.length >= minShots ? mean(smashes) : null;
  const avgSpin  = spins.length   >= minShots ? mean(spins)   : null;
  const avgPath  = paths.length   >= minShots ? mean(paths.map(Math.abs)) : null;
  const avgAoA   = aoAs.length    >= minShots ? mean(aoAs)    : null;
  const cv       = carries.length > 1 ? stdDev(carries) / mean(carries) : 0;

  // Build ordered fault list - highest-impact first
  const faults: string[] = [];
  if (avgAoA !== null && attackAngle && avgAoA < attackAngle.steepFault) faults.push('attack-steep');
  if (avgSmash !== null && bm && smashFactor && avgSmash < bm.smash - smashFactor.lowGap) faults.push('smash-low');
  if (avgSpin  !== null && bm && spinRate    && avgSpin  > bm.spin  * spinRate.highFactor) faults.push('spin-high');
  if (avgPath  !== null && clubPath          && avgPath  > clubPath.absFault)              faults.push('path');
  if (cv > (consistencyCV ?? 0.10))                                                        faults.push('consistency');

  return resolveDrills(faults, category, t, 3);
}
