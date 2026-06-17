import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { UnitPreferenceProvider } from '../state/UnitPreferenceProvider';
import { LanguageProvider } from '../state/LanguageProvider';
import { ViewModeProvider } from '../state/ViewModeProvider';
import type { CameraStatus } from '../hooks/useSocket';
import type { Shot } from '../types/shot';
import { Scoreboard } from './Scoreboard';

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
  carry_spin_adjusted: 261,
};

describe('Scoreboard', () => {
  it('renders latest shot metrics and recent shot strip', () => {
    const a11yPrefs = { reduceMotion: false, highContrast: false, largeText: false, colorBlind: false };
    const html = renderToString(
      <LanguageProvider>
        <ViewModeProvider>
        <UnitPreferenceProvider>
          <Scoreboard
            connected
            cameraStatus={cameraStatus}
            latestShot={shot}
            shots={[shot]}
            a11yPrefs={a11yPrefs}
            onA11yToggle={() => {}}
          />
        </UnitPreferenceProvider>
        </ViewModeProvider>
      </LanguageProvider>,
    );

    expect(html).toContain('OpenFlight Scoreboard');
    expect(html).toContain('151.2');
    expect(html).toContain('261');
    expect(html).toContain('Socket connected');
    expect(html).toContain('display-shot-chip__number');
    // Screen-reader structure: metric tiles are single composed stops (role=img,
    // so VoiceOver reads one label) plus a concise live status region.
    expect(html).toContain('role="img"');
    expect(html).toContain('role="status"');
    expect(html).toContain('class="sr-only"');
  });

  it('shows the shot visualizer (not an open camera stream) when the camera is unavailable', () => {
    const a11yPrefs = { reduceMotion: false, highContrast: false, largeText: false, colorBlind: false };
    const offCamera: CameraStatus = { ...cameraStatus, available: false, streaming: false };
    const html = renderToString(
      <LanguageProvider>
        <ViewModeProvider>
        <UnitPreferenceProvider>
          <Scoreboard
            connected
            cameraStatus={offCamera}
            latestShot={shot}
            shots={[shot]}
            a11yPrefs={a11yPrefs}
            onA11yToggle={() => {}}
          />
        </UnitPreferenceProvider>
        </ViewModeProvider>
      </LanguageProvider>,
    );

    expect(html).toContain('display-viz');
    // No MJPEG connection should be opened when the camera is off (CQ2).
    expect(html).not.toContain('/camera/stream');
  });
});
