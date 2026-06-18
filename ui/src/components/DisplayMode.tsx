import { useState } from 'react';
import type { CameraStatus } from '../stores/useCameraStore';
import type { Shot } from '../types/shot';
import { useUnitPreference } from '../state/useUnitPreference';
import { formatDistance, formatSpeed, getDistanceUnit, getSpeedUnit } from '../utils/units';
import { getServerOrigin } from '../utils/serverOrigin';
import './DisplayMode.css';

interface DisplayModeProps {
  connected: boolean;
  cameraStatus: CameraStatus;
  latestShot: Shot | null;
  shots: Shot[];
}

interface DisplayMetric {
  label: string;
  value: string;
  unit?: string;
  detail?: string;
}

const CAMERA_STREAM_URL = `${getServerOrigin()}/camera/stream`;
const RECENT_SHOT_COUNT = 5;

function formatOptionalNumber(value: number | null, digits = 1, prefixPositive = false): string {
  if (value === null) {
    return '--';
  }

  const prefix = prefixPositive && value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(digits)}`;
}

function formatSpin(value: number | null): string {
  if (value === null) {
    return '--';
  }

  return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function buildMetrics(shot: Shot | null, unitSystem: 'imperial' | 'metric'): DisplayMetric[] {
  if (!shot) {
    return [
      { label: 'Ball Speed', value: '--', unit: getSpeedUnit(unitSystem) },
      { label: 'Carry', value: '--', unit: getDistanceUnit(unitSystem) },
      { label: 'Club Speed', value: '--', unit: getSpeedUnit(unitSystem) },
      { label: 'Smash', value: '--' },
      { label: 'Launch', value: '--', unit: 'deg' },
      { label: 'Spin', value: '--', unit: 'rpm' },
      { label: 'Club Path', value: '--', unit: 'deg' },
      { label: 'H. Launch', value: '--', unit: 'deg' },
    ];
  }

  const carryYards = shot.carry_spin_adjusted ?? shot.estimated_carry_yards;

  return [
    {
      label: 'Ball Speed',
      value: formatSpeed(shot.ball_speed_mph, unitSystem, 1),
      unit: getSpeedUnit(unitSystem),
    },
    {
      label: 'Carry',
      value: formatDistance(carryYards, unitSystem, 0),
      unit: getDistanceUnit(unitSystem),
      detail: shot.carry_spin_adjusted ? 'spin-adjusted' : undefined,
    },
    {
      label: 'Club Speed',
      value: shot.club_speed_mph === null ? '--' : formatSpeed(shot.club_speed_mph, unitSystem, 1),
      unit: shot.club_speed_mph === null ? undefined : getSpeedUnit(unitSystem),
    },
    {
      label: 'Smash',
      value: shot.smash_factor === null ? '--' : shot.smash_factor.toFixed(2),
    },
    {
      label: 'Launch',
      value: formatOptionalNumber(shot.launch_angle_vertical),
      unit: shot.launch_angle_vertical === null ? undefined : 'deg',
      detail: shot.angle_source ?? undefined,
    },
    {
      label: 'Spin',
      value: formatSpin(shot.spin_rpm),
      unit: shot.spin_rpm === null ? undefined : 'rpm',
      detail: shot.spin_quality ?? undefined,
    },
    {
      label: 'Club Path',
      value: formatOptionalNumber(shot.club_path_deg, 1, true),
      unit: shot.club_path_deg === null ? undefined : 'deg',
    },
    {
      label: 'H. Launch',
      value: formatOptionalNumber(shot.launch_angle_horizontal, 1, true),
      unit: shot.launch_angle_horizontal === null ? undefined : 'deg',
    },
  ];
}

function DisplayMetricCard({ metric, featured = false }: { metric: DisplayMetric; featured?: boolean }) {
  return (
    <div className={`display-metric ${featured ? 'display-metric--featured' : ''}`}>
      <span className="display-metric__label">{metric.label}</span>
      <span className="display-metric__value-row">
        <span className="display-metric__value">{metric.value}</span>
        {metric.unit && <span className="display-metric__unit">{metric.unit}</span>}
      </span>
      {metric.detail && <span className="display-metric__detail">{metric.detail}</span>}
    </div>
  );
}

export function DisplayMode({ connected, cameraStatus, latestShot, shots }: DisplayModeProps) {
  const [failedCameraKey, setFailedCameraKey] = useState<string | null>(null);
  const { unitSystem } = useUnitPreference();
  const metrics = buildMetrics(latestShot, unitSystem);
  const recentShots = shots.slice(-RECENT_SHOT_COUNT).reverse();
  const cameraKey = `${cameraStatus.available}-${cameraStatus.streaming}`;
  const cameraError = failedCameraKey === cameraKey;

  return (
    <main className="display-mode">
      <section className="display-mode__hero" aria-label="TV display mode">
        <div className="display-mode__camera">
          {cameraError ? (
            <div className="display-mode__camera-placeholder">
              <span>Camera stream unavailable</span>
            </div>
          ) : (
            <img
              src={CAMERA_STREAM_URL}
              alt="OpenFlight camera stream"
              className="display-mode__camera-image"
              onError={() => setFailedCameraKey(cameraKey)}
              onLoad={() => setFailedCameraKey(null)}
            />
          )}
          <div className="display-mode__status-row">
            <span className={`display-mode__status ${connected ? 'display-mode__status--online' : 'display-mode__status--offline'}`}>
              {connected ? 'Socket connected' : 'Socket disconnected'}
            </span>
            <span className={`display-mode__status ${cameraStatus.available && cameraStatus.streaming && !cameraError ? 'display-mode__status--online' : 'display-mode__status--offline'}`}>
              {cameraStatus.available && cameraStatus.streaming && !cameraError ? 'Camera stream active' : 'Camera unavailable'}
            </span>
          </div>
        </div>

        <div className="display-mode__shot-panel">
          <div className="display-mode__eyebrow">OpenFlight Display</div>
          <h1 className="display-mode__title">{latestShot ? latestShot.club : 'Ready'}</h1>
          <div className="display-mode__primary-grid">
            <DisplayMetricCard metric={metrics[0]} featured />
            <DisplayMetricCard metric={metrics[1]} featured />
          </div>
          <div className="display-mode__metrics-grid">
            {metrics.slice(2).map((metric) => (
              <DisplayMetricCard key={metric.label} metric={metric} />
            ))}
          </div>
        </div>
      </section>

      <section className="display-mode__recent" aria-label="Recent shots">
        {recentShots.length === 0 ? (
          <div className="display-mode__empty-strip">Recent shots will appear here</div>
        ) : (
          recentShots.map((shot, index) => (
            <div className="display-shot-chip" key={shot.timestamp}>
              <span className="display-shot-chip__number">#{shots.length - index}</span>
              <span className="display-shot-chip__club">{shot.club}</span>
              <span className="display-shot-chip__stat">
                {formatSpeed(shot.ball_speed_mph, unitSystem, 0)} {getSpeedUnit(unitSystem)}
              </span>
              <span className="display-shot-chip__stat">
                {formatDistance(shot.carry_spin_adjusted ?? shot.estimated_carry_yards, unitSystem, 0)} {getDistanceUnit(unitSystem)}
              </span>
            </div>
          ))
        )}
      </section>
    </main>
  );
}
