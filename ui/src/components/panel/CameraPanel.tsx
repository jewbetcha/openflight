import { useState } from 'react';
import type { CameraCaptureSettings, CameraStatus } from '../../stores/useCameraStore';
import { getServerOrigin } from '../../utils/serverOrigin';
import { CameraFeed } from '../CameraFeed';
import { PanelHeader } from './PanelHeader';
import { PanelAction } from './PanelAction';
import { useI18n } from '../../i18n/useI18n';

interface CameraPanelProps {
  cameraStatus: CameraStatus;
  captureSettings: CameraCaptureSettings;
  captureSettingsError: string | null;
  clubLabel?: string;
  onToggleCamera: () => void;
  onToggleStream: () => void;
  onUpdateCaptureSettings: (settings: Partial<CameraCaptureSettings>) => void;
}

const STREAM_URL = `${getServerOrigin()}/camera/stream`;

/** The hairline camera glyph drawn in 7c's empty state. */
function CameraGlyph() {
  return (
    <span className="camera-panel__glyph" aria-hidden="true">
      <span className="camera-panel__glyph-lens" />
    </span>
  );
}

function LiveFeed({ ballDetected, ballConfidence }: { ballDetected: boolean; ballConfidence: number }) {
  const { t } = useI18n();
  const [streamError, setStreamError] = useState(false);

  if (streamError) {
    return (
      <div className="camera-panel__stage">
        <CameraGlyph />
        <span className="camera-panel__title">{t('camera.streamError')}</span>
        <span className="camera-panel__detail">{t('camera.streamErrorDetail')}</span>
        <button type="button" className="panel-chip" onClick={() => setStreamError(false)}>
          {t('camera.retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="camera-panel__stage camera-panel__stage--live">
      <img
        src={STREAM_URL}
        alt={t('camera.feedAlt')}
        className="camera-panel__video"
        onError={() => setStreamError(true)}
      />
      <span className={`camera-panel__chip${ballDetected ? ' camera-panel__chip--detected' : ''}`}>
        {ballDetected ? t('camera.ballPercent', { percent: Math.round(ballConfidence * 100) }) : t('camera.searching')}
      </span>
    </div>
  );
}

/**
 * Design doc 7c draws the disabled state. The unavailable, idle, streaming and
 * error states reuse the same hatched stage so the panel reads as one surface.
 */
export function CameraPanel({
  cameraStatus,
  captureSettings,
  captureSettingsError,
  clubLabel,
  onToggleCamera,
  onToggleStream,
  onUpdateCaptureSettings,
}: CameraPanelProps) {
  const { t } = useI18n();
  const { available, enabled, streaming, ball_detected, ball_confidence } = cameraStatus;

  if (captureSettings.available) {
    return (
      <div className="panel camera-panel camera-panel--capture">
        <div className="panel__body camera-panel__body camera-panel__body--capture">
          <CameraFeed
            cameraStatus={cameraStatus}
            captureSettings={captureSettings}
            captureSettingsError={captureSettingsError}
            onToggleCamera={onToggleCamera}
            onToggleStream={onToggleStream}
            onUpdateCaptureSettings={onUpdateCaptureSettings}
          />
        </div>
      </div>
    );
  }

  const subtitle = !available
    ? t('camera.notConnected')
    : !enabled
      ? t('camera.detectionOff')
      : ball_detected
        ? t('camera.detected', { percent: Math.round(ball_confidence * 100) })
        : t('camera.detectionOn');

  const stage = () => {
    if (!available) {
      return (
        <div className="camera-panel__stage">
          <CameraGlyph />
          <span className="camera-panel__title">{t('camera.unavailable')}</span>
          <span className="camera-panel__detail">{t('camera.unavailableDetail')}</span>
        </div>
      );
    }

    if (!enabled) {
      return (
        <div className="camera-panel__stage">
          <CameraGlyph />
          <span className="camera-panel__title">{t('camera.disabled')}</span>
          <span className="camera-panel__detail">{t('camera.disabledDetail')}</span>
        </div>
      );
    }

    if (!streaming) {
      return (
        <div className="camera-panel__stage">
          <CameraGlyph />
          <span className="camera-panel__title">{t('camera.streamPaused')}</span>
          <span className="camera-panel__detail">{t('camera.streamPausedDetail')}</span>
        </div>
      );
    }

    return <LiveFeed ballDetected={ball_detected} ballConfidence={ball_confidence} />;
  };

  return (
    <div className="panel">
      <PanelHeader
        title={t('nav.camera')}
        subtitle={subtitle}
        club={clubLabel}
        actions={
          available ? (
            <>
              <PanelAction onClick={onToggleCamera}>{enabled ? t('camera.disable') : t('camera.enable')}</PanelAction>
              {enabled ? (
                <PanelAction variant="secondary" onClick={onToggleStream}>
                  {streaming ? t('camera.stopStream') : t('camera.startStream')}
                </PanelAction>
              ) : null}
            </>
          ) : null
        }
      />
      <div className="panel__body camera-panel__body">{stage()}</div>
    </div>
  );
}
