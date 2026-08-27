import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Shot } from '../types/shot';

const ballShot = {
  mode: 'rolling-buffer',
  ball_speed_mph: 145,
  club: '7i',
  timestamp: '2026-08-23T12:00:00Z',
} as Shot;

class FakeAudioNode {
  connect() {
    return this;
  }
}

class FakeOscillator extends FakeAudioNode {
  type = 'sine';
  frequency = { setValueAtTime() {} };
  started = false;

  start() {
    this.started = true;
  }

  stop() {}
}

class FakeGain extends FakeAudioNode {
  gain = {
    setValueAtTime() {},
    exponentialRampToValueAtTime() {},
  };
}

class FakeAudioContext {
  state = 'running';
  currentTime = 0;
  destination = {};
  oscillators: FakeOscillator[] = [];

  resume() {
    return Promise.resolve();
  }

  createOscillator() {
    const oscillator = new FakeOscillator();
    this.oscillators.push(oscillator);
    return oscillator;
  }

  createGain() {
    return new FakeGain();
  }
}

describe('handleShotMessage', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('plays a beep when a live ball shot is received', async () => {
    const context = new FakeAudioContext();
    vi.stubGlobal('window', {
      AudioContext: function AudioContext() {
        return context;
      },
    } as unknown as Window & typeof globalThis);

    const { handleShotMessage } = await import('./handleShotMessage');
    const { useShotStore } = await import('../stores/useShotStore');
    useShotStore.setState({
      latestShot: null,
      shots: [],
      isNewShot: false,
      shotProcessingPhase: null,
      shotVersion: 0,
    });

    handleShotMessage({
      shot: ballShot,
      stats: {
        shot_count: 1,
        avg_ball_speed: 145,
        max_ball_speed: 145,
        min_ball_speed: 145,
        avg_club_speed: null,
        avg_smash_factor: null,
        avg_carry_est: 0,
      },
    });

    expect(useShotStore.getState().latestShot).toEqual(ballShot);
    expect(context.oscillators.some((oscillator) => oscillator.started)).toBe(true);
  });
});
