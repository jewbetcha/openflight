import { useState, useEffect } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useSocket } from './hooks/useSocket';
import { useSystemStore } from './stores/useSystemStore';
import { useShotStore } from './stores/useShotStore';
import { useCameraStore } from './stores/useCameraStore';
import { useDebugStore } from './stores/useDebugStore';
import { usePlayerStore } from './stores/usePlayerStore';
import { useHeroMetricStore } from './stores/useHeroMetricStore';
import { useCameraReplayController } from './hooks/useCameraReplayController';
import { socketService } from './services/socketService';
import { shouldEchoSelectionToServer } from './services/playerSocketSync';
import { DebugPanel } from './components/DebugPanel';
import { DisplayMode } from './components/DisplayMode';
import { SimShotBadges } from './components/SimShotBadges';
import { ShotProcessingArea } from './components/ShotProcessingArea';
import { ShutdownDialog, type ShutdownState } from './components/ShutdownDialog';
import { CameraReplayDialog } from './components/CameraReplayDialog';
import {
  CameraPanel,
  LivePanel,
  AddPlayerDialog,
  ClearSessionDialog,
  SimulateBubble,
  MenuSheet,
  PanelFooter,
  PanelHeader,
  PanelAction,
  PickerOverlay,
  PlayersPanel,
  ShotsPanel,
  StatsPanel,
  clubSections,
  trainingImplementSections,
  type PanelView,
} from './components/panel';
import { shouldEnableLiveBallWarning } from './components/panel/liveMetrics';
import { filterShotsByPlayer } from './types/shot';
import { getClubName } from './data/clubs';
import { getTrainingImplementLabel } from './data/trainingImplements';
import { unlockAudioCue } from './utils/audioCue';
import { useLaunchDaddy, LaunchDaddyOverlay, LaunchDaddyBrand } from './components/LaunchDaddy';

import { useI18n } from './i18n/useI18n';
import './components/panel/panel.css';

function AppContent() {
  const { t } = useI18n();
  const { shutdown } = useSocket();
  const { connected, mockMode, debugMode, latestSimShots, serverClub } = useSystemStore(
    useShallow((state) => ({
      connected: state.connected,
      mockMode: state.mockMode,
      debugMode: state.debugMode,
      latestSimShots: state.latestSimShots,
      serverClub: state.serverClub,
    }))
  );
  const { latestShot, shots, isNewShot, shotProcessingPhase, shotVersion } = useShotStore(
    useShallow((state) => ({
      latestShot: state.latestShot,
      shots: state.shots,
      isNewShot: state.isNewShot,
      shotProcessingPhase: state.shotProcessingPhase,
      shotVersion: state.shotVersion,
    }))
  );
  const { cameraStatus, captureSettings, captureSettingsError } = useCameraStore(
    useShallow((state) => ({
      cameraStatus: state.cameraStatus,
      captureSettings: state.captureSettings,
      captureSettingsError: state.captureSettingsError,
    }))
  );
  const { selectedPlayer, players, selectPlayer, addPlayer, removePlayer } = usePlayerStore(
    useShallow((state) => ({
      selectedPlayer: state.selectedPlayer,
      players: state.players,
      selectPlayer: state.selectPlayer,
      addPlayer: state.addPlayer,
      removePlayer: state.removePlayer,
    }))
  );
  const serverPlayerName = useSystemStore((state) => state.serverPlayerName);
  const { heroMetricId, setHeroMetricId } = useHeroMetricStore(
    useShallow((state) => ({ heroMetricId: state.heroMetricId, setHeroMetricId: state.setHeroMetricId }))
  );
  const {
    debugReadings,
    debugShotLogs,
    radarConfig,
    triggerDiagnostics,
    triggerStatus,
    iwr6843Alert,
    dismissIWR6843Alert,
  } = useDebugStore(
    useShallow((state) => ({
      debugReadings: state.debugReadings,
      debugShotLogs: state.debugShotLogs,
      radarConfig: state.radarConfig,
      triggerDiagnostics: state.triggerDiagnostics,
      triggerStatus: state.triggerStatus,
      iwr6843Alert: state.iwr6843Alert,
      dismissIWR6843Alert: state.dismissIWR6843Alert,
    }))
  );

  const [currentView, setCurrentView] = useState<PanelView>('live');
  const [selectedClub, setSelectedClub] = useState('driver');
  const [selectedTrainingImplement, setSelectedTrainingImplement] = useState('driver');
  const [menuOpen, setMenuOpen] = useState(false);
  const [showShutdown, setShowShutdown] = useState(false);
  const [shutdownState, setShutdownState] = useState<ShutdownState>('confirm');
  // Open on every app load so the user confirms their club before the first
  // shot; dismissing keeps the default. The /display route returns early below,
  // so this never appears in the passive TV view.
  const [pickerOpen, setPickerOpen] = useState(true);
  const [addPlayerOpen, setAddPlayerOpen] = useState(false);
  const [newPlayerName, setNewPlayerName] = useState('');
  const [clearSessionOpen, setClearSessionOpen] = useState(false);
  const { activeReplay, openReplay, closeReplay, reportPlaybackError } = useCameraReplayController();

  // Reflect a server-pushed club change (e.g. the club changed in the connected
  // simulator) locally without echoing back. Done during render (React's "adjust
  // state when an input changes" pattern) rather than in an effect.
  const [appliedServerClub, setAppliedServerClub] = useState<string | null>(null);
  if (serverClub && serverClub !== appliedServerClub) {
    setAppliedServerClub(serverClub);
    setSelectedClub(serverClub);
  }
  // Same pattern for a server-pushed player change. This used to live in
  // PlayerPicker, which the menu sheet replaced.
  const [appliedServerPlayer, setAppliedServerPlayer] = useState<string | null>(null);
  if (serverPlayerName && serverPlayerName !== appliedServerPlayer) {
    setAppliedServerPlayer(serverPlayerName);
    if (serverPlayerName !== selectedPlayer) {
      selectPlayer(serverPlayerName);
    }
  }

  const { isLaunchDaddyMode, isExploding, triggerExplosion } = useLaunchDaddy();
  const isDisplayRoute = typeof window !== 'undefined' && window.location.pathname.replace(/\/$/, '') === '/display';
  const isSwingSpeedMode = triggerStatus.mode === 'swing-speed';
  const activeImplementLabel = isSwingSpeedMode
    ? getTrainingImplementLabel(selectedTrainingImplement)
    : getClubName(selectedClub);

  // Push the local player to the server once connected, so a reload restores it.
  // Do not re-emit when selectedPlayer changes: that echoes player_changed back
  // as set_player and races with the connect-time session_state snapshot.
  useEffect(() => {
    if (!connected || !shouldEchoSelectionToServer('became-connected')) return;
    socketService.setPlayer(usePlayerStore.getState().selectedPlayer);
  }, [connected]);

  useEffect(() => {
    return socketService.onSessionCleared(() => {
      setClearSessionOpen(false);
      setCurrentView('live');
    });
  }, []);

  // Trigger explosion when a new shot is detected in Launch Daddy mode
  useEffect(() => {
    if (isNewShot && isLaunchDaddyMode) {
      triggerExplosion();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- shotVersion triggers the effect; isNewShot is only a guard
  }, [shotVersion, isLaunchDaddyMode, triggerExplosion]);

  useEffect(() => {
    const unlock = () => unlockAudioCue();
    window.addEventListener('pointerdown', unlock, { once: true });
    window.addEventListener('keydown', unlock, { once: true });

    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
    };
  }, []);

  const handleSelectPlayer = (playerName: string) => {
    selectPlayer(playerName);
    socketService.setPlayer(playerName);
    setCurrentView('live');
  };

  const handleRemovePlayer = (playerName: string) => {
    if (playerName === usePlayerStore.getState().selectedPlayer) return;
    removePlayer(playerName);
  };

  const handleAddPlayer = () => {
    if (!newPlayerName.trim()) return;
    const playerName = addPlayer(newPlayerName);
    socketService.setPlayer(playerName);
    setNewPlayerName('');
    setAddPlayerOpen(false);
  };

  const handlePickerSelect = (id: string) => {
    if (isSwingSpeedMode) {
      setSelectedTrainingImplement(id);
      socketService.setTrainingImplement(id);
    } else {
      setSelectedClub(id);
      socketService.setClub(id);
    }
    setPickerOpen(false);
  };

  const handleShutdown = async () => {
    setShutdownState('pending');
    try {
      await shutdown();
    } catch {
      setShutdownState('error');
    }
  };

  const closeShutdown = () => {
    setShowShutdown(false);
    setShutdownState('confirm');
  };

  const playerShots = filterShotsByPlayer(shots, selectedPlayer);
  const playerLatestShot = playerShots[playerShots.length - 1] ?? null;
  const playerIsNewShot = Boolean(
    isNewShot && latestShot && playerLatestShot && latestShot.timestamp === playerLatestShot.timestamp
  );

  if (isDisplayRoute) {
    return <DisplayMode connected={connected} cameraStatus={cameraStatus} latestShot={latestShot} shots={shots} />;
  }

  const changeClubAction = (
    <PanelAction onClick={() => setPickerOpen(true)}>
      {isSwingSpeedMode ? t('app.changeImplement') : t('app.changeClub')}
    </PanelAction>
  );
  const latestReplay = playerLatestShot?.camera_replay;

  const liveHeaderActions = (
    <>
      {latestReplay ? (
        <PanelAction variant="secondary" onClick={() => openReplay(latestReplay)}>
          {t('replay.open')}
        </PanelAction>
      ) : null}
      {changeClubAction}
    </>
  );

  const addPlayerAction = <PanelAction onClick={() => setAddPlayerOpen(true)}>{t('menu.addPlayer')}</PanelAction>;

  const clearSessionAction = (
    <PanelAction variant="danger" onClick={() => setClearSessionOpen(true)}>
      {t('app.clearSession')}
    </PanelAction>
  );

  const debugRecordAction = (
    <PanelAction variant="secondary" onClick={() => socketService.toggleDebug()}>
      {debugMode ? t('app.stopRecording') : t('app.record')}
    </PanelAction>
  );

  return (
    <div className={`panel-app ${isLaunchDaddyMode ? 'app--launch-daddy' : ''} ${isExploding ? 'app--exploding' : ''}`}>
      <LaunchDaddyOverlay />

      {iwr6843Alert && (
        <div className="iwr-alert" role="alert">
          <div>
            <strong>{t('live.tiRadarFailed')}</strong>
            <span>{t('live.tiRadarDetail', { reason: iwr6843Alert.reason })}</span>
          </div>
          <button type="button" onClick={dismissIWR6843Alert} aria-label={t('live.dismissAlert')}>
            {t('live.dismiss')}
          </button>
        </div>
      )}

      {showShutdown ? (
        <ShutdownDialog state={shutdownState} onConfirm={handleShutdown} onCancel={closeShutdown} />
      ) : null}

      {activeReplay ? (
        <CameraReplayDialog
          replay={activeReplay.replay}
          state={activeReplay.state}
          onClose={closeReplay}
          onRetry={() => openReplay(activeReplay.replay)}
          onPlaybackError={reportPlaybackError}
        />
      ) : null}

      <main className="panel-app__main">
        {currentView === 'live' && (
          <>
            <ShotProcessingArea phase={shotProcessingPhase}>
              <LivePanel
                key={shotVersion}
                shot={playerLatestShot}
                shots={shots}
                playerName={selectedPlayer}
                clubLabel={activeImplementLabel}
                activeTrainingImplement={isSwingSpeedMode ? selectedTrainingImplement : undefined}
                selectedMetricId={heroMetricId}
                onSelectMetric={setHeroMetricId}
                isNewShot={playerIsNewShot}
                ballDetectionEnabled={shouldEnableLiveBallWarning(currentView, cameraStatus)}
                ballDetected={cameraStatus.ball_detected}
                headerAction={liveHeaderActions}
              />
            </ShotProcessingArea>
            {debugMode && <SimShotBadges latestSimShots={latestSimShots} />}
          </>
        )}
        {currentView === 'players' && (
          <PlayersPanel
            players={players}
            selectedPlayer={selectedPlayer}
            shots={shots}
            onSelectPlayer={handleSelectPlayer}
            onRemovePlayer={handleRemovePlayer}
            headerAction={addPlayerAction}
          />
        )}
        {currentView === 'stats' && (
          <StatsPanel
            shots={shots}
            activeClub={selectedClub}
            playerName={selectedPlayer}
            headerAction={clearSessionAction}
          />
        )}
        {currentView === 'shots' && (
          <ShotsPanel
            shots={shots}
            playerName={selectedPlayer}
            clubLabel={activeImplementLabel}
            onDeleteShot={(timestamp) => socketService.deleteShot(timestamp)}
            onReplayShot={(shot) => {
              if (shot.camera_replay) openReplay(shot.camera_replay);
            }}
          />
        )}
        {currentView === 'camera' && (
          <CameraPanel
            cameraStatus={cameraStatus}
            clubLabel={activeImplementLabel}
            captureSettings={captureSettings}
            captureSettingsError={captureSettingsError}
            onToggleCamera={() => socketService.toggleCamera()}
            onToggleStream={() => socketService.toggleCameraStream()}
            onUpdateCaptureSettings={(settings) => socketService.setCameraCaptureSettings(settings)}
          />
        )}
        {currentView === 'debug' && (
          <div className="panel">
            <PanelHeader
              title={t('nav.debug')}
              subtitle={debugMode ? t('app.debugRecording') : t('app.debugIdle')}
              actions={debugRecordAction}
            />
            <div className="panel__body panel-app__debug">
              <DebugPanel
                enabled={debugMode}
                readings={debugReadings}
                shotLogs={debugShotLogs}
                radarConfig={radarConfig}
                cameraStatus={cameraStatus}
                mockMode={mockMode}
                onToggle={() => socketService.toggleDebug()}
                onUpdateConfig={(config) => socketService.setRadarConfig(config)}
                triggerDiagnostics={triggerDiagnostics}
                triggerStatus={triggerStatus}
              />
            </div>
          </div>
        )}
        {mockMode && currentView === 'live' ? (
          <SimulateBubble
            label={isSwingSpeedMode ? t('app.simulateSwing') : t('app.simulateShot')}
            onSimulate={() => socketService.simulateShot()}
          />
        ) : null}
      </main>

      {/*
       * Overlays sit outside <main> so they cover the footer too, matching how
       * 6a draws them over the whole card.
       */}
      {menuOpen ? (
        <MenuSheet
          onClose={() => setMenuOpen(false)}
          onShutdown={() => {
            setMenuOpen(false);
            setShutdownState('confirm');
            setShowShutdown(true);
          }}
        />
      ) : null}

      {addPlayerOpen ? (
        <AddPlayerDialog
          name={newPlayerName}
          onChange={setNewPlayerName}
          onAdd={handleAddPlayer}
          onCancel={() => {
            setNewPlayerName('');
            setAddPlayerOpen(false);
          }}
        />
      ) : null}

      {clearSessionOpen ? (
        <ClearSessionDialog
          playerName={selectedPlayer}
          onConfirm={() => socketService.clearSession(selectedPlayer)}
          onCancel={() => setClearSessionOpen(false)}
        />
      ) : null}

      {pickerOpen ? (
        <PickerOverlay
          title={isSwingSpeedMode ? t('app.selectImplement') : t('app.selectClub')}
          selectedId={isSwingSpeedMode ? selectedTrainingImplement : selectedClub}
          sections={isSwingSpeedMode ? trainingImplementSections() : clubSections()}
          onSelect={handlePickerSelect}
          onClose={() => setPickerOpen(false)}
          wide={isSwingSpeedMode}
        />
      ) : null}

      <PanelFooter
        currentView={currentView}
        onChangeView={setCurrentView}
        onOpenMenu={() => setMenuOpen((open) => !open)}
        menuOpen={menuOpen}
        shotCount={playerShots.length}
        cameraStreaming={cameraStatus.streaming}
        ballDetected={cameraStatus.ball_detected}
        debugRecording={debugMode}
        brand={isLaunchDaddyMode ? <LaunchDaddyBrand /> : undefined}
        onShutdown={() => {
          setShutdownState('confirm');
          setShowShutdown(true);
        }}
      />
    </div>
  );
}

function App() {
  return <AppContent />;
}

export default App;
