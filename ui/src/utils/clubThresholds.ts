// ── Club category classification ───────────────────────────────────────────────

export type ClubCategory =
  | 'driver'
  | 'fairway-wood'
  | 'hybrid'
  | 'long-iron'
  | 'mid-iron'
  | 'short-iron'
  | 'wedge';

export function getClubCategory(club: string): ClubCategory {
  const c = club.toLowerCase().replace(/[\s_]+/g, '-');
  if (c === 'driver') return 'driver';
  if (/^\d-wood$/.test(c)) return 'fairway-wood';
  if (c.includes('hybrid')) return 'hybrid';
  if (['2-iron', '3-iron', '4-iron', '5-iron'].includes(c)) return 'long-iron';
  if (['6-iron', '7-iron'].includes(c)) return 'mid-iron';
  if (['8-iron', '9-iron'].includes(c)) return 'short-iron';
  return 'wedge'; // pw, gw, sw, lw
}

// ── Per-club fault-detection windows ──────────────────────────────────────────
// Sources: TrackMan industry averages, Keiser University/College of Golf data.
// All windows are intentionally conservative - only flag clear faults, not edge cases.

export interface FaultWindow {
  /** Minimum shots required before any fault is flagged for this club category */
  minShots: number;
  /** Attack angle (club_angle_deg): fault if rolling avg is below this value (degrees) */
  attackAngle?: { steepFault: number };
  /** Spin rate: fault thresholds expressed as a factor of the club benchmark spin */
  spinRate?: { highFactor: number; lowFactor?: number };
  /** Launch angle: fault gap (degrees) from benchmark before flagging */
  launchAngle?: { lowGap: number; highGap: number };
  /** Smash factor: gap below benchmark before flagging */
  smashFactor?: { lowGap: number };
  /** Club path: absolute degrees off-line before flagging */
  clubPath?: { absFault: number };
  /** Spin axis: absolute degrees before flagging */
  spinAxis?: { absFault: number };
  /** Carry CV (stdDev/mean) above which consistency is flagged */
  consistencyCV: number;
}

export const FAULT_WINDOWS: Record<ClubCategory, FaultWindow> = {
  // Driver: optimal AoA +1° to +5°; fault below −2°
  driver: {
    minShots:     3,
    attackAngle:  { steepFault: -2 },
    spinRate:     { highFactor: 1.20, lowFactor: 0.80 },
    launchAngle:  { lowGap: 3, highGap: 4 },
    smashFactor:  { lowGap: 0.04 },
    clubPath:     { absFault: 4 },
    spinAxis:     { absFault: 6 },
    consistencyCV: 0.08,
  },
  // Fairway woods: slight downward AoA acceptable, steep fault below −4°
  'fairway-wood': {
    minShots:     3,
    attackAngle:  { steepFault: -4 },
    spinRate:     { highFactor: 1.20 },
    launchAngle:  { lowGap: 3, highGap: 4 },
    smashFactor:  { lowGap: 0.04 },
    clubPath:     { absFault: 5 },
    spinAxis:     { absFault: 8 },
    consistencyCV: 0.10,
  },
  hybrid: {
    minShots:     3,
    attackAngle:  { steepFault: -5 },
    spinRate:     { highFactor: 1.20 },
    launchAngle:  { lowGap: 3, highGap: 5 },
    smashFactor:  { lowGap: 0.04 },
    clubPath:     { absFault: 5 },
    consistencyCV: 0.10,
  },
  // Long irons: ideal AoA −2° to −4°; fault below −7°
  'long-iron': {
    minShots:     3,
    attackAngle:  { steepFault: -7 },
    spinRate:     { highFactor: 1.20, lowFactor: 0.75 },
    launchAngle:  { lowGap: 3, highGap: 5 },
    smashFactor:  { lowGap: 0.04 },
    clubPath:     { absFault: 5 },
    consistencyCV: 0.10,
  },
  'mid-iron': {
    minShots:     5,
    spinRate:     { highFactor: 1.20, lowFactor: 0.75 },
    launchAngle:  { lowGap: 3, highGap: 5 },
    smashFactor:  { lowGap: 0.04 },
    clubPath:     { absFault: 5 },
    consistencyCV: 0.10,
  },
  'short-iron': {
    minShots:     5,
    spinRate:     { highFactor: 1.20, lowFactor: 0.75 },
    launchAngle:  { lowGap: 3, highGap: 5 },
    smashFactor:  { lowGap: 0.04 },
    clubPath:     { absFault: 5 },
    consistencyCV: 0.12,
  },
  // Wedges: higher spin tolerance, more launch variation acceptable
  wedge: {
    minShots:     5,
    spinRate:     { highFactor: 1.25, lowFactor: 0.70 },
    launchAngle:  { lowGap: 4, highGap: 6 },
    smashFactor:  { lowGap: 0.05 },
    clubPath:     { absFault: 6 },
    consistencyCV: 0.15,
  },
};

// ── Fault → drill mapping ──────────────────────────────────────────────────────
// Each fault ID maps to an ordered list of drill candidates.
// Drills are filtered at runtime to only include ones applicable to the shot club category.
// 'all' means the drill is suitable for any club.

export interface DrillMapping {
  /** Club categories this drill entry applies to; 'all' = no restriction */
  clubs: ClubCategory[] | 'all';
  /** Drill key matching a DRILL_LIBRARY entry in analysis.ts */
  key: string;
}

// ── Per-club optimal target windows ───────────────────────────────────────────
// Sources: TrackMan optimizer data, PGA/LPGA industry averages.
// Ranges represent the optimal performance window; outside = flaggable opportunity.
// A skill-profile scalar (future) could shift targets toward higher-launch/lower-spin
// for slower swing speeds; these values assume a mid-handicap baseline.

export interface ClubTarget {
  /** Optimal smash factor range [min, max] */
  smash: [number, number];
  /** Optimal backspin range rpm [min, max] */
  spin: [number, number];
  /** Optimal launch angle degrees [min, max] */
  launch: [number, number];
  /** Optimal attack angle degrees [min, max]; negative = downward */
  aoa?: [number, number];
  /** Optimal descent angle degrees [min, max] */
  descent?: [number, number];
}

export const CLUB_TARGETS: Record<string, ClubTarget> = {
  driver:   { smash: [1.48, 1.50], spin: [2200, 2700], launch: [11, 14],  aoa: [1, 5],        descent: [35, 40] },
  '3-wood': { smash: [1.47, 1.49], spin: [3000, 3700], launch: [9, 13],   aoa: [-3, -1],      descent: [38, 43] },
  '5-wood': { smash: [1.45, 1.48], spin: [3700, 4500], launch: [12, 16],  aoa: [-3, -2],      descent: [43, 47] },
  '7-wood': { smash: [1.45, 1.48], spin: [3700, 4500], launch: [12, 16],  aoa: [-3, -2],      descent: [43, 47] },
  hybrid:   { smash: [1.42, 1.46], spin: [4000, 4800], launch: [12, 17],  aoa: [-4, -2],      descent: [45, 48] },
  '4-iron': { smash: [1.40, 1.45], spin: [4500, 5300], launch: [14, 16],  aoa: [-4, -3],      descent: [46, 48] },
  '5-iron': { smash: [1.38, 1.43], spin: [5000, 5800], launch: [14, 17],  aoa: [-4, -3],      descent: [47, 49] },
  '6-iron': { smash: [1.36, 1.40], spin: [5900, 6400], launch: [15, 18],  aoa: [-4.5, -3.5],  descent: [48, 50] },
  '7-iron': { smash: [1.33, 1.38], spin: [6800, 7300], launch: [16, 19],  aoa: [-5, -4],      descent: [49, 51] },
  '8-iron': { smash: [1.30, 1.35], spin: [7800, 8300], launch: [18, 21],  aoa: [-5, -4.5],    descent: [50, 51] },
  '9-iron': { smash: [1.27, 1.32], spin: [8600, 9000], launch: [20, 24],  aoa: [-5, -4],      descent: [50, 52] },
  pw:       { smash: [1.23, 1.27], spin: [8400, 9500], launch: [23, 28],  aoa: [-6, -5],      descent: [50, 52] },
  gw:       { smash: [1.10, 1.25], spin: [9000, 11000], launch: [28, 34], aoa: [-7, -4],      descent: [50, 53] },
  sw:       { smash: [1.10, 1.25], spin: [9000, 11000], launch: [28, 34], aoa: [-7, -4],      descent: [50, 53] },
  lw:       { smash: [1.10, 1.25], spin: [9000, 11000], launch: [28, 34], aoa: [-7, -4],      descent: [50, 53] },
};

export function getClubTarget(club: string): ClubTarget | null {
  const key = club.toLowerCase().replace(/[\s_]+/g, '-');
  return CLUB_TARGETS[key] ?? null;
}

// ── Gap → yardage conversion constants ─────────────────────────────────────────
// All constants are tunable here; no magic numbers in analysis logic.

export const GAP_CONVERSIONS = {
  /** Carry yards gained per 1 mph of ball speed improvement */
  ydsPerMphBallSpeed: 2.0,
  /** Fallback club speed (mph) used when club_speed_mph is unavailable in shot data */
  defaultClubSpeedMph: 95.0,
  /** Driver/fairway-wood: carry yards lost per 500 rpm above spin target upper bound */
  driverSpinYdsPer500Rpm: 2.0,
  /** Driver only: carry yards gained per degree closer to optimal AoA lower bound */
  driverAoaYdsPerDegree: 2.5,
  /** Launch-angle-to-dynamic-loft ratio used for spin-loft estimation */
  launchToDynamicLoftRatio: 0.65,
} as const;

// ── Root-cause chain templates ─────────────────────────────────────────────────
// Keyed by chain/fault ID.  Nodes carry English text with {var} placeholders;
// values are filled at runtime from computed shot metrics.
// drillKey is the primary Fix drill; fallbackDrillKey is used when the primary
// does not apply to the current club category (per DRILL_LIBRARY.clubs).

export interface ChainNodeTemplate {
  /** i18n key for label text (value may contain {var} placeholders) */
  labelKey: string;
  /** i18n key for optional secondary explanation (value may contain {var} placeholders) */
  subKey?: string;
}

export interface ChainTemplate {
  /** Primary drill key (must exist in DRILL_LIBRARY) */
  drillKey: string;
  /** Fallback drill key when drillKey doesn't apply to the current club category */
  fallbackDrillKey?: string;
  /** i18n key for the fix cue appended after the drill title in the Fix line */
  fixCueKey: string;
  /** Ordered chain nodes; {var} slots filled from ChainValues at runtime */
  nodes: ChainNodeTemplate[];
}

export const CHAIN_TEMPLATES: Record<string, ChainTemplate> = {
  // 1. Steep AoA → high spin loft → excess spin → distance loss
  'attack-steep': {
    drillKey: 'shallow-aoa',
    fallbackDrillKey: 'wall-drill',
    fixCueKey: 'fcAttackSteep',
    nodes: [
      { labelKey: 'cnAttack1', subKey: 'cnAttack1s' },
      { labelKey: 'cnAttack2', subKey: 'cnAttack2s' },
      { labelKey: 'cnAttack3' },
      { labelKey: 'cnAttack4' },
    ],
  },

  // 2. Low smash + high spin → low-face gear effect
  'low-face-spin': {
    drillKey: 'low-face',
    fallbackDrillKey: 'impact-board',
    fixCueKey: 'fcLowFaceSpin',
    nodes: [
      { labelKey: 'cnLowFace1', subKey: 'cnLowFace1s' },
      { labelKey: 'cnLowFace2' },
      { labelKey: 'cnLowFace3', subKey: 'cnLowFace3s' },
      { labelKey: 'cnLowFace4' },
    ],
  },

  // 3. Low smash + high launch → casting / early release
  'casting': {
    drillKey: 'lag-pump',
    fixCueKey: 'fcCasting',
    nodes: [
      { labelKey: 'cnCasting1', subKey: 'cnCasting1s' },
      { labelKey: 'cnCasting2' },
      { labelKey: 'cnCasting3' },
      { labelKey: 'cnCasting4' },
    ],
  },

  // 4. Low smash (standalone) → off-center contact
  'smash-low': {
    drillKey: 'impact-board',
    fixCueKey: 'fcSmashLow',
    nodes: [
      { labelKey: 'cnSmash1', subKey: 'cnSmash1s' },
      { labelKey: 'cnSmash2' },
      { labelKey: 'cnSmash3' },
    ],
  },

  // 5. High spin + high launch → stalled hips / flip
  'stalled-hips': {
    drillKey: 'step-through',
    fixCueKey: 'fcStalledHips',
    nodes: [
      { labelKey: 'cnHips1', subKey: 'cnHips1s' },
      { labelKey: 'cnHips2' },
      { labelKey: 'cnHips3' },
      { labelKey: 'cnHips4' },
    ],
  },

  // 6. High spin (standalone) → added dynamic loft at impact
  'spin-high': {
    drillKey: 'shaft-lean',
    fallbackDrillKey: 'shallow-aoa',
    fixCueKey: 'fcSpinHigh',
    nodes: [
      { labelKey: 'cnSpinHigh1', subKey: 'cnSpinHigh1s' },
      { labelKey: 'cnSpinHigh2' },
      { labelKey: 'cnSpinHigh3' },
      { labelKey: 'cnSpinHigh4' },
    ],
  },

  // 7. High path + high axis → out-to-in with open face (slice)
  'out-to-in-slice': {
    drillKey: 'headcover-path',
    fixCueKey: 'fcOutToInSlice',
    nodes: [
      { labelKey: 'cnSlice1', subKey: 'cnSlice1s' },
      { labelKey: 'cnSlice2' },
      { labelKey: 'cnSlice3' },
    ],
  },

  // 8. High spin axis (no path fault) → face-to-path mismatch
  'face-path-mismatch': {
    drillKey: 'gate-drill',
    fixCueKey: 'fcFacePathMismatch',
    nodes: [
      { labelKey: 'cnFacePath1', subKey: 'cnFacePath1s' },
      { labelKey: 'cnFacePath2' },
    ],
  },

  // 9. High path (no axis fault) → path deviation / face control
  'path': {
    drillKey: 'face-control',
    fixCueKey: 'fcPath',
    nodes: [
      { labelKey: 'cnPath1', subKey: 'cnPath1s' },
      { labelKey: 'cnPath2' },
    ],
  },

  // 10. High CV → inconsistent tempo / delivery
  'consistency': {
    drillKey: 'tempo-drill',
    fixCueKey: 'fcConsistency',
    nodes: [
      { labelKey: 'cnConsist1', subKey: 'cnConsist1s' },
      { labelKey: 'cnConsist2' },
      { labelKey: 'cnConsist3' },
    ],
  },

  // 11. High launch (standalone) → effective loft too high
  'launch-high': {
    drillKey: 'step-through',
    fixCueKey: 'fcLaunchHigh',
    nodes: [
      { labelKey: 'cnLaunchHigh1', subKey: 'cnLaunchHigh1s' },
      { labelKey: 'cnLaunchHigh2' },
    ],
  },
};

export const FAULT_DRILLS: Record<string, DrillMapping[]> = {
  'attack-steep': [
    { clubs: ['driver', 'fairway-wood', 'hybrid'], key: 'shallow-aoa' },
    { clubs: 'all',                                key: 'wall-drill' },
    { clubs: 'all',                                key: 'step-through' },
  ],
  'spin-high': [
    { clubs: ['driver', 'fairway-wood', 'hybrid'], key: 'shallow-aoa' },
    { clubs: 'all',                                key: 'lag-pump' },
    { clubs: ['mid-iron', 'short-iron', 'wedge'],  key: 'shaft-lean' },
    { clubs: 'all',                                key: 'step-through' },
  ],
  'spin-low': [
    { clubs: 'all',                                key: 'low-point' },
    { clubs: ['long-iron', 'mid-iron', 'short-iron', 'wedge'], key: 'shaft-lean' },
  ],
  'smash-low': [
    { clubs: 'all',                                key: 'impact-board' },
    { clubs: ['driver', 'fairway-wood'],           key: 'low-face' },
    { clubs: 'all',                                key: 'wall-drill' },
  ],
  'launch-low': [
    { clubs: ['driver', 'fairway-wood', 'hybrid'], key: 'shallow-aoa' },
    { clubs: ['driver', 'fairway-wood'],           key: 'low-face' },
    { clubs: ['long-iron', 'mid-iron', 'short-iron', 'wedge'], key: 'shaft-lean' },
  ],
  'launch-high': [
    { clubs: 'all',                                key: 'shaft-lean' },
    { clubs: 'all',                                key: 'step-through' },
    { clubs: 'all',                                key: 'lag-pump' },
  ],
  'path': [
    { clubs: 'all',                                key: 'headcover-path' },
    { clubs: 'all',                                key: 'gate-drill' },
    { clubs: 'all',                                key: 'face-control' },
  ],
  'spin-axis': [
    { clubs: 'all',                                key: 'face-control' },
    { clubs: 'all',                                key: 'gate-drill' },
  ],
  'consistency': [
    { clubs: 'all',                                key: 'tempo-drill' },
    { clubs: 'all',                                key: 'connection' },
    { clubs: 'all',                                key: 'wall-drill' },
    { clubs: 'all',                                key: 'low-point' },
  ],
};
