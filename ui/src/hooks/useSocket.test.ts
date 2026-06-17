import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ShotProvider } from '../state/ShotProvider';
import { useSocket } from './useSocket';

// Capture the event handlers useSocket registers, and expose a fake socket so
// tests can drive server events without a real connection.
const { handlers, fakeSocket } = vi.hoisted(() => {
  const handlers: Record<string, (data: unknown) => void> = {};
  const fakeSocket = {
    on: (event: string, cb: (data: unknown) => void) => {
      handlers[event] = cb;
    },
    emit: vi.fn(),
    close: vi.fn(),
  };
  return { handlers, fakeSocket };
});

vi.mock('socket.io-client', () => ({ io: () => fakeSocket }));

function fire(event: string, data?: unknown) {
  act(() => handlers[event]?.(data));
}

// Reset before each test (not after): RTL's auto-cleanup unmounts the previous
// hook - and calls socket.close() - after afterEach hooks run, so clearing here
// keeps that teardown from leaking a call count into the next test.
beforeEach(() => {
  fakeSocket.emit.mockClear();
  fakeSocket.close.mockClear();
  for (const key of Object.keys(handlers)) delete handlers[key];
});

describe('useSocket', () => {
  it('starts disconnected and flips to connected on the connect event', () => {
    const { result } = renderHook(() => useSocket(), { wrapper: ShotProvider });
    expect(result.current.connected).toBe(false);

    fire('connect');

    expect(result.current.connected).toBe(true);
  });

  it('maps session_state into mock/debug/camera flags', () => {
    const { result } = renderHook(() => useSocket(), { wrapper: ShotProvider });

    fire('session_state', {
      shots: [],
      mock_mode: true,
      debug_mode: true,
      camera_available: true,
      camera_enabled: true,
      camera_streaming: false,
      ball_detected: false,
    });

    expect(result.current.mockMode).toBe(true);
    expect(result.current.debugMode).toBe(true);
    expect(result.current.cameraStatus.available).toBe(true);
    expect(result.current.cameraStatus.enabled).toBe(true);
  });

  it('caps debug readings at 50 and debug shot logs at 20', () => {
    const { result } = renderHook(() => useSocket(), { wrapper: ShotProvider });

    for (let i = 0; i < 60; i++) {
      fire('debug_reading', { speed: i, direction: 'outbound', magnitude: 1, timestamp: `${i}` });
    }
    for (let i = 0; i < 25; i++) {
      fire('debug_shot', { type: 'shot', timestamp: `${i}`, radar: {}, camera: null, club: 'driver' });
    }

    expect(result.current.debugReadings).toHaveLength(50);
    expect(result.current.debugReadings[49].speed).toBe(59); // newest retained
    expect(result.current.debugShotLogs).toHaveLength(20);
  });

  it('accumulates trigger diagnostics (capped at 50) and tallies the status counts', () => {
    const { result } = renderHook(() => useSocket(), { wrapper: ShotProvider });

    for (let i = 0; i < 60; i++) {
      fire('trigger_diagnostic', { accepted: i % 2 === 0 });
    }

    expect(result.current.triggerDiagnostics).toHaveLength(50);
    expect(result.current.triggerStatus.triggers_total).toBe(60);
    expect(result.current.triggerStatus.triggers_accepted).toBe(30);
    expect(result.current.triggerStatus.triggers_rejected).toBe(30);
  });

  it('closes the socket on unmount', () => {
    const { unmount } = renderHook(() => useSocket(), { wrapper: ShotProvider });
    unmount();
    expect(fakeSocket.close).toHaveBeenCalledTimes(1);
  });
});
