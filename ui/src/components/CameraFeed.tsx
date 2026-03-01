import { useState } from 'react';
import type { CameraStatus } from '../hooks/useSocket';
import './CameraFeed.css';

interface CameraFeedProps {
  cameraStatus: CameraStatus;
  onToggleCamera: () => void;
  onToggleStream: () => void;
}

const STREAM_URL = import.meta.env.VITE_SOCKET_URL
  ? `${import.meta.env.VITE_SOCKET_URL}/camera/stream`
  : 'http://localhost:8080/camera/stream';

export function CameraFeed({ cameraStatus, onToggleCamera, onToggleStream }: CameraFeedProps) {
  const [streamError, setStreamError] = useState(false);
  const [prevStreaming, setPrevStreaming] = useState(false);
  const { available, enabled, streaming, ball_detected, ball_confidence } = cameraStatus;

  // Reset error when streaming starts
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
          <h3>Camera Not Available</h3>
          <p>Start the server with --camera flag to enable camera support</p>
        </div>
      </div>
    );
  }

  return (
    <div className="camera-feed">
      <div className="camera-feed__header">
        <h2 className="camera-feed__title">Camera Feed</h2>
        <div className="camera-feed__controls">
          <button
            className={`camera-feed__button ${enabled ? 'camera-feed__button--active' : ''}`}
            onClick={onToggleCamera}
          >
            {enabled ? 'Disable Camera' : 'Enable Camera'}
          </button>
          {enabled && (
            <button
              className={`camera-feed__button ${streaming ? 'camera-feed__button--streaming' : ''}`}
              onClick={onToggleStream}
            >
              {streaming ? 'Stop Stream' : 'Start Stream'}
            </button>
          )}
        </div>
      </div>

      <div className="camera-feed__content">
        {!enabled ? (
          <div className="camera-feed__message">
            <span className="camera-feed__icon">📷</span>
            <h3>Camera Disabled</h3>
            <p>Click "Enable Camera" to start ball detection</p>
          </div>
        ) : !streaming ? (
          <div className="camera-feed__message">
            <span className="camera-feed__icon">🎥</span>
            <h3>Stream Paused</h3>
            <p>Ball detection is active. Click "Start Stream" to view live feed.</p>
            <div className={`camera-feed__detection ${ball_detected ? 'camera-feed__detection--detected' : ''}`}>
              {ball_detected ? `Ball Detected (${Math.round(ball_confidence * 100)}%)` : 'No Ball Detected'}
            </div>
          </div>
        ) : streamError ? (
          <div className="camera-feed__message camera-feed__message--error">
            <span className="camera-feed__icon">⚠️</span>
            <h3>Stream Error</h3>
            <p>Could not load camera stream</p>
            <button className="camera-feed__button" onClick={() => setStreamError(false)}>
              Retry
            </button>
          </div>
        ) : (
          <div className="camera-feed__stream">
            <img
              src={STREAM_URL}
              alt="Camera Feed"
              className="camera-feed__video"
              onError={() => setStreamError(true)}
            />
            <div className="camera-feed__overlay">
              <div className={`camera-feed__status ${ball_detected ? 'camera-feed__status--detected' : ''}`}>
                {ball_detected ? `Ball: ${Math.round(ball_confidence * 100)}%` : 'Searching...'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
