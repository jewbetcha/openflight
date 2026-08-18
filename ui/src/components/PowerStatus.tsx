import { useState } from 'react';
import { useSystemStore } from '../stores/useSystemStore';
import type { PowerStatus as PowerStatusData } from '../types/power';
import './PowerStatus.css';

type WarningLevel = 'low' | 'critical';

function BatteryIcon({ status }: { status: PowerStatusData }) {
  const percent = Math.max(0, Math.min(100, status.battery_percent ?? 0));

  return (
    <span className="power-status__icon" aria-hidden="true">
      <span className="power-status__battery">
        <span className="power-status__fill" style={{ width: `${percent}%` }} />
      </span>
      {status.external_power ? (
        <svg className="power-status__bolt" viewBox="0 0 12 16" fill="currentColor">
          <path d="M7.2 0 1 9h4l-.6 7L11 6.4H7.1L7.2 0Z" />
        </svg>
      ) : null}
    </span>
  );
}

export function PowerIndicator({ status }: { status: PowerStatusData }) {
  const percentage = status.battery_percent === null ? '--' : `${Math.round(status.battery_percent)}%`;
  const source = status.external_power ? 'Plugged in' : 'On battery';
  const label = status.available ? `${source}, ${percentage} battery` : 'Battery status unavailable';
  const detail = status.available
    ? `${label}${status.battery_voltage_v === null ? '' : `, ${status.battery_voltage_v.toFixed(2)} volts`}`
    : status.error || label;

  return (
    <div className={`power-status power-status--${status.state}`} aria-label={label} title={detail} role="status">
      <BatteryIcon status={status} />
      <span className="power-status__percentage">{percentage}</span>
    </div>
  );
}

export function PowerWarning({ level, percentage }: { level: WarningLevel; percentage: number }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const critical = level === 'critical';
  const roundedPercentage = Math.round(percentage);
  return (
    <div className="power-warning-overlay">
      <div
        className={`power-warning power-warning--${level}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="power-warning-title"
        aria-describedby="power-warning-detail"
      >
        <div className="power-warning__battery" aria-hidden="true">
          {`${roundedPercentage}%`}
        </div>
        <div className="power-warning__content">
          <h2 id="power-warning-title">{critical ? 'Battery critically low' : 'Battery low'}</h2>
          <p id="power-warning-detail">
            {critical ? 'Connect OpenFlight to external power now.' : 'Connect OpenFlight to external power soon.'}
          </p>
        </div>
        <button type="button" onClick={() => setDismissed(true)} autoFocus>
          Dismiss
        </button>
      </div>
    </div>
  );
}

export function PowerExperience() {
  const status = useSystemStore((state) => state.powerStatus);
  if (!status) return null;

  const warningLevel: WarningLevel | null =
    status.available && !status.external_power && (status.state === 'low' || status.state === 'critical')
      ? status.state
      : null;

  return (
    <>
      <PowerIndicator status={status} />
      {warningLevel && status.battery_percent !== null ? (
        <PowerWarning key={warningLevel} level={warningLevel} percentage={status.battery_percent} />
      ) : null}
    </>
  );
}
