export interface Shot {
  ball_speed_mph: number;
  club_speed_mph: number | null;
  smash_factor: number | null;
  estimated_carry_yards: number;
  carry_range: [number, number];
  club: string;
  timestamp: string;
  peak_magnitude: number | null;
  // Camera-based launch angle data
  launch_angle_vertical: number | null;
  launch_angle_horizontal: number | null;
  launch_angle_confidence: number | null;
  // Rolling buffer mode spin data
  spin_rpm: number | null;
  spin_confidence: number | null;
  spin_quality: 'high' | 'medium' | 'low' | null;
  carry_spin_adjusted: number | null;
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
  mode?: 'streaming' | 'rolling-buffer';
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
}

export interface TriggerStatus {
  mode: 'streaming' | 'rolling-buffer' | 'mock';
  trigger_type: string | null;
  radar_connected: boolean;
  radar_port: string | null;
  triggers_total: number;
  triggers_accepted: number;
  triggers_rejected: number;
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
