import { useState } from 'react';
import type { CameraStatus } from '../hooks/useSocket';
import { useLanguage } from '../state/useLanguage';
import { getServerOrigin } from '../utils/serverOrigin';
import './CameraFeed.css';

interface CameraFeedProps {
  cameraStatus: CameraStatus;
  onToggleCamera: () => void;
  onToggleStream: () => void;
  streamToken?: string;
}

export function CameraFeed({ cameraStatus, onToggleCamera, onToggleStream, streamToken }: CameraFeedProps) {
  const [streamError, setStreamError] = useState(false);
  const [prevStreaming, setPrevStreaming] = useState(false);
  const { t } = useLanguage();
  const { available, enabled, streaming, ball_detected, ball_confidence } = cameraStatus;
  const streamUrl = streamToken
    ? `${getServerOrigin()}/camera/stream?token=${encodeURIComponent(streamToken)}`
    : `${getServerOrigin()}/camera/stream`;

  if (streaming && !prevStreaming) {
    setStreamError(false);
  }
  if (streaming !== prevStreaming) {
    setPrevStreaming(streaming);
  }

  if (!available) {
    return (
      <div className="camera-feed camera-feed--unavailable">
        <div className="camera-feed__message">
          <span className="camera-feed__icon">📷</span>
          <h3>{t('cameraNotAvailable')}</h3>
          <p>{t('cameraNotAvailableSub')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="camera-feed">
      <div className="camera-feed__header">
        <h2 className="camera-feed__title">{t('cameraFeed')}</h2>
        <div className="camera-feed__controls">
          <button
            className={`camera-feed__button ${enabled ? 'camera-feed__button--active' : ''}`}
            onClick={onToggleCamera}
          >
            {enabled ? t('disableCamera') : t('enableCamera')}
          </button>
          {enabled && (
            <button
              className={`camera-feed__button ${streaming ? 'camera-feed__button--streaming' : ''}`}
              onClick={onToggleStream}
            >
              {streaming ? t('stopStream') : t('startStream')}
            </button>
          )}
        </div>
      </div>

      <div className="camera-feed__content">
        {!enabled ? (
          <div className="camera-feed__message">
            <span className="camera-feed__icon">📷</span>
            <h3>{t('cameraDisabled')}</h3>
            <p>{t('cameraDisabledSub')}</p>
          </div>
        ) : !streaming ? (
          <div className="camera-feed__message">
            <span className="camera-feed__icon">🎥</span>
            <h3>{t('streamPaused')}</h3>
            <p>{t('streamPausedSub')}</p>
            <div className={`camera-feed__detection ${ball_detected ? 'camera-feed__detection--detected' : ''}`}>
              {ball_detected ? `${t('ballDetected')} (${Math.round(ball_confidence * 100)}%)` : t('noBallDetected')}
            </div>
          </div>
        ) : streamError ? (
          <div className="camera-feed__message camera-feed__message--error">
            <span className="camera-feed__icon">⚠️</span>
            <h3>{t('streamError')}</h3>
            <p>{t('streamErrorSub')}</p>
            <button className="camera-feed__button" onClick={() => setStreamError(false)}>
              {t('retry')}
            </button>
          </div>
        ) : (
          <div className="camera-feed__stream">
            <img
              src={streamUrl}
              alt={t('cameraFeed')}
              className="camera-feed__video"
              onError={() => setStreamError(true)}
            />
            <div className="camera-feed__overlay">
              <div className={`camera-feed__status ${ball_detected ? 'camera-feed__status--detected' : ''}`}>
                {ball_detected ? `${t('ballDetected')}: ${Math.round(ball_confidence * 100)}%` : `${t('noBallDetected')}…`}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
