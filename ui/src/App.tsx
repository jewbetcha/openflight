import { useState, useEffect } from "react";
import { useSocket } from "./hooks/useSocket";
import { ShotDisplay } from "./components/ShotDisplay";
import { StatsView } from "./components/StatsView";
import { ShotList } from "./components/ShotList";
import { DebugPanel } from "./components/DebugPanel";
import { CameraFeed } from "./components/CameraFeed";
import { ConnectionStatus } from "./components/ConnectionStatus";
import { ClubPicker } from "./components/ClubPicker";
import { BallDetectionIndicator } from "./components/BallDetectionIndicator";
import {
  LaunchDaddyProvider,
  useLaunchDaddy,
  LaunchDaddyOverlay,
  LaunchDaddyBrand,
  LaunchDaddySecretIndicator,
} from "./components/LaunchDaddy";
import "./App.css";

type View = "live" | "stats" | "shots" | "camera" | "debug";

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
      <path
        d="M18 20V10M12 20V4M6 20v-6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  shots: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path
        d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  camera: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  ),
  debug: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path
        d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
};

function AppContent() {
  const {
    connected,
    mockMode,
    debugMode,
    debugReadings,
    debugShotLogs,
    radarConfig,
    latestShot,
    shots,
    cameraStatus,
    clearSession,
    setClub,
    simulateShot,
    toggleDebug,
    updateRadarConfig,
    toggleCamera,
    toggleCameraStream,
  } = useSocket();
  const [currentView, setCurrentView] = useState<View>("live");
  const [selectedClub, setSelectedClub] = useState("driver");
  const { isLaunchDaddyMode, isExploding, triggerExplosion, handleSecretTap } = useLaunchDaddy();

  // Trigger explosion when a new shot is detected
  useEffect(() => {
    if (latestShot && isLaunchDaddyMode) {
      triggerExplosion();
    }
  }, [latestShot?.timestamp, isLaunchDaddyMode, triggerExplosion]);

  const handleClubChange = (club: string) => {
    setSelectedClub(club);
    setClub(club);
  };

  return (
    <div className={`app ${isLaunchDaddyMode ? 'app--launch-daddy' : ''} ${isExploding ? 'app--exploding' : ''}`}>
      {/* Launch Daddy Overlay */}
      <LaunchDaddyOverlay />
      <LaunchDaddySecretIndicator />

      <header className="header">
        {/* Secret activation area - click/tap 5 times quickly */}
        <div
          className="header__secret-tap"
          onClick={handleSecretTap}
          onKeyDown={(e) => e.key === 'Enter' && handleSecretTap()}
          role="button"
          tabIndex={0}
          style={{
            padding: '8px',
            cursor: 'pointer',
            minWidth: '44px',
            minHeight: '44px',
            display: 'flex',
            alignItems: 'center',
            userSelect: 'none',
          }}
        >
          {isLaunchDaddyMode ? <LaunchDaddyBrand /> : <span style={{ opacity: 0.3, fontSize: '1.2rem' }}>⛳</span>}
        </div>
        <div className="header__controls">
          <ClubPicker
            selectedClub={selectedClub}
            onClubChange={handleClubChange}
          />
          <BallDetectionIndicator
            available={cameraStatus.available}
            enabled={cameraStatus.enabled}
            detected={cameraStatus.ball_detected}
            confidence={cameraStatus.ball_confidence}
            onToggle={toggleCamera}
          />
          <ConnectionStatus connected={connected} />
        </div>
      </header>

      <nav className="nav">
        <button
          className={`nav__button ${
            currentView === "live" ? "nav__button--active" : ""
          }`}
          onClick={() => setCurrentView("live")}
        >
          {Icons.live}
          <span>Live</span>
        </button>
        <button
          className={`nav__button ${
            currentView === "stats" ? "nav__button--active" : ""
          }`}
          onClick={() => setCurrentView("stats")}
        >
          {Icons.stats}
          <span>Stats</span>
        </button>
        <button
          className={`nav__button ${
            currentView === "shots" ? "nav__button--active" : ""
          }`}
          onClick={() => setCurrentView("shots")}
        >
          {Icons.shots}
          <span>Shots</span>
          {shots.length > 0 && (
            <span className="nav__badge">{shots.length}</span>
          )}
        </button>
        <button
          className={`nav__button ${
            currentView === "camera" ? "nav__button--active" : ""
          } ${cameraStatus.streaming ? "nav__button--streaming" : ""}`}
          onClick={() => setCurrentView("camera")}
        >
          {Icons.camera}
          <span>Camera</span>
          {cameraStatus.ball_detected && <span className="nav__ball-dot" />}
        </button>
        <button
          className={`nav__button ${
            currentView === "debug" ? "nav__button--active" : ""
          } ${debugMode ? "nav__button--recording" : ""}`}
          onClick={() => setCurrentView("debug")}
        >
          {Icons.debug}
          <span>Debug</span>
          {debugMode && <span className="nav__recording-dot" />}
        </button>
      </nav>

      <main className="main">
        {currentView === "live" && (
          <div className="live-view">
            {latestShot && (
              <div key={latestShot.timestamp} className="shot-flash" />
            )}
            <ShotDisplay
              key={latestShot?.timestamp}
              shot={latestShot}
              isLatest={true}
            />
            {mockMode && (
              <button className="simulate-button" onClick={simulateShot}>
                Simulate Shot
              </button>
            )}
          </div>
        )}
        {currentView === "stats" && (
          <StatsView shots={shots} onClearSession={clearSession} />
        )}
        {currentView === "shots" && <ShotList shots={shots} />}
        {currentView === "camera" && (
          <CameraFeed
            cameraStatus={cameraStatus}
            onToggleCamera={toggleCamera}
            onToggleStream={toggleCameraStream}
          />
        )}
        {currentView === "debug" && (
          <DebugPanel
            enabled={debugMode}
            readings={debugReadings}
            shotLogs={debugShotLogs}
            radarConfig={radarConfig}
            cameraStatus={cameraStatus}
            mockMode={mockMode}
            onToggle={toggleDebug}
            onUpdateConfig={updateRadarConfig}
          />
        )}
      </main>
    </div>
  );
}

function App() {
  return (
    <LaunchDaddyProvider>
      <AppContent />
    </LaunchDaddyProvider>
  );
}

export default App;
