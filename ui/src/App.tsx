import { useState, useEffect, lazy, Suspense } from 'react';
import { useSocket, type CameraStatus } from './hooks/useSocket';
import { ShotDisplay } from './components/ShotDisplay';
import { ConnectionStatus } from './components/ConnectionStatus';
import { ClubPicker } from './components/ClubPicker';
import { ClubSelectScreen } from './components/ClubSelectScreen';
import { BallDetectionIndicator } from './components/BallDetectionIndicator';
import { SettingsTrigger } from './components/SettingsPanel';
import { KioskSettingsPanel } from './components/KioskSettingsPanel';

// Code-split the heavy, non-default views so the kiosk's initial bundle stays
// small and boots faster on the Pi. Named exports → adapt to a default export.
const StatsView = lazy(() => import('./components/StatsView').then((m) => ({ default: m.StatsView })));
const DebugPanel = lazy(() => import('./components/DebugPanel').then((m) => ({ default: m.DebugPanel })));
const CameraFeed = lazy(() => import('./components/CameraFeed').then((m) => ({ default: m.CameraFeed })));
const HistoryView = lazy(() => import('./components/HistoryView').then((m) => ({ default: m.HistoryView })));
const Scoreboard = lazy(() => import('./components/Scoreboard').then((m) => ({ default: m.Scoreboard })));
import { useAccessibilitySettings, type A11yPrefs } from './state/useAccessibilitySettings';
import { useScoreboardRoute, useRemoteRoute } from './state/appRoutes';
import { useSpatialNavigation, useRemoteKeyBridge } from './state/useSpatialNavigation';
import { RemoteControl } from './components/RemoteControl';
import { ViewModeChooser } from './components/ViewModeChooser';
import { ViewModeProvider } from './state/ViewModeProvider';
import { useViewMode } from './state/useViewMode';
import { isSmallKioskScreen } from './state/displayDetect';
import { usePersistentBoolean } from './state/usePersistentBoolean';
import {
  LaunchDaddyProvider,
  useLaunchDaddy,
  LaunchDaddyOverlay,
  LaunchDaddyBrand,
  LaunchDaddySecretIndicator,
} from './components/LaunchDaddy';
import { ShotProvider } from './state/ShotProvider';
import { UnitPreferenceProvider } from './state/UnitPreferenceProvider';
import { LanguageProvider } from './state/LanguageProvider';
import { useLanguage } from './state/useLanguage';
import { useShotData } from './state/useShotData';
import './App.css';

type View = 'live' | 'stats' | 'history' | 'camera' | 'debug';

// Navigation icons as inline SVGs for better control
const Icons = {
  live: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
      <path d="M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  ),
  stats: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M18 20V10M12 20V4M6 20v-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  camera: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  ),
  history: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M12 8v4l3 3M3.05 11a9 9 0 1 0 .5-3M3 4v4h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  debug: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

/**
 * Shot-subscribing leaf components. Each reads shot data itself so that
 * AppContent (header, nav, chrome) does NOT subscribe and therefore does not
 * re-render on every incoming shot - the key perf win on the Raspberry Pi.
 */

/** Live shot view for the main kiosk. */
function LiveView({ mockMode, onSimulateShot }: { mockMode: boolean; onSimulateShot: () => void }) {
  const { latestShot, isNewShot, shotVersion } = useShotData();
  const { t } = useLanguage();
  return (
    <div className="live-view">
      <ShotDisplay key={shotVersion} shot={latestShot} animate={isNewShot} />
      {mockMode && (
        <button className="simulate-button" onClick={onSimulateShot}>
          {t('simulateShot')}
        </button>
      )}
    </div>
  );
}

/** Stats view wrapper - subscribes to shots on AppContent's behalf. */
function StatsSection({ onClearSession }: { onClearSession: () => void }) {
  const { shots } = useShotData();
  return <StatsView shots={shots} onClearSession={onClearSession} />;
}

/** Placeholder shown while a lazily-loaded view chunk is fetched. */
function ViewFallback() {
  return <div className="view-fallback" aria-busy="true" aria-live="polite" />;
}

/** Passive scoreboard wrapper - subscribes to shot data. */
function ScoreboardRoute({
  connected,
  cameraStatus,
  cameraToken,
  a11yPrefs,
  onA11yToggle,
}: {
  connected: boolean;
  cameraStatus: CameraStatus;
  cameraToken: string;
  a11yPrefs: A11yPrefs;
  onA11yToggle: (key: keyof A11yPrefs, value: boolean) => void;
}) {
  const { latestShot, shots } = useShotData();
  return (
    <Scoreboard
      connected={connected}
      cameraStatus={cameraStatus}
      cameraToken={cameraToken}
      latestShot={latestShot}
      shots={shots}
      a11yPrefs={a11yPrefs}
      onA11yToggle={onA11yToggle}
    />
  );
}

/** Fires the Launch-Daddy explosion on each new shot; renders nothing. */
function ShotExplosionTrigger() {
  const { isNewShot, shotVersion } = useShotData();
  const { isLaunchDaddyMode, triggerExplosion } = useLaunchDaddy();
  useEffect(() => {
    if (isNewShot && isLaunchDaddyMode) triggerExplosion();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- shotVersion drives the effect; isNewShot is only a guard
  }, [shotVersion, isLaunchDaddyMode, triggerExplosion]);
  return null;
}

function AppContent() {
  const {
    connected,
    cameraToken,
    mockMode,
    debugMode,
    debugReadings,
    debugShotLogs,
    radarConfig,
    cameraStatus,
    triggerDiagnostics,
    triggerStatus,
    remoteA11yPrefs,
    clearSession,
    setClub,
    simulateShot,
    toggleDebug,
    updateRadarConfig,
    toggleCamera,
    toggleCameraStream,
    shutdown,
    sendRemoteKey,
  } = useSocket();

  const { prefs: a11yPrefs, setPref: setA11yPref, applyRemote } = useAccessibilitySettings();
  const { t } = useLanguage();
  // The view mode (Interactive vs Scoreboard) is reactive state owned by
  // ViewModeProvider, which applies the `tv`/`low-power` <html> classes live
  // and exposes whether the user has chosen yet.
  const { isInteractive, chosen } = useViewMode();
  // Remote / keyboard D-pad navigation works in BOTH modes - a monitor can have
  // a remote too - so it is NOT gated on TV mode. The display profile only
  // changes the visual scale (10-foot vs near); navigation is always available,
  // and a visible focus ring appears as soon as a key/remote is used (see the
  // `using-dpad` handling in useSpatialNavigation + index.css).
  useSpatialNavigation(true);
  useRemoteKeyBridge(true);
  const [a11yPanelOpen, setA11yPanelOpen] = useState(false);

  // NOTE: AppContent deliberately does NOT subscribe to shot data. That keeps
  // the header/nav/chrome from re-rendering on every shot. The components that
  // actually display shots subscribe themselves (LiveView, StatsSection,
  // DisplayRoute), and ShotExplosionTrigger handles the Launch-Daddy effect.

  const [currentView, setCurrentView] = useState<View>('live');
  const [selectedClub, setSelectedClub] = useState('driver');
  // Shown on every app load so the user confirms their club before the first
  // shot (skippable, keeps the default). The /display route returns early
  // below, so this interstitial never appears in the passive TV view.
  const [showClubSelect, setShowClubSelect] = useState(true);
  const [showShutdown, setShowShutdown] = useState(false);
  const [shutdownState, setShutdownState] = useState<'idle' | 'pending' | 'done' | 'error'>('idle');
  const [showCameraTab, setShowCameraTab] = usePersistentBoolean('openflight.showCameraTab', false);
  const [showDebugTab, setShowDebugTab] = usePersistentBoolean('openflight.showDebugTab', true);
  const { isLaunchDaddyMode, isExploding, handleSecretTap } = useLaunchDaddy();
  const isScoreboardRoute = useScoreboardRoute();
  const isRemoteRoute = useRemoteRoute();

  // Apply remote a11y prefs when received from the mobile app.
  // applyRemote is a stable useCallback, so listing it as a dep is correct
  // and the effect still only fires when new remote prefs arrive.
  useEffect(() => {
    if (remoteA11yPrefs) applyRemote(remoteA11yPrefs);
  }, [remoteA11yPrefs, applyRemote]);

  // TV focus memory (Apple HIG focus engine): when a view mounts and nothing is
  // focused - at boot, or after the previously focused control unmounted on a
  // tab/interstitial change - land focus on a sensible anchor so the remote is
  // never stranded. Only acts when focus has fallen to <body>, so it never
  // steals focus from an open dialog or an already-focused control.
  useEffect(() => {
    if (!isInteractive) return;
    const id = window.setTimeout(() => {
      const active = document.activeElement;
      if (active && active !== document.body) return;
      const anchor =
        document.querySelector<HTMLElement>('.nav__button--active') ??
        document.querySelector<HTMLElement>('main button, main a[href], main [tabindex]');
      anchor?.focus();
    }, 0);
    return () => window.clearTimeout(id);
  }, [isInteractive, currentView, showClubSelect]);

  const handleClubChange = (club: string) => {
    setSelectedClub(club);
    setClub(club);
  };

  const handleToggleCameraTab = (visible: boolean) => {
    setShowCameraTab(visible);
    if (!visible && currentView === 'camera') setCurrentView('live');
  };

  const handleToggleDebugTab = (visible: boolean) => {
    setShowDebugTab(visible);
    if (!visible && currentView === 'debug') setCurrentView('live');
  };

  const handleShutdown = () => {
    setShutdownState('pending');
    shutdown().then((ok) => {
      setShutdownState(ok ? 'done' : 'error');
      if (ok) setTimeout(() => setShowShutdown(false), 2500);
    });
  };

  // The passive Scoreboard UI - shared by the dedicated /scoreboard route and
  // by Scoreboard mode on the main screen.
  const scoreboard = (
    <Suspense fallback={<ViewFallback />}>
      <ScoreboardRoute
        connected={connected}
        cameraStatus={cameraStatus}
        cameraToken={cameraToken}
        a11yPrefs={a11yPrefs}
        onA11yToggle={setA11yPref}
      />
    </Suspense>
  );

  if (isRemoteRoute) {
    return <RemoteControl sendKey={sendRemoteKey} connected={connected} />;
  }

  // The dedicated /scoreboard URL is always the scoreboard (for a second screen).
  if (isScoreboardRoute) {
    return scoreboard;
  }

  // First-run chooser is for larger external screens only - the small 7" kiosk
  // panel defaults to Interactive (it's the control surface), and the dedicated
  // /scoreboard route + /remote controller (above) never see it.
  if (!chosen && !isSmallKioskScreen()) {
    return <ViewModeChooser />;
  }

  // The Settings "Interactive mode" switch flips between the two UIs on this
  // screen: Scoreboard mode → the passive scoreboard; Interactive mode → the
  // kiosk below (bigger on an actual TV via the resolution scale ramp).
  if (!isInteractive) {
    return scoreboard;
  }

  return (
    <div className={`app ${isLaunchDaddyMode ? 'app--launch-daddy' : ''} ${isExploding ? 'app--exploding' : ''}`}>
      {showClubSelect && (
        <ClubSelectScreen
          selectedClub={selectedClub}
          onSelect={(club) => {
            handleClubChange(club);
            setShowClubSelect(false);
          }}
          onSkip={() => setShowClubSelect(false)}
        />
      )}

      {/* Launch Daddy Overlay */}
      <LaunchDaddyOverlay />
      <LaunchDaddySecretIndicator />
      {/* Subscribes to shot data and fires the explosion; renders nothing, so
          the chrome above never re-renders when a shot lands. */}
      <ShotExplosionTrigger />

      <header className="header">
        <div className="header__left">
          {/* Secret activation area - click/tap 5 times quickly */}
          <div
            className="header__secret-tap"
            onClick={handleSecretTap}
            onKeyDown={(e) => {
              // role="button" must activate on Space as well as Enter (WCAG 4.1.2).
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleSecretTap();
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="OpenFlight"
          >
            {isLaunchDaddyMode ? <LaunchDaddyBrand /> : <img className="header__logo" src="/openflightlogo.svg" alt="OpenFlight" />}
          </div>
          <ConnectionStatus connected={connected} />
        </div>
        <div className="header__controls">
          <ClubPicker selectedClub={selectedClub} onClubChange={handleClubChange} />
          <BallDetectionIndicator
            available={cameraStatus.available}
            enabled={cameraStatus.enabled}
            detected={cameraStatus.ball_detected}
            confidence={cameraStatus.ball_confidence}
            onToggle={toggleCamera}
          />
          <SettingsTrigger open={a11yPanelOpen} onClick={() => setA11yPanelOpen((o) => !o)} />
          <button
            className="power-button"
            onClick={() => { setShutdownState('idle'); setShowShutdown(true); }}
            aria-label={t('shutdownTitle')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
              <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
              <line x1="12" y1="2" x2="12" y2="12" />
            </svg>
          </button>
        </div>
      </header>

      <KioskSettingsPanel
        open={a11yPanelOpen}
        onClose={() => setA11yPanelOpen(false)}
        prefs={a11yPrefs}
        onToggle={setA11yPref}
        showCameraTab={showCameraTab}
        onToggleCameraTab={handleToggleCameraTab}
        showDebugTab={showDebugTab}
        onToggleDebugTab={handleToggleDebugTab}
      />

      {showShutdown && (
        <div className="shutdown-overlay" role="presentation">
          <div
            className="shutdown-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="shutdown-title"
          >
            {shutdownState === 'idle' && (
              <>
                <p id="shutdown-title">{t('shutdownTitle')}</p>
                <div className="shutdown-dialog__buttons">
                  <button
                    className="shutdown-dialog__confirm"
                    onClick={handleShutdown}
                    aria-label={t('shutdownConfirm')}
                  >
                    {t('shutdownConfirm')}
                  </button>
                  <button
                    className="shutdown-dialog__cancel"
                    onClick={() => setShowShutdown(false)}
                    autoFocus
                    data-modal-dismiss
                  >
                    {t('cancel')}
                  </button>
                </div>
              </>
            )}
            {shutdownState === 'pending' && (
              <p id="shutdown-title" className="shutdown-dialog__status">{t('shuttingDown')}</p>
            )}
            {shutdownState === 'done' && (
              <p id="shutdown-title" className="shutdown-dialog__status">{t('serverStopped')}</p>
            )}
            {shutdownState === 'error' && (
              <>
                <p id="shutdown-title" className="shutdown-dialog__status shutdown-dialog__status--error">
                  {t('serverUnreachable')}
                </p>
                <div className="shutdown-dialog__buttons">
                  <button className="shutdown-dialog__cancel" onClick={() => { setShowShutdown(false); setShutdownState('idle'); }} data-modal-dismiss>
                    {t('close')}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <nav className="nav" aria-label={t('a11yMainNav')}>
        <button
          className={`nav__button ${currentView === 'live' ? 'nav__button--active' : ''}`}
          onClick={() => setCurrentView('live')}
          aria-current={currentView === 'live' ? 'page' : undefined}
        >
          {Icons.live}
          <span>{t('tabLive')}</span>
        </button>
        <button
          className={`nav__button ${currentView === 'stats' ? 'nav__button--active' : ''}`}
          onClick={() => setCurrentView('stats')}
          aria-current={currentView === 'stats' ? 'page' : undefined}
        >
          {Icons.stats}
          <span>{t('tabStats')}</span>
        </button>
        <button
          className={`nav__button ${currentView === 'history' ? 'nav__button--active' : ''}`}
          onClick={() => setCurrentView('history')}
          aria-current={currentView === 'history' ? 'page' : undefined}
        >
          {Icons.history}
          <span>{t('tabHistory')}</span>
        </button>
        {showCameraTab && (
          <button
            className={`nav__button ${currentView === 'camera' ? 'nav__button--active' : ''} ${cameraStatus.streaming ? 'nav__button--streaming' : ''}`}
            onClick={() => setCurrentView('camera')}
            aria-current={currentView === 'camera' ? 'page' : undefined}
            aria-label={t('tabCamera')}
          >
            {Icons.camera}
            <span aria-hidden="true">{t('tabCamera')}</span>
            {cameraStatus.ball_detected && <span className="nav__ball-dot" aria-hidden="true" />}
          </button>
        )}
        {showDebugTab && (
          <button
            className={`nav__button ${currentView === 'debug' ? 'nav__button--active' : ''} ${debugMode ? 'nav__button--recording' : ''}`}
            onClick={() => setCurrentView('debug')}
            aria-current={currentView === 'debug' ? 'page' : undefined}
            aria-label={t('tabDebug')}
          >
            {Icons.debug}
            <span aria-hidden="true">{t('tabDebug')}</span>
            {debugMode && <span className="nav__recording-dot" aria-hidden="true" />}
          </button>
        )}
      </nav>

      <main className="main">
        <Suspense fallback={<ViewFallback />}>
          {currentView === 'live' && <LiveView mockMode={mockMode} onSimulateShot={simulateShot} />}
          {currentView === 'stats' && <StatsSection onClearSession={clearSession} />}
          {currentView === 'history' && <HistoryView />}
          {currentView === 'camera' && (
            <CameraFeed cameraStatus={cameraStatus} onToggleCamera={toggleCamera} onToggleStream={toggleCameraStream} streamToken={cameraToken} />
          )}
          {currentView === 'debug' && showDebugTab && (
            <DebugPanel
              enabled={debugMode}
              readings={debugReadings}
              shotLogs={debugShotLogs}
              radarConfig={radarConfig}
              cameraStatus={cameraStatus}
              mockMode={mockMode}
              onToggle={toggleDebug}
              onUpdateConfig={updateRadarConfig}
              triggerDiagnostics={triggerDiagnostics}
              triggerStatus={triggerStatus}
            />
          )}
        </Suspense>
      </main>
    </div>
  );
}

function App() {
  return (
    <LaunchDaddyProvider>
      <UnitPreferenceProvider>
        <LanguageProvider>
          <ShotProvider>
            <ViewModeProvider>
              <AppContent />
            </ViewModeProvider>
          </ShotProvider>
        </LanguageProvider>
      </UnitPreferenceProvider>
    </LaunchDaddyProvider>
  );
}

export default App;
