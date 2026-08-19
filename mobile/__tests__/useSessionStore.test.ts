import { useSessionStore } from '../stores/useSessionStore';
import type { Shot } from '../types';

// Minimal Shot factory — only the fields the store cares about (identity/order)
// need to be distinct; the rest are filled with representative values.
function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    ball_speed_mph: 100,
    club_speed_mph: 70,
    smash_factor: 1.43,
    estimated_carry_yards: 250,
    carry_spin_adjusted: null,
    carry_range: [240, 260],
    club: 'driver',
    timestamp: '2026-08-18T00:00:00Z',
    launch_angle_vertical: null,
    launch_angle_horizontal: null,
    launch_angle_confidence: null,
    angle_source: null,
    club_angle_deg: null,
    club_path_deg: null,
    spin_axis_deg: null,
    spin_rpm: null,
    spin_source: null,
    spin_quality: null,
    ...overrides,
  };
}

// Reset to initial state between tests — the store is a module singleton.
beforeEach(() => {
  useSessionStore.setState({ connectionState: 'disconnected', shots: [] });
});

describe('useSessionStore', () => {
  it('starts disconnected with no shots', () => {
    const state = useSessionStore.getState();
    expect(state.connectionState).toBe('disconnected');
    expect(state.shots).toEqual([]);
  });

  it('setConnectionState transitions through the connection lifecycle', () => {
    const { setConnectionState } = useSessionStore.getState();
    setConnectionState('connecting');
    expect(useSessionStore.getState().connectionState).toBe('connecting');
    setConnectionState('connected');
    expect(useSessionStore.getState().connectionState).toBe('connected');
    setConnectionState('error');
    expect(useSessionStore.getState().connectionState).toBe('error');
  });

  it('setShots inverts server (oldest-first) order into newest-first', () => {
    const oldest = makeShot({ timestamp: 't1' });
    const newest = makeShot({ timestamp: 't3' });
    // Server sends oldest-first.
    useSessionStore.getState().setShots([oldest, makeShot({ timestamp: 't2' }), newest]);

    const shots = useSessionStore.getState().shots;
    expect(shots[0].timestamp).toBe('t3');
    expect(shots[2].timestamp).toBe('t1');
  });

  it('setShots does not mutate the caller-supplied array', () => {
    const input = [makeShot({ timestamp: 't1' }), makeShot({ timestamp: 't2' })];
    useSessionStore.getState().setShots(input);
    // reverse() on a copy, not in place.
    expect(input[0].timestamp).toBe('t1');
  });

  it('addShot prepends the new shot as the latest', () => {
    useSessionStore.getState().setShots([makeShot({ timestamp: 't1' })]);
    useSessionStore.getState().addShot(makeShot({ timestamp: 't2' }));

    const shots = useSessionStore.getState().shots;
    expect(shots).toHaveLength(2);
    expect(shots[0].timestamp).toBe('t2');
    expect(shots[1].timestamp).toBe('t1');
  });

  it('clearShots empties the list', () => {
    useSessionStore.getState().setShots([makeShot(), makeShot()]);
    useSessionStore.getState().clearShots();
    expect(useSessionStore.getState().shots).toEqual([]);
  });
});
