import { describe, expect, it } from 'vitest';
import type { CameraStatus } from '../stores/useCameraStore';
import { ballDetectionStatusLabel } from './ballDetectionStatus';

const camera = (overrides: Partial<CameraStatus> = {}): CameraStatus => ({
  available: false,
  enabled: false,
  streaming: false,
  ball_detected: false,
  ball_confidence: 0,
  ...overrides,
});

describe('ballDetectionStatusLabel', () => {
  it('says unavailable when the camera is not present', () => {
    expect(ballDetectionStatusLabel(camera())).toBe('Unavailable');
  });

  it('says off when the camera is present but disabled', () => {
    expect(ballDetectionStatusLabel(camera({ available: true, enabled: false }))).toBe('Off');
  });

  it('says searching when detection is on but no ball is seen', () => {
    expect(ballDetectionStatusLabel(camera({ available: true, enabled: true, ball_detected: false }))).toBe(
      'Searching'
    );
  });

  it('reports confidence when a ball is seen', () => {
    expect(
      ballDetectionStatusLabel(camera({ available: true, enabled: true, ball_detected: true, ball_confidence: 0.84 }))
    ).toBe('Ball 84%');
  });
});
