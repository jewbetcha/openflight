// Local mirror of the subset of src/openflight/server.py's shot_to_dict() payload
// that the mobile UI renders. Intentionally self-contained rather than shared
// with ui/src/types/shot.ts -- the two apps ship separately, and both are just
// hand-mirrors of the Python wire contract (the real source of truth).

export type SpinQuality = 'high' | 'medium' | 'low' | 'experimental';

// Graded confidence used for the 3-dot indicator on launch-angle tiles.
export type AngleQuality = 'high' | 'medium' | 'low';

export interface Shot {
  mode?: 'rolling-buffer' | 'mock' | 'swing-speed';
  ball_speed_mph: number;
  club_speed_mph: number | null;
  smash_factor: number | null;
  estimated_carry_yards: number;
  carry_spin_adjusted: number | null;
  carry_range: [number, number];
  club: string;
  timestamp: string;
  // Launch angle data (radar/camera/estimation; "mock" in mock mode)
  launch_angle_vertical: number | null;
  launch_angle_horizontal: number | null;
  launch_angle_confidence: number | null;
  angle_source: string | null;
  club_angle_deg: number | null;
  club_path_deg: number | null;
  spin_axis_deg: number | null;
  // Rolling buffer mode spin data
  spin_rpm: number | null;
  spin_source: 'measured' | 'calculated' | null;
  spin_quality: SpinQuality | null;
}

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';
