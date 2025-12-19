import { memo, useState } from 'react';
import type { DebugReading, RadarConfig } from '../hooks/useSocket';
import './DebugPanel.css';

interface DebugPanelProps {
  enabled: boolean;
  readings: DebugReading[];
  radarConfig: RadarConfig;
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

export function DebugPanel({ enabled, readings, radarConfig, mockMode, onToggle, onUpdateConfig }: DebugPanelProps) {
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

      {/* Raw Readings */}
      {enabled && (
        <div className="debug-panel__section debug-panel__section--readings">
          <h4>Raw Readings</h4>
          <p className="debug-panel__log-info">Logging to ~/openlaunch_logs/</p>

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
            Start debug mode to see raw radar readings and log data for analysis.
          </p>
        </div>
      )}
    </div>
  );
}
