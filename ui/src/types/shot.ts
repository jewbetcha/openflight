export type SpinQuality = 'high' | 'medium' | 'low' | 'experimental';

export interface Shot {
  mode?: 'rolling-buffer' | 'mock' | 'swing-speed';
  ball_speed_mph: number;
  club_speed_mph: number | null;
  smash_factor: number | null;
  estimated_carry_yards: number;
  carry_range: [number, number];
  club: string;
  player_name?: string;
  timestamp: string;
  peak_magnitude: number | null;
  // Launch angle data (from K-LD7 radar (deprecated), camera, or estimation)
  launch_angle_vertical: number | null;
  launch_angle_horizontal: number | null;
  launch_angle_confidence: number | null;
  angle_source: 'radar' | 'camera' | 'estimated' | null;
  club_angle_deg: number | null;
  club_path_deg: number | null;
  spin_axis_deg: number | null;
  // Rolling buffer mode spin data
  spin_rpm: number | null;
  spin_confidence: number | null;
  spin_quality: SpinQuality | null;
  spin_source: 'measured' | 'calculated' | null;
  spin_method?: string | null;
  spin_multipath_fade_hz?: number | null;
  carry_spin_adjusted: number | null;
  swing_speed_duration_ms?: number;
  swing_speed_reading_count?: number;
  swing_speed_trigger_mph?: number;
  training_implement?: string;
  training_implement_label?: string;
}

export interface SessionStats {
  shot_count: number;
  avg_ball_speed: number;
  max_ball_speed: number;
  min_ball_speed: number;
  std_dev?: number;
  avg_club_speed: number | null;
  avg_smash_factor: number | null;
  avg_carry_est: number;
  // Rolling buffer mode spin stats
  avg_spin_rpm?: number | null;
  spin_detection_rate?: number;
  mode?: 'rolling-buffer';
}

export interface SessionState {
  stats: SessionStats;
  shots: Shot[];
}

export interface TriggerDiagnostic {
  timestamp: string;
  trigger_type: string;
  accepted: boolean;
  reason: string;
  response_bytes: number;
  total_readings: number;
  outbound_readings: number;
  inbound_readings: number;
  peak_outbound_mph: number;
  peak_inbound_mph: number;
  all_outbound_speeds: number[];
  all_inbound_speeds: number[];
  peak_outbound_magnitude: number;
  peak_inbound_magnitude: number;
  latency_ms: number | null;
  // Present when accepted (shot created):
  ball_speed_mph?: number | null;
  club_speed_mph?: number | null;
  spin_rpm?: number | null;
  carry_yards?: number | null;
  iwr6843?: IWR6843Diagnostic;
}

export type IWR6843DiagnosticState = 'accepted' | 'rejected' | 'error';

export interface IWR6843Diagnostic {
  state: IWR6843DiagnosticState;
  reason: string;
  angle_deg?: number;
}

export interface TriggerDiagnosticUpdate {
  timestamp: string;
  iwr6843: IWR6843Diagnostic;
}

export interface TriggerStatus {
  mode: 'rolling-buffer' | 'mock' | 'swing-speed';
  trigger_type: string | null;
  radar_connected: boolean;
  radar_port: string | null;
  triggers_total: number;
  triggers_accepted: number;
  triggers_rejected: number;
}

export interface SwingSpeedStats {
  count: number;
  last_speed_mph: number;
  best_speed_mph: number;
  avg_speed_mph: number;
}

export interface SwingSpeedStatsFilter {
  playerName?: string | null;
  trainingImplement?: string | null;
  club?: string | null;
}

export function isSwingSpeedShot(shot: Shot | null): boolean {
  return shot?.mode === 'swing-speed' || shot?.club === 'Swing Speed';
}

export function getSwingSpeedMph(shot: Shot): number {
  return shot.club_speed_mph ?? shot.ball_speed_mph;
}

function normalizePlayerName(playerName: string | null | undefined): string {
  return (playerName?.trim() || 'Player 1').toLowerCase();
}

function normalizeToken(value: string | null | undefined): string {
  return (value?.trim() || '').toLowerCase();
}

export function filterSwingSpeedShots(shots: Shot[], filter: SwingSpeedStatsFilter = {}): Shot[] {
  const playerName = normalizePlayerName(filter.playerName);
  const trainingImplement = normalizeToken(filter.trainingImplement);
  const club = normalizeToken(filter.club);

  return shots.filter((shot) => {
    if (!isSwingSpeedShot(shot)) {
      return false;
    }

    if (filter.playerName && normalizePlayerName(shot.player_name) !== playerName) {
      return false;
    }

    if (trainingImplement) {
      const shotImplement = normalizeToken(shot.training_implement);
      const shotImplementLabel = normalizeToken(shot.training_implement_label);
      const shotClub = normalizeToken(shot.club);

      return (
        shotImplement === trainingImplement ||
        shotImplementLabel === trainingImplement ||
        shotClub === trainingImplement
      );
    }

    if (club && normalizeToken(shot.club) !== club) {
      return false;
    }

    return true;
  });
}

export function computeSwingSpeedStats(shots: Shot[], filter: SwingSpeedStatsFilter = {}): SwingSpeedStats {
  const swingSpeeds = filterSwingSpeedShots(shots, filter).map(getSwingSpeedMph);

  if (swingSpeeds.length === 0) {
    return {
      count: 0,
      last_speed_mph: 0,
      best_speed_mph: 0,
      avg_speed_mph: 0,
    };
  }

  const total = swingSpeeds.reduce((sum, speed) => sum + speed, 0);

  return {
    count: swingSpeeds.length,
    last_speed_mph: swingSpeeds[swingSpeeds.length - 1],
    best_speed_mph: Math.max(...swingSpeeds),
    avg_speed_mph: total / swingSpeeds.length,
  };
}

/**
 * Compute session stats from an array of shots.
 */
export function computeStats(shots: Shot[]): SessionStats {
  if (shots.length === 0) {
    return {
      shot_count: 0,
      avg_ball_speed: 0,
      max_ball_speed: 0,
      min_ball_speed: 0,
      avg_club_speed: null,
      avg_smash_factor: null,
      avg_carry_est: 0,
    };
  }

  const ballSpeeds = shots.map((s) => s.ball_speed_mph);
  const clubSpeeds = shots.map((s) => s.club_speed_mph).filter((v): v is number => v !== null);
  const smashFactors = shots.map((s) => s.smash_factor).filter((v): v is number => v !== null);
  const carries = shots.map((s) => s.estimated_carry_yards);

  const mean = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
  const stdDev = (arr: number[]) => {
    if (arr.length < 2) return 0;
    const m = mean(arr);
    return Math.sqrt(arr.reduce((sum, x) => sum + (x - m) ** 2, 0) / (arr.length - 1));
  };

  return {
    shot_count: shots.length,
    avg_ball_speed: mean(ballSpeeds),
    max_ball_speed: Math.max(...ballSpeeds),
    min_ball_speed: Math.min(...ballSpeeds),
    std_dev: stdDev(ballSpeeds),
    avg_club_speed: clubSpeeds.length > 0 ? mean(clubSpeeds) : null,
    avg_smash_factor: smashFactors.length > 0 ? mean(smashFactors) : null,
    avg_carry_est: mean(carries),
  };
}

/**
 * Get unique clubs from shots array.
 */
export function getUniqueClubs(shots: Shot[]): string[] {
  const clubs = new Set(shots.map((s) => s.club));
  return Array.from(clubs);
}
