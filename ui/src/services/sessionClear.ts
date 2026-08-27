import type { Shot } from '../types/shot';
import { excludeShotsByPlayer } from '../types/shot';

export interface SessionClearedPayload {
  player_name?: string;
  shots?: Shot[];
}

/** Remaining shots after a clear. Prefer the server list; otherwise drop one player. */
export function remainingShotsAfterClear(currentShots: Shot[], payload?: SessionClearedPayload | null): Shot[] {
  if (payload?.shots) {
    return payload.shots;
  }
  if (payload?.player_name) {
    return excludeShotsByPlayer(currentShots, payload.player_name);
  }
  return [];
}
