import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { CameraStatus } from '../stores/useCameraStore';
import type { Shot } from '../types/shot';
import { DisplayMode } from './DisplayMode';

const cameraStatus: CameraStatus = {
  available: true,
  enabled: true,
  streaming: true,
  ball_detected: false,
  ball_confidence: 0,
};

const shot: Shot = {
  ball_speed_mph: 151.2,
  club_speed_mph: 101.1,
  smash_factor: 1.5,
  estimated_carry_yards: 254,
  carry_range: [244, 264],
  club: 'driver',
  timestamp: '2026-05-18T12:00:00Z',
  peak_magnitude: 42,
  launch_angle_vertical: 13.4,
  launch_angle_horizontal: -1.2,
  launch_angle_confidence: 0.82,
  angle_source: 'radar',
  club_angle_deg: 1.1,
  club_path_deg: 2.5,
  spin_axis_deg: -3.1,
  spin_rpm: 2450,
  spin_confidence: 0.8,
  spin_quality: 'high',
  spin_source: 'calculated',
  carry_spin_adjusted: 261,
};

describe('DisplayMode', () => {
  it('renders latest shot metrics and recent shot strip', () => {
    const html = renderToString(<DisplayMode connected cameraStatus={cameraStatus} latestShot={shot} shots={[shot]} />);

    expect(html).toContain('OpenFlight Display');
    expect(html).toContain('151.2');
    expect(html).toContain('261');
    expect(html).toContain('Socket connected');
    expect(html).toContain('display-shot-chip__number');
  });
});
