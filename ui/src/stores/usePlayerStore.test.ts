import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

function installBrowser(players: string[] = ['James', 'Alex'], selected = 'James') {
  const store: Record<string, string> = {
    'openflight-players': JSON.stringify(players),
    'openflight-selected-player': selected,
  };
  const localStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
  };
  vi.stubGlobal('localStorage', localStorage);
  vi.stubGlobal('window', { localStorage });
  return store;
}

describe('usePlayerStore', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('refuses to remove the active player', async () => {
    installBrowser();
    const { usePlayerStore } = await import('./usePlayerStore');

    usePlayerStore.getState().removePlayer('James');

    expect(usePlayerStore.getState().players).toEqual(['James', 'Alex']);
    expect(usePlayerStore.getState().selectedPlayer).toBe('James');
  });

  it('removes an inactive player', async () => {
    installBrowser();
    const { usePlayerStore } = await import('./usePlayerStore');

    usePlayerStore.getState().removePlayer('Alex');

    expect(usePlayerStore.getState().players).toEqual(['James']);
    expect(usePlayerStore.getState().selectedPlayer).toBe('James');
  });
});
