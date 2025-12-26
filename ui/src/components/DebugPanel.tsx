import { memo, useState } from 'react';
import type { DebugReading, RadarConfig, DebugShotLog, CameraStatus } from '../hooks/useSocket';
import './DebugPanel.css';

interface DebugPanelProps {
  enabled: boolean;
  readings: DebugReading[];
  shotLogs: DebugShotLog[];
  radarConfig: RadarConfig;
  cameraStatus: CameraStatus;
  mockMode: boolean;
  onToggle: () => void;
  onUpdateConfig: (config: Partial<RadarConfig>) => void;
}

interface ReadingRowProps {
  reading: DebugReading;
}

const ReadingRow = memo(function ReadingRow({ reading }: ReadingRowProps) {
  const time = new Date(reading.timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div className={`debug-reading debug-reading--${reading.direction}`}>
      <span className="debug-reading__time">{time}</span>
      <span className="debug-reading__speed">{reading.speed.toFixed(1)}</span>
      <span className="debug-reading__dir">{reading.direction === 'outbound' ? 'OUT' : 'IN'}</span>
      <span className="debug-reading__mag">{reading.magnitude?.toFixed(0) ?? '--'}</span>
    </div>
  );
});

interface ShotLogRowProps {
  log: DebugShotLog;
}

const ShotLogRow = memo(function ShotLogRow({ log }: ShotLogRowProps) {
  const time = new Date(log.timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  const hasLaunchAngle = log.camera && log.camera.launch_detected;

  return (
    <div className="debug-shot-log">
      <div className="debug-shot-log__header">
        <span className="debug-shot-log__time">{time}</span>
        <span className="debug-shot-log__club">{log.club}</span>
      </div>
      <div className="debug-shot-log__data">
        <div className="debug-shot-log__section">
          <span className="debug-shot-log__section-label">Radar</span>
          <div className="debug-shot-log__row">
            <span className="debug-shot-log__label">Ball Speed</span>
            <span className="debug-shot-log__value debug-shot-log__value--primary">{log.radar.ball_speed_mph} mph</span>
          </div>
          <div className="debug-shot-log__row">
            <span className="debug-shot-log__label">Club Speed</span>
            <span className="debug-shot-log__value">{log.radar.club_speed_mph ?? '—'} {log.radar.club_speed_mph ? 'mph' : ''}</span>
          </div>
          <div className="debug-shot-log__row">
            <span className="debug-shot-log__label">Smash</span>
            <span className="debug-shot-log__value">{log.radar.smash_factor?.toFixed(2) ?? '—'}</span>
          </div>
          <div className="debug-shot-log__row">
            <span className="debug-shot-log__label">Magnitude</span>
            <span className="debug-shot-log__value">{log.radar.peak_magnitude}</span>
          </div>
        </div>
        <div className="debug-shot-log__section">
          <span className="debug-shot-log__section-label">Camera</span>
          {log.camera ? (
            <>
              <div className="debug-shot-log__row">
                <span className="debug-shot-log__label">Launch Angle</span>
                <span className={`debug-shot-log__value ${hasLaunchAngle ? 'debug-shot-log__value--success' : 'debug-shot-log__value--muted'}`}>
                  {hasLaunchAngle ? `${log.camera.launch_angle_vertical.toFixed(1)}°` : 'Not detected'}
                </span>
              </div>
              <div className="debug-shot-log__row">
                <span className="debug-shot-log__label">Horizontal</span>
                <span className="debug-shot-log__value">
                  {hasLaunchAngle ? `${log.camera.launch_angle_horizontal.toFixed(1)}°` : '—'}
                </span>
              </div>
              <div className="debug-shot-log__row">
                <span className="debug-shot-log__label">Confidence</span>
                <span className="debug-shot-log__value">
                  {hasLaunchAngle ? `${(log.camera.launch_angle_confidence * 100).toFixed(0)}%` : '—'}
                </span>
              </div>
              <div className="debug-shot-log__row">
                <span className="debug-shot-log__label">Positions</span>
                <span className="debug-shot-log__value">{log.camera.positions_tracked}</span>
              </div>
            </>
          ) : (
            <div className="debug-shot-log__row">
              <span className="debug-shot-log__value debug-shot-log__value--muted">Camera disabled</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

interface SliderControlProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}

function SliderControl({ label, value, min, max, step = 1, unit = '', disabled, onChange }: SliderControlProps) {
  const [localValue, setLocalValue] = useState(value);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseInt(e.target.value, 10);
    setLocalValue(newValue);
  };

  const handleRelease = () => {
    if (localValue !== value) {
      onChange(localValue);
    }
  };

  // Sync local value when prop changes
  if (localValue !== value && !document.activeElement?.classList.contains('slider-control__input')) {
    setLocalValue(value);
  }

  return (
    <div className={`slider-control ${disabled ? 'slider-control--disabled' : ''}`}>
      <div className="slider-control__header">
        <span className="slider-control__label">{label}</span>
        <span className="slider-control__value">{localValue}{unit}</span>
      </div>
      <input
        type="range"
        className="slider-control__input"
        min={min}
        max={max}
        step={step}
        value={localValue}
        disabled={disabled}
        onChange={handleChange}
        onMouseUp={handleRelease}
        onTouchEnd={handleRelease}
      />
      <div className="slider-control__range">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

export function DebugPanel({ enabled, readings, shotLogs, radarConfig, cameraStatus, mockMode, onToggle, onUpdateConfig }: DebugPanelProps) {
  return (
    <div className="debug-panel">
      <div className="debug-panel__header">
        <h3>Debug Mode</h3>
        <button
          className={`debug-toggle ${enabled ? 'debug-toggle--active' : ''}`}
          onClick={onToggle}
        >
          {enabled ? 'Stop' : 'Start'}
        </button>
      </div>

      {/* Camera Status */}
      <div className="debug-panel__section">
        <h4>Camera Status</h4>
        <div className="debug-panel__status-grid">
          <div className="debug-panel__status-item">
            <span className="debug-panel__status-label">Available</span>
            <span className={`debug-panel__status-value ${cameraStatus.available ? 'debug-panel__status-value--success' : 'debug-panel__status-value--error'}`}>
              {cameraStatus.available ? 'Yes' : 'No'}
            </span>
          </div>
          <div className="debug-panel__status-item">
            <span className="debug-panel__status-label">Enabled</span>
            <span className={`debug-panel__status-value ${cameraStatus.enabled ? 'debug-panel__status-value--success' : ''}`}>
              {cameraStatus.enabled ? 'Yes' : 'No'}
            </span>
          </div>
          <div className="debug-panel__status-item">
            <span className="debug-panel__status-label">Ball Detected</span>
            <span className={`debug-panel__status-value ${cameraStatus.ball_detected ? 'debug-panel__status-value--success' : ''}`}>
              {cameraStatus.ball_detected ? `Yes (${(cameraStatus.ball_confidence * 100).toFixed(0)}%)` : 'No'}
            </span>
          </div>
        </div>
        <p className="debug-panel__note">
          Launch angle detection is ready for testing. Spin detection requires a high-speed camera and is not yet available.
        </p>
      </div>

      {/* Radar Tuning Controls */}
      <div className="debug-panel__section">
        <h4>Radar Tuning</h4>
        {mockMode && (
          <p className="debug-panel__mock-warning">Radar tuning disabled in mock mode</p>
        )}
        <div className="debug-panel__controls">
          <SliderControl
            label="Min Speed"
            value={radarConfig.min_speed}
            min={0}
            max={50}
            unit=" mph"
            disabled={mockMode}
            onChange={(v) => onUpdateConfig({ min_speed: v })}
          />
          <SliderControl
            label="Min Magnitude"
            value={radarConfig.min_magnitude}
            min={0}
            max={2000}
            step={50}
            disabled={mockMode}
            onChange={(v) => onUpdateConfig({ min_magnitude: v })}
          />
          <SliderControl
            label="TX Power"
            value={radarConfig.transmit_power}
            min={0}
            max={7}
            disabled={mockMode}
            onChange={(v) => onUpdateConfig({ transmit_power: v })}
          />
        </div>
        <p className="debug-panel__hint">
          TX Power: 0 = max range, 7 = min range
        </p>
      </div>

      {/* Shot History */}
      {enabled && (
        <div className="debug-panel__section debug-panel__section--shots">
          <h4>Shot History (Radar + Camera)</h4>
          <p className="debug-panel__log-info">Logging to ~/openlaunch_logs/</p>
          <div className="debug-panel__shot-logs">
            {shotLogs.length === 0 ? (
              <p className="debug-panel__empty">No shots recorded yet...</p>
            ) : (
              [...shotLogs].reverse().map((log, index) => (
                <ShotLogRow key={`${log.timestamp}-${index}`} log={log} />
              ))
            )}
          </div>
        </div>
      )}

      {/* Raw Readings */}
      {enabled && (
        <div className="debug-panel__section debug-panel__section--readings">
          <h4>Raw Radar Readings</h4>

          <div className="debug-panel__labels">
            <span>Time</span>
            <span>Speed</span>
            <span>Dir</span>
            <span>Mag</span>
          </div>

          <div className="debug-panel__readings">
            {readings.length === 0 ? (
              <p className="debug-panel__empty">Waiting for readings...</p>
            ) : (
              [...readings].reverse().map((reading, index) => (
                <ReadingRow key={`${reading.timestamp}-${index}`} reading={reading} />
              ))
            )}
          </div>
        </div>
      )}

      {!enabled && (
        <div className="debug-panel__section">
          <p className="debug-panel__hint">
            Start debug mode to see raw radar readings, shot history with camera data, and log data for analysis.
          </p>
        </div>
      )}
    </div>
  );
}
