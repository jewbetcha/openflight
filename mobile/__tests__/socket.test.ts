import { socketService } from '../services/socket';
import { useSessionStore } from '../stores/useSessionStore';
import type { Shot } from '../types';

// Fake Socket.IO socket. The fake is built *inside* the mock factory (not
// captured from an outer const) so it exists by the time `services/socket`
// requires 'socket.io-client' during import — outer consts would still be in
// their temporal dead zone at that point. The internals are exposed on `__mock`
// and pulled back out with requireMock below.
jest.mock('socket.io-client', () => {
  const handlers: Record<string, (...args: unknown[]) => void> = {};
  const emit = jest.fn();
  const close = jest.fn();
  const io = jest.fn((_url: string, _opts?: unknown) => ({
    on: (event: string, cb: (...args: unknown[]) => void) => {
      handlers[event] = cb;
    },
    emit,
    close,
  }));
  return { io, __mock: { handlers, emit, close } };
});

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

const socketMock = jest.requireMock('socket.io-client') as {
  io: jest.Mock;
  __mock: {
    handlers: Record<string, (...args: unknown[]) => void>;
    emit: jest.Mock;
    close: jest.Mock;
  };
};
const { io: mockIo } = socketMock;
const { emit: mockEmit, close: mockClose, handlers: mockHandlers } = socketMock.__mock;

function trigger(event: string, ...args: unknown[]) {
  mockHandlers[event]?.(...args);
}

function makeShot(timestamp: string): Shot {
  return {
    ball_speed_mph: 100,
    club_speed_mph: null,
    smash_factor: null,
    estimated_carry_yards: 250,
    carry_spin_adjusted: null,
    carry_range: [240, 260],
    club: 'driver',
    timestamp,
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
  };
}

beforeEach(() => {
  useSessionStore.setState({ connectionState: 'disconnected', shots: [] });
  for (const key of Object.keys(mockHandlers)) delete mockHandlers[key];
  mockIo.mockClear();
  mockEmit.mockClear();
  mockClose.mockClear();
});

afterEach(() => {
  socketService.disconnect();
});

describe('socketService', () => {
  it('opens a connection and reports connecting', () => {
    socketService.connect('http://host:8080');
    expect(mockIo).toHaveBeenCalledTimes(1);
    expect(mockIo).toHaveBeenCalledWith('http://host:8080', expect.objectContaining({ reconnection: true }));
    expect(useSessionStore.getState().connectionState).toBe('connecting');
  });

  it('ignores a second connect while already connected', () => {
    socketService.connect('http://host:8080');
    socketService.connect('http://other:8080');
    expect(mockIo).toHaveBeenCalledTimes(1);
  });

  it('on connect: reports connected and requests the session', () => {
    socketService.connect('http://host:8080');
    trigger('connect');
    expect(useSessionStore.getState().connectionState).toBe('connected');
    expect(mockEmit).toHaveBeenCalledWith('get_session');
  });

  it('session_state replaces shots newest-first', () => {
    socketService.connect('http://host:8080');
    trigger('session_state', { shots: [makeShot('t1'), makeShot('t2')] });
    const shots = useSessionStore.getState().shots;
    expect(shots[0].timestamp).toBe('t2');
  });

  it('shot event prepends the new shot', () => {
    socketService.connect('http://host:8080');
    trigger('session_state', { shots: [makeShot('t1')] });
    trigger('shot', { shot: makeShot('t2') });
    const shots = useSessionStore.getState().shots;
    expect(shots).toHaveLength(2);
    expect(shots[0].timestamp).toBe('t2');
  });

  it('disconnect event reports disconnected', () => {
    socketService.connect('http://host:8080');
    trigger('connect');
    trigger('disconnect');
    expect(useSessionStore.getState().connectionState).toBe('disconnected');
  });

  it('connect_error reports error', () => {
    socketService.connect('http://host:8080');
    trigger('connect_error');
    expect(useSessionStore.getState().connectionState).toBe('error');
  });

  it('simulateShot emits the simulate_shot event', () => {
    socketService.connect('http://host:8080');
    mockEmit.mockClear();
    socketService.simulateShot();
    expect(mockEmit).toHaveBeenCalledWith('simulate_shot');
  });

  it('disconnect() closes the socket and reports disconnected', () => {
    socketService.connect('http://host:8080');
    socketService.disconnect();
    expect(mockClose).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().connectionState).toBe('disconnected');
  });
});
