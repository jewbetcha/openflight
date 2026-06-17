import { renderHook, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useStatsData } from './useStatsData';
import { makeShot } from '../test/shotFactory';

function mockFetch() {
  return vi.fn((url: string) => {
    if (url === '/api/history') {
      return Promise.resolve({
        json: () =>
          Promise.resolve({
            sessions: [{ id: 's1', started_at: null, filename: 'f.jsonl', shot_count: 1 }],
          }),
      });
    }
    // /api/history/:id/shots
    return Promise.resolve({ json: () => Promise.resolve({ shots: [makeShot({ club: 'pw' })] }) });
  });
}

describe('useStatsData', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch() as unknown as typeof fetch);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('derives clubs, counts and stats from the live shots', () => {
    const live = [makeShot({ club: 'driver' }), makeShot({ club: '7-iron' })];
    const { result } = renderHook(() => useStatsData(live));

    expect(result.current.activeShots).toHaveLength(2);
    expect(result.current.availableClubs).toEqual(expect.arrayContaining(['driver', '7-iron']));
    expect(result.current.clubCounts).toMatchObject({ driver: 1, '7-iron': 1 });
    expect(result.current.isHistorical).toBe(false);
    expect(result.current.stats?.shot_count).toBe(2);
  });

  it('filters shots by the selected club', () => {
    const live = [makeShot({ club: 'driver' }), makeShot({ club: '7-iron' })];
    const { result } = renderHook(() => useStatsData(live));

    act(() => result.current.setSelectedClub('driver'));

    expect(result.current.filteredShots).toHaveLength(1);
    expect(result.current.filteredShots[0].club).toBe('driver');
  });

  it('loads the session list and switches to a historical session', async () => {
    const { result } = renderHook(() => useStatsData([makeShot({ club: 'driver' })]));

    await waitFor(() => expect(result.current.sessionList).toHaveLength(1));

    act(() => result.current.setSelectedSessionId('s1'));

    await waitFor(() => expect(result.current.isHistorical).toBe(true));
    await waitFor(() => expect(result.current.activeShots[0]?.club).toBe('pw'));
  });
});
