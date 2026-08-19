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

// --- Wire-contract payloads (mirror src/openflight/server.py SocketIO events) ---
// These document the events later roadmap phases consume. Phase 0 wires only
// `session_state` and `shot`; the rest are declared here so adding a feature is
// a store/handler change, not a type-hunting exercise.

// `shot` event payload. The web UI also receives `stats` alongside the shot;
// mobile derives its own stats from the shot list, so only `shot` is modelled.
export interface ShotEnvelope {
  shot: Shot;
}

// `session_state` event payload (emitted after `get_session`). The server sends
// shots oldest-first; the store inverts this to its newest-first invariant.
export interface SessionStatePayload {
  shots: Shot[];
  mock_mode?: boolean;
  debug_mode?: boolean;
  player_name?: string;
}

// `shot_processing` event: the capture/analysis lifecycle for the live view.
export type ShotProcessingState = 'capturing' | 'calculating' | 'failed';

// `club_changed` / `player_changed`: server-pushed selection changes to reflect
// back into the local pickers without echoing to the server.
export interface ClubChangedPayload {
  club: string;
}

export interface PlayerChangedPayload {
  player_name: string;
}
