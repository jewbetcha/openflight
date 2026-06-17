import { useState } from 'react';
import type { CameraStatus } from '../hooks/useSocket';
import type { Shot } from '../types/shot';
import { useUnitPreference } from '../state/useUnitPreference';
import { useLanguage } from '../state/useLanguage';
import { formatDistance, formatSpeed, getDistanceUnit, getSpeedUnit } from '../utils/units';
import type { Quality } from '../utils/shotQuality';
import { PLACEHOLDER, fmtSigned, fmtSpin, shapeKeyFromSpinAxis } from '../utils/shotFormat';
import { directionalLabels, getShotQualities, magnitudeLabels, type QualityLabels } from '../utils/shotMetrics';
import { ConfidenceDots } from './ConfidenceDots';
import { DisplayShotVisualizer } from './DisplayShotVisualizer';
import { SpeedGauge } from './SpeedGauge';
import { getGaugeMax, getClubHeadGaugeMax } from '../utils/gaugeRanges';
import { SettingsPanel, SettingsTrigger } from './SettingsPanel';
import type { A11yPrefs } from '../state/useAccessibilitySettings';
import { getServerOrigin } from '../utils/serverOrigin';
import './Scoreboard.css';

interface ScoreboardProps {
  connected: boolean;
  cameraStatus: CameraStatus;
  latestShot: Shot | null;
  shots: Shot[];
  /** Accessibility prefs + setter, shared with the kiosk so settings carry over. */
  a11yPrefs: A11yPrefs;
  onA11yToggle: (key: keyof A11yPrefs, value: boolean) => void;
  /** MJPEG stream auth token (only delivered to localhost clients by the server). */
  cameraToken?: string;
}

const RECENT_SHOT_COUNT = 5;

/** Spoken form of a unit symbol so a screen reader doesn't read "°" literally. */
function unitSpoken(unit: string): string {
  if (unit === '°') return 'degrees';
  if (unit === 'rpm') return 'RPM';
  return unit;
}

/** One uniform tile in the /display grid, with optional kiosk-style confidence dots. */
function DisplayTile({
  label,
  value,
  unit,
  detail,
  quality = null,
  qualityLabels,
  gold = false,
}: {
  label: string;
  value: string;
  unit?: string;
  detail?: string;
  quality?: Quality | null;
  qualityLabels?: QualityLabels;
  gold?: boolean;
}) {
  // Compose one accessible name so the tile is a single, coherent SR stop
  // ("Est Carry: 245 yards, spin adjusted"). role="img" makes VoiceOver read
  // the label as one phrase and never dive into the children (a non-focusable
  // role="group" can be skipped entirely). Inner content is hidden from AT.
  const spokenValue =
    value === PLACEHOLDER ? 'no data' : `${value}${unit ? ` ${unitSpoken(unit)}` : ''}`;
  const spoken =
    `${label}: ${spokenValue}` +
    (detail ? `, ${detail}` : '') +
    (quality && qualityLabels ? `, ${qualityLabels[quality]}` : '');
  return (
    <div className={`display-metric${gold ? ' display-metric--gold' : ''}`} role="img" aria-label={spoken}>
      <span className="display-metric__label" aria-hidden="true">{label}</span>
      <span className="display-metric__value-row" aria-hidden="true">
        <span className="display-metric__value">{value}</span>
        {unit && (
          <span className={`display-metric__unit${unit === '°' ? ' display-metric__unit--degree' : ''}`}>
            {unit}
          </span>
        )}
      </span>
      {detail && <span className="display-metric__detail" aria-hidden="true">{detail}</span>}
      {quality && qualityLabels && (
        <span aria-hidden="true">
          <ConfidenceDots quality={quality} labels={qualityLabels} scope="display" />
        </span>
      )}
    </div>
  );
}

export function Scoreboard({ connected, cameraStatus, latestShot, shots, a11yPrefs, onA11yToggle, cameraToken }: ScoreboardProps) {
  const [failedCameraKey, setFailedCameraKey] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { speedUnit, distanceUnit } = useUnitPreference();
  const { t } = useLanguage();
  const recentShots = shots.slice(-RECENT_SHOT_COUNT).reverse();
  const cameraKey = `${cameraStatus.available}-${cameraStatus.streaming}`;
  const cameraError = failedCameraKey === cameraKey;
  // Only hold an MJPEG connection open when the camera is actually live; when
  // it isn't, the camera frame shows the animated shot visualizer instead.
  const cameraLive = cameraStatus.available && cameraStatus.streaming && !cameraError;
  // Mirror CameraFeed: only a localhost client is handed a token; remote TVs
  // get none and the stream 401s (by design), falling back to the visualizer.
  const cameraStreamUrl = cameraToken
    ? `${getServerOrigin()}/camera/stream?token=${encodeURIComponent(cameraToken)}`
    : `${getServerOrigin()}/camera/stream`;

  // Metric grid derivations (kiosk-parity gauges + confidence indicators)
  const shot = latestShot;
  const sLabel = getSpeedUnit(speedUnit);
  const dLabel = getDistanceUnit(distanceUnit);
  // All quality + formatting derive from the shared modules so the /display
  // scoreboard stays in lock-step with the kiosk live view.
  const qualities = shot ? getShotQualities(shot) : null;
  // Magnitude metrics read Low/Perfect/High; directional metrics read Left/Perfect/Right.
  const magLabels: QualityLabels = magnitudeLabels(t);
  const dirLabels: QualityLabels = directionalLabels(t);
  const carryYards = shot ? (shot.carry_spin_adjusted ?? shot.estimated_carry_yards) : null;
  // Shot shape from spin axis (kiosk parity): drives the "ball · <shape>" line.
  const shapeKey = shapeKeyFromSpinAxis(shot?.spin_axis_deg);
  const spinDir = shapeKey ? t(shapeKey) : null;

  // Recent-shot chips are informational (no action), so they're intentionally
  // not in the focus order. Remote D-pad navigation across actual controls is
  // handled globally by useSpatialNavigation in the app shell.

  return (
    <main className="display-mode">
      <div className="display-mode__settings">
        <SettingsTrigger open={settingsOpen} onClick={() => setSettingsOpen((o) => !o)} />
      </div>
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        prefs={a11yPrefs}
        onToggle={onA11yToggle}
      />

      {/* Stable page heading (the visible club title changes per shot, so it's
          an <h2> below, not the page <h1>). */}
      <h1 className="sr-only">{`OpenFlight ${t('vmScoreboard')}`}</h1>
      {/* The ONLY live region: one concise sentence per shot, so a TV screen
          reader isn't talked over by a 40-word re-read of the whole grid. */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {shot
          ? `${shot.club}: ${t('estCarry')} ${
              carryYards != null ? `${formatDistance(carryYards, distanceUnit, 0)} ${dLabel}` : ''
            }, ${t('ballSpeed')} ${formatSpeed(shot.ball_speed_mph, speedUnit, 0)} ${sLabel}` +
            // Zero-width toggle (flips each shot) so two identical summaries
            // (same club + rounded values) still register as a change and
            // re-announce. SRs speak it as nothing.
            (shots.length % 2 ? '​' : '')
          : ''}
      </div>

      <section className="display-mode__hero" aria-label={t('vmScoreboard')}>
        <div className="display-mode__camera">
          {cameraLive ? (
            <img
              src={cameraStreamUrl}
              alt=""
              className="display-mode__camera-image"
              onError={() => setFailedCameraKey(cameraKey)}
              onLoad={() => setFailedCameraKey(null)}
            />
          ) : (
            <DisplayShotVisualizer
              shots={shots}
              latestShot={latestShot}
              distUnit={distanceUnit}
              reduceMotion={a11yPrefs.reduceMotion}
            />
          )}
          {/* Not a live region - only the concise shot summary above announces,
              so connection/camera changes don't clobber it (one polite owner). */}
          <div className="display-mode__status-row">
            <span className={`display-mode__status ${connected ? 'display-mode__status--online' : 'display-mode__status--offline'}`}>
              {connected ? t('socketConnected') : t('socketDisconnected')}
            </span>
            <span className={`display-mode__status ${cameraLive ? 'display-mode__status--online' : 'display-mode__status--offline'}`}>
              {cameraLive ? t('cameraStreamActive') : t('cameraUnavailable')}
            </span>
          </div>
        </div>

        {/* Not a live region - the concise sr-only summary above is the single
            announcement; the full grid stays navigable on demand. */}
        <div className="display-mode__shot-panel">
          <img
            className="display-mode__logo"
            src="/openflighttransparentlogo.png"
            alt=""
            aria-hidden="true"
          />
          <h2 className="display-mode__title">{shot ? shot.club : t('displayReady')}</h2>
          <div className="display-mode__grid">
            {/* Row 1 - Est. Carry · Est. Total */}
            <DisplayTile
              gold
              label={t('estCarry')}
              value={carryYards != null ? formatDistance(carryYards, distanceUnit, 0) : PLACEHOLDER}
              unit={carryYards != null ? dLabel : undefined}
              detail={shot?.carry_spin_adjusted ? t('spinAdj') : undefined}
            />
            <DisplayTile
              gold
              label={t('totalDist')}
              value={shot?.total_distance_yards != null ? formatDistance(shot.total_distance_yards, distanceUnit, 0) : PLACEHOLDER}
              unit={shot?.total_distance_yards != null ? dLabel : undefined}
            />

            {/* Row 2 - Ball Speed (gauge) · Club Speed (gauge) */}
            {shot ? (
              <div className="display-metric display-metric--gauge display-metric--gold">
                <SpeedGauge
                  speedMph={shot.ball_speed_mph}
                  gaugeMax={getGaugeMax(shot.club)}
                  label={t('ballSpeed')}
                  displayValue={formatSpeed(shot.ball_speed_mph, speedUnit, 1)}
                  unit={sLabel}
                />
              </div>
            ) : (
              <DisplayTile gold label={t('ballSpeed')} value={PLACEHOLDER} unit={sLabel} />
            )}
            {shot && shot.club_speed_mph != null ? (
              <div className="display-metric display-metric--gauge display-metric--gold">
                <SpeedGauge
                  speedMph={shot.club_speed_mph}
                  gaugeMax={getClubHeadGaugeMax(shot.club)}
                  label={t('clubSpeed')}
                  displayValue={formatSpeed(shot.club_speed_mph, speedUnit, 1)}
                  unit={sLabel}
                />
              </div>
            ) : (
              <DisplayTile gold label={t('clubSpeed')} value={PLACEHOLDER} unit={sLabel} />
            )}

            {/* Row 3 - V. Launch · H. Launch */}
            <DisplayTile
              label={t('vLaunch')}
              value={shot?.launch_angle_vertical != null ? shot.launch_angle_vertical.toFixed(1) : PLACEHOLDER}
              unit={shot?.launch_angle_vertical != null ? '°' : undefined}
              quality={qualities?.vLaunch ?? null}
              qualityLabels={magLabels}
            />
            <DisplayTile
              label={t('hLaunch')}
              value={fmtSigned(shot?.launch_angle_horizontal)}
              unit={shot?.launch_angle_horizontal != null ? '°' : undefined}
              quality={qualities?.hLaunch ?? null}
              qualityLabels={magLabels}
            />

            {/* Row 4 - Club Path · Club AoA */}
            <DisplayTile
              label={t('clubPath')}
              value={fmtSigned(shot?.club_path_deg)}
              unit={shot?.club_path_deg != null ? '°' : undefined}
              quality={qualities?.clubPath ?? null}
              qualityLabels={dirLabels}
            />
            <DisplayTile
              label={t('clubAoA')}
              value={shot?.club_angle_deg != null ? shot.club_angle_deg.toFixed(1) : PLACEHOLDER}
              unit={shot?.club_angle_deg != null ? '°' : undefined}
              quality={qualities?.aoa ?? null}
              qualityLabels={magLabels}
            />

            {/* Row 5 - Spin Rate · Spin Axis */}
            <DisplayTile
              label={t('spinRate')}
              value={fmtSpin(shot?.spin_rpm)}
              unit={shot?.spin_rpm != null ? 'rpm' : undefined}
              quality={qualities?.spin ?? null}
              qualityLabels={magLabels}
            />
            <DisplayTile
              label={t('spinAxis')}
              value={fmtSigned(shot?.spin_axis_deg)}
              unit={shot?.spin_axis_deg != null ? '°' : undefined}
              detail={spinDir ? `${t('ball')} · ${spinDir}` : undefined}
            />
          </div>
        </div>
      </section>

      <section className="display-mode__recent" aria-label={t('recentShots')}>
        <h2 className="sr-only">{t('recentShots')}</h2>
        {recentShots.length === 0 ? (
          <div className="display-mode__empty-strip">{t('displayRecentEmpty')}</div>
        ) : (
          recentShots.map((shot, index) => (
            // role="img" + one composed aria-label = a single reliable SR stop;
            // inner spans hidden so browse-mode SRs don't re-read each fragment.
            <div
              className="display-shot-chip"
              role="img"
              key={shot.timestamp}
              aria-label={`${t('shot')} ${shots.length - index}: ${shot.club}, ${formatSpeed(shot.ball_speed_mph, speedUnit, 0)} ${getSpeedUnit(speedUnit)}`}
            >
              <span className="display-shot-chip__number" aria-hidden="true">#{shots.length - index}</span>
              <span className="display-shot-chip__club" aria-hidden="true">{shot.club}</span>
              <span className="display-shot-chip__stat" aria-hidden="true">
                {formatSpeed(shot.ball_speed_mph, speedUnit, 0)} {getSpeedUnit(speedUnit)}
              </span>
              <span className="display-shot-chip__stat" aria-hidden="true">
                {formatDistance(shot.carry_spin_adjusted ?? shot.estimated_carry_yards, distanceUnit, 0)} {getDistanceUnit(distanceUnit)}
              </span>
            </div>
          ))
        )}
      </section>
    </main>
  );
}
