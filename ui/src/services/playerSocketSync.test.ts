import { beforeEach, describe, expect, it } from 'vitest';
import { useSystemStore } from '../stores/useSystemStore';
import { ingestSocketPlayerName, shouldEchoSelectionToServer } from './playerSocketSync';

describe('player socket sync', () => {
  beforeEach(() => {
    useSystemStore.setState({ serverPlayerName: null });
  });

  it('does not adopt player_name from session_state snapshots', () => {
    ingestSocketPlayerName('session_state', 'Player 1');

    expect(useSystemStore.getState().serverPlayerName).toBeNull();
  });

  it('adopts player_name from player_changed', () => {
    ingestSocketPlayerName('player_changed', 'James');

    expect(useSystemStore.getState().serverPlayerName).toBe('James');
  });

  it('does not ping-pong when a stale snapshot arrives after a local push', () => {
    const selected = 'James';
    const emitted: string[] = [];

    if (shouldEchoSelectionToServer('became-connected')) {
      emitted.push(selected);
    }

    ingestSocketPlayerName('session_state', 'Player 1');
    const afterSnapshot = useSystemStore.getState().serverPlayerName;
    if (afterSnapshot && afterSnapshot !== selected && shouldEchoSelectionToServer('selection-changed')) {
      emitted.push(afterSnapshot);
    }

    ingestSocketPlayerName('player_changed', selected);

    expect(useSystemStore.getState().serverPlayerName).toBe('James');
    expect(emitted).toEqual(['James']);
  });

  it('only pushes the local player when the socket becomes connected', () => {
    expect(shouldEchoSelectionToServer('became-connected')).toBe(true);
    expect(shouldEchoSelectionToServer('selection-changed')).toBe(false);
  });
});
