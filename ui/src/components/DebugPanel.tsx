import { memo, useState } from 'react';
import type { DebugReading, RadarConfig, DebugShotLog, CameraStatus } from '../hooks/useSocket';
import type { TriggerDiagnostic, TriggerStatus } from '../types/shot';
import { useLanguage } from '../state/useLanguage';
import type { TKey } from '../i18n/translations';
import './DebugPanel.css';

const MODE_KEYS: Record<string, TKey> = {
  'rolling-buffer': 'modeRollingBuffer',
  'mock': 'modeMock',
};

interface DebugPanelProps {
  enabled: boolean;
  readings: DebugReading[];
  shotLogs: DebugShotLog[];
  radarConfig: RadarConfig;
  cameraStatus: CameraStatus;
  mockMode: boolean;
  onToggle: () => void;
  onUpdateConfig: (config: Partial<RadarConfig>) => void;
  triggerDiagnostics: TriggerDiagnostic[];
  triggerStatus: TriggerStatus;
}

const REASON_DISPLAY: Record<string, string> = {
  accepted: 'Shot detected',
  no_response: 'No data from radar after trigger',
  parse_failed: 'Failed to parse radar data',
  no_outbound_speed: 'No outbound speed >= 15 mph',
  processing_failed: 'Failed to process capture data',
  shot_validation_failed: 'Ball speed too low for shot',
};

function formatReason(reason: string): string {
  return REASON_DISPLAY[reason] || reason;
}

function formatTimeAgo(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffSec = Math.floor((now - then) / 1000);

  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  return `${Math.floor(diffSec / 3600)}h ago`;
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

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
  const [prevValue, setPrevValue] = useState(value);
  const [dragging, setDragging] = useState(false);

  if (prevValue !== value) {
    setPrevValue(value);
    if (!dragging) {
      setLocalValue(value);
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDragging(true);
    setLocalValue(parseInt(e.target.value, 10));
  };

  const handleRelease = () => {
    setDragging(false);
    if (localValue !== value) {
      onChange(localValue);
    }
  };

  return (
    <div className={`slider-control ${disabled ? 'slider-control--disabled' : ''}`}>
      <div className="slider-control__header">
        <span className="slider-control__label">{label}</span>
        <span className="slider-control__value">
          {localValue}
          {unit}
        </span>
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
        <span>
          {min}
          {unit}
        </span>
        <span>
          {max}
          {unit}
        </span>
      </div>
    </div>
  );
}

interface TriggerRowProps {
  diag: TriggerDiagnostic;
}

const TriggerRow = memo(function TriggerRow({ diag }: TriggerRowProps) {
  return (
    <div className={`trigger-row ${diag.accepted ? 'trigger-row--accepted' : 'trigger-row--rejected'}`}>
      <div className="trigger-row__header">
        <span className="trigger-row__time">{formatTime(diag.timestamp)}</span>
        <span
          className={`trigger-row__badge ${diag.accepted ? 'trigger-row__badge--accepted' : 'trigger-row__badge--rejected'}`}
        >
          {diag.accepted ? 'HIT' : 'MISS'}
        </span>
      </div>
      <div className="trigger-row__details">
        <span className="trigger-row__reason">{formatReason(diag.reason)}</span>
        {diag.peak_outbound_mph > 0 && (
          <span className="trigger-row__speed">OUT {diag.peak_outbound_mph.toFixed(0)} mph</span>
        )}
        {diag.accepted && diag.ball_speed_mph && (
          <span className="trigger-row__ball-speed">{diag.ball_speed_mph.toFixed(0)} mph</span>
        )}
      </div>
    </div>
  );
});

function SystemStatus({ status }: { status: TriggerStatus }) {
  const { t } = useLanguage();
  return (
    <div className="debug-panel__section">
      <h4>{t('systemStatus')}</h4>
      <div className="system-status">
        <div className="system-status__item">
          <span className="system-status__label">{t('debugMode')}</span>
          <span className={`system-status__badge system-status__badge--${status.mode}`}>
            {MODE_KEYS[status.mode] ? t(MODE_KEYS[status.mode]) : status.mode}
          </span>
        </div>
        {status.trigger_type && (
          <div className="system-status__item">
            <span className="system-status__label">{t('debugTrigger')}</span>
            <span className="system-status__value">{status.trigger_type}</span>
          </div>
        )}
        <div className="system-status__item">
          <span className="system-status__label">{t('radar')}</span>
          <span
            className={`system-status__value ${status.radar_connected ? 'system-status__value--success' : 'system-status__value--error'}`}
          >
            {status.radar_connected ? t('connected') : t('disconnected')}
          </span>
        </div>
        <div className="system-status__item">
          <span className="system-status__label">{t('debugTriggers')}</span>
          <span className="system-status__value">
            <span className="system-status__counter">{status.triggers_total}</span>
            {status.triggers_total > 0 && (
              <>
                {' '}
                (<span className="system-status__counter--accepted">{status.triggers_accepted}</span>
                {' / '}
                <span className="system-status__counter--rejected">{status.triggers_rejected}</span>)
              </>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

function LastTriggerCard({ diag }: { diag: TriggerDiagnostic | null }) {
  const { t } = useLanguage();
  if (!diag) {
    return (
      <div className="debug-panel__section">
        <h4>{t('lastTrigger')}</h4>
        <p className="debug-panel__empty">{t('waitingForTrigger')}</p>
      </div>
    );
  }

  return (
    <div className="debug-panel__section">
      <h4>{t('lastTrigger')}</h4>
      <div className={`last-trigger ${diag.accepted ? 'last-trigger--accepted' : 'last-trigger--rejected'}`}>
        <div className="last-trigger__header">
          <span
            className={`last-trigger__status ${diag.accepted ? 'last-trigger__status--accepted' : 'last-trigger__status--rejected'}`}
          >
            {diag.accepted ? 'ACCEPTED' : 'REJECTED'}
          </span>
          <span className="last-trigger__time">{formatTimeAgo(diag.timestamp)}</span>
        </div>

        <div className="last-trigger__reason">{formatReason(diag.reason)}</div>

        <div className="last-trigger__data">
          <div className="last-trigger__speeds">
            <div className="last-trigger__speed-row">
              <span className="last-trigger__speed-label">Outbound</span>
              <span className="last-trigger__speed-value">
                {diag.outbound_readings} readings
                {diag.peak_outbound_mph > 0 && (
                  <>
                    , peak <strong>{diag.peak_outbound_mph.toFixed(1)} mph</strong>
                  </>
                )}
              </span>
            </div>
            <div className="last-trigger__speed-row">
              <span className="last-trigger__speed-label">Inbound</span>
              <span className="last-trigger__speed-value">
                {diag.inbound_readings} readings
                {diag.peak_inbound_mph > 0 && (
                  <>
                    , peak <strong>{diag.peak_inbound_mph.toFixed(1)} mph</strong>
                  </>
                )}
              </span>
            </div>
          </div>

          <div className="last-trigger__meta">
            {diag.latency_ms !== null && (
              <span className="last-trigger__meta-item">Latency: {diag.latency_ms.toFixed(0)}ms</span>
            )}
            {diag.response_bytes > 0 && (
              <span className="last-trigger__meta-item">Data: {(diag.response_bytes / 1024).toFixed(1)}KB</span>
            )}
            <span className="last-trigger__meta-item">Readings: {diag.total_readings}</span>
          </div>

          {diag.accepted && diag.ball_speed_mph && (
            <div className="last-trigger__shot-result">
              <div className="last-trigger__shot-item">
                <span className="last-trigger__shot-label">Ball</span>
                <span className="last-trigger__shot-value">{diag.ball_speed_mph.toFixed(1)} mph</span>
              </div>
              {diag.club_speed_mph && (
                <div className="last-trigger__shot-item">
                  <span className="last-trigger__shot-label">Club</span>
                  <span className="last-trigger__shot-value">{diag.club_speed_mph.toFixed(1)} mph</span>
                </div>
              )}
              {diag.spin_rpm && (
                <div className="last-trigger__shot-item">
                  <span className="last-trigger__shot-label">Spin</span>
                  <span className="last-trigger__shot-value">{diag.spin_rpm.toFixed(0)} rpm</span>
                </div>
              )}
              {diag.carry_yards && (
                <div className="last-trigger__shot-item">
                  <span className="last-trigger__shot-label">Carry</span>
                  <span className="last-trigger__shot-value">{diag.carry_yards.toFixed(0)} yds</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

type DebugTab = 'status' | 'history' | 'tuning';

export function DebugPanel({
  enabled,
  radarConfig,
  mockMode,
  onToggle,
  onUpdateConfig,
  triggerDiagnostics,
  triggerStatus,
}: DebugPanelProps) {
  const [activeTab, setActiveTab] = useState<DebugTab>('status');
  const { t } = useLanguage();
  const isRollingBuffer = triggerStatus.mode === 'rolling-buffer';
  const lastDiag = triggerDiagnostics.length > 0 ? triggerDiagnostics[triggerDiagnostics.length - 1] : null;

  const recentTriggers = [...triggerDiagnostics].reverse().slice(0, 20);

  return (
    <div className="debug-panel">
      <div className="debug-panel__header">
        <h3>{t('diagnostics')}</h3>
        <button
          className={`debug-record-btn ${enabled ? 'debug-record-btn--active' : ''}`}
          onClick={onToggle}
          aria-pressed={enabled}
          aria-label={enabled ? 'Stop recording raw readings' : 'Start recording raw readings'}
        >
          <span className={`debug-record-btn__dot ${enabled ? 'debug-record-btn__dot--active' : ''}`} aria-hidden="true" />
          {enabled ? t('recording') : t('record')}
        </button>
      </div>

      <div className="debug-tabs">
        <button
          className={`debug-tabs__tab ${activeTab === 'status' ? 'debug-tabs__tab--active' : ''}`}
          onClick={() => setActiveTab('status')}
        >
          {t('debugStatusTab')}
        </button>
        {isRollingBuffer && (
          <button
            className={`debug-tabs__tab ${activeTab === 'history' ? 'debug-tabs__tab--active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            {t('tabHistory')}
          </button>
        )}
        <button
          className={`debug-tabs__tab ${activeTab === 'tuning' ? 'debug-tabs__tab--active' : ''}`}
          onClick={() => setActiveTab('tuning')}
        >
          {t('debugTuningTab')}
        </button>
      </div>

      <div className="debug-panel__tab-content">
        {activeTab === 'status' && (
          <>
            <SystemStatus status={triggerStatus} />
            {isRollingBuffer && <LastTriggerCard diag={lastDiag} />}
            {!isRollingBuffer && triggerStatus.mode !== 'mock' && (
              <div className="debug-panel__section">
                <p className="debug-panel__hint">
                  Trigger diagnostics are available in rolling buffer mode. Current mode: {triggerStatus.mode}
                </p>
              </div>
            )}
          </>
        )}

        {activeTab === 'history' && isRollingBuffer && (
          <div className="debug-panel__section debug-panel__section--history">
            <h4>{t('triggerHistory')}</h4>
            <div className="trigger-history">
              {recentTriggers.length === 0 ? (
                <p className="debug-panel__empty">{t('noTriggersYet')}</p>
              ) : (
                recentTriggers.map((diag, index) => <TriggerRow key={`${diag.timestamp}-${index}`} diag={diag} />)
              )}
            </div>
          </div>
        )}

        {activeTab === 'tuning' && (
          <div className="debug-panel__section">
            <h4>{t('radarTuning')}</h4>
            {mockMode && <p className="debug-panel__mock-warning">{t('radarTuningDisabled')}</p>}
            <div className="debug-panel__controls">
              <SliderControl
                label={t('minSpeed')}
                value={radarConfig.min_speed}
                min={0}
                max={50}
                unit=" mph"
                disabled={mockMode}
                onChange={(v) => onUpdateConfig({ min_speed: v })}
              />
              <SliderControl
                label={t('minMagnitude')}
                value={radarConfig.min_magnitude}
                min={0}
                max={2000}
                step={50}
                disabled={mockMode}
                onChange={(v) => onUpdateConfig({ min_magnitude: v })}
              />
              <SliderControl
                label={t('txPower')}
                value={radarConfig.transmit_power}
                min={0}
                max={7}
                disabled={mockMode}
                onChange={(v) => onUpdateConfig({ transmit_power: v })}
              />
            </div>
            <p className="debug-panel__hint">{t('txPowerHint')}</p>
          </div>
        )}

      </div>
    </div>
  );
}
