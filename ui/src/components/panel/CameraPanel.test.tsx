import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { CameraCaptureSettings, CameraStatus } from '../../stores/useCameraStore';
import { CameraPanel } from './CameraPanel';

function text(html: string): string {
  return html.replace(/<!-- -->/g, '');
}

function render(status: Partial<CameraStatus>, captureSettings: CameraCaptureSettings = { available: false }) {
  const cameraStatus: CameraStatus = {
    available: true,
    enabled: false,
    streaming: false,
    ball_detected: false,
    ball_confidence: 0,
    ...status,
  };

  return text(
    renderToString(
      <CameraPanel
        cameraStatus={cameraStatus}
        captureSettings={captureSettings}
        captureSettingsError={null}
        onToggleCamera={() => {}}
        onToggleStream={() => {}}
        onUpdateCaptureSettings={() => {}}
      />
    )
  );
}

describe('CameraPanel', () => {
  it('renders the disabled state drawn in the mockup', () => {
    const html = render({ enabled: false });

    expect(html).toContain('Camera disabled');
    expect(html).toContain('Enable the camera to start ball detection');
    expect(html).toContain('Enable camera');
    expect(html).toContain('panel-action--primary');
    expect(html).toContain('Ball detection off');
    // No stream controls until the camera is on.
    expect(html).not.toContain('Start stream');
  });

  it('offers stream controls once enabled', () => {
    const html = render({ enabled: true });

    expect(html).toContain('Disable camera');
    expect(html).toContain('Start stream');
    expect(html).toContain('panel-action--secondary');
    expect(html).toContain('Stream paused');
  });

  it('renders the live feed while streaming', () => {
    const html = render({ enabled: true, streaming: true });

    expect(html).toContain('camera-panel__stage--live');
    expect(html).toContain('alt="Camera feed"');
    expect(html).toContain('Stop stream');
    expect(html).toContain('Searching…');
  });

  it('reports ball confidence when a ball is detected', () => {
    const html = render({ enabled: true, streaming: true, ball_detected: true, ball_confidence: 0.837 });

    expect(html).toContain('Ball 84%');
    expect(html).toContain('camera-panel__chip--detected');
    expect(html).toContain('Ball detected 84%');
  });

  it('explains the unavailable case and hides controls that cannot work', () => {
    const html = render({ available: false });

    expect(html).toContain('Camera unavailable');
    expect(html).toContain('--camera');
    expect(html).not.toContain('Enable camera');
  });

  it('preserves the high-speed camera workspace when capture is available', () => {
    const html = render({}, { available: true, running: true, armed: true, width: 320, height: 200, fps: 600 });

    expect(html).toContain('camera-panel--capture');
    expect(html).toContain('camera-feed__workspace');
    expect(html).toContain('Camera setup');
    expect(html).toContain('rolling buffer');
  });
});
