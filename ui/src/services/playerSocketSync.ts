import { useSystemStore } from '../stores/useSystemStore';

export type PlayerSocketEvent = 'session_state' | 'player_changed';
export type PlayerEchoTrigger = 'became-connected' | 'selection-changed';

/**
 * session_state.player_name is a connect/reload snapshot and can race with
 * set_player. Only player_changed is a live selection update.
 */
export function ingestSocketPlayerName(source: PlayerSocketEvent, playerName: string | undefined): void {
  if (playerName === undefined || source === 'session_state') return;
  useSystemStore.getState().setServerPlayerName(playerName);
}

/** Push localStorage player on connect. User clicks already emit set_player. */
export function shouldEchoSelectionToServer(trigger: PlayerEchoTrigger): boolean {
  return trigger === 'became-connected';
}
