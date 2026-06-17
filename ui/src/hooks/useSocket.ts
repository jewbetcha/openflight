import { useEffect, useState, useCallback, useRef } from 'react';
import { io, type Socket } from 'socket.io-client';
import type { Shot, SessionStats, SessionState, TriggerDiagnostic, TriggerStatus } from '../types/shot';
import { useShotActions } from '../state/useShotActions';
import { getServerOrigin } from '../utils/serverOrigin';
import type { A11yPrefs } from '../state/useAccessibilitySettings';

const SOCKET_URL = getServerOrigin();

export interface DebugReading {
  speed: number;
  direction: 'inbound' | 'outbound' | 'unknown';
  magnitude: number | null;
  timestamp: string;
}

export interface RadarConfig {
  min_speed: number;
  max_speed: number;
  min_magnitude: number;
  transmit_power: number;
}

export interface CameraStatus {
  available: boolean;
  enabled: boolean;
  streaming: boolean;
  ball_detected: boolean;
  ball_confidence: number;
}

export interface DebugShotLog {
  type: 'shot';
  timestamp: string;
  radar: {
    ball_speed_mph: number;
    club_speed_mph: number | null;
    smash_factor: number | null;
    peak_magnitude: number;
  };
  camera: {
    launch_angle_vertical: number;
    launch_angle_horizontal: number;
    launch_angle_confidence: number;
    positions_tracked: number;
    launch_detected: boolean;
  } | null;
  club: string;
}

export function useSocket() {
  const socketRef = useRef<Socket | null>(null);
  const { addShot, setShots, clearShots } = useShotActions();

  // Keep stable refs so socket event handlers always see the latest callbacks
  // without needing to re-register listeners when they change.
  const addShotRef = useRef(addShot);
  const setShotsRef = useRef(setShots);
  const clearShotsRef = useRef(clearShots);
  const adminTokenRef = useRef('');
  const cameraTokenRef = useRef('');

  useEffect(() => {
    addShotRef.current = addShot;
    setShotsRef.current = setShots;
    clearShotsRef.current = clearShots;
  }, [addShot, setShots, clearShots]);

  const [connected, setConnected] = useState(false);
  const [adminToken, setAdminToken] = useState('');
  const [cameraToken, setCameraToken] = useState('');
  const [mockMode, setMockMode] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [debugReadings, setDebugReadings] = useState<DebugReading[]>([]);
  const [debugShotLogs, setDebugShotLogs] = useState<DebugShotLog[]>([]);
  const [radarConfig, setRadarConfig] = useState<RadarConfig>({
    min_speed: 10,
    max_speed: 220,
    min_magnitude: 0,
    transmit_power: 0,
  });
  // Camera state
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>({
    available: false,
    enabled: false,
    streaming: false,
    ball_detected: false,
    ball_confidence: 0,
  });
  const [remoteA11yPrefs, setRemoteA11yPrefs] = useState<Partial<A11yPrefs> | null>(null);

  // Trigger diagnostics state
  const [triggerDiagnostics, setTriggerDiagnostics] = useState<TriggerDiagnostic[]>([]);
  const [triggerStatus, setTriggerStatus] = useState<TriggerStatus>({
    mode: 'rolling-buffer',
    trigger_type: null,
    radar_connected: false,
    radar_port: null,
    triggers_total: 0,
    triggers_accepted: 0,
    triggers_rejected: 0,
  });

  useEffect(() => {
    const newSocket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
    });

    newSocket.on('connect', () => {
      console.log('Connected to server');
      setConnected(true);
      newSocket.emit('get_trigger_status');
    });

    newSocket.on('admin_token', (data: { token: string; camera_token?: string }) => {
      adminTokenRef.current = data.token;
      setAdminToken(data.token);
      if (data.camera_token) {
        cameraTokenRef.current = data.camera_token;
        setCameraToken(data.camera_token);
      }
    });

    newSocket.on('disconnect', () => {
      console.log('Disconnected from server');
      setConnected(false);
    });

    // Phone/tablet web-remote: a relayed D-pad key. Re-broadcast as a window
    // event so the spatial-navigation bridge can synthesize the matching
    // keystroke (keeps socket plumbing decoupled from focus/DOM logic).
    newSocket.on('remote_key', (data: { key?: string }) => {
      if (data?.key) {
        window.dispatchEvent(new CustomEvent('openflight:remotekey', { detail: data.key }));
      }
    });

    newSocket.on('shot', (data: { shot: Shot; stats: SessionStats }) => {
      addShotRef.current(data.shot);
    });

    newSocket.on(
      'session_state',
      (
        data: SessionState & {
          mock_mode?: boolean;
          debug_mode?: boolean;
          camera_available?: boolean;
          camera_enabled?: boolean;
          camera_streaming?: boolean;
          ball_detected?: boolean;
        }
      ) => {
        console.log('Session state received:', data);
        setShotsRef.current(data.shots);

        if (data.mock_mode !== undefined) {
          setMockMode(data.mock_mode);
        }
        if (data.debug_mode !== undefined) {
          setDebugMode(data.debug_mode);
        }
        // Update camera status from session state
        if (data.camera_available !== undefined) {
          setCameraStatus((prev) => ({
            ...prev,
            available: data.camera_available!,
            enabled: data.camera_enabled || false,
            streaming: data.camera_streaming || false,
            ball_detected: data.ball_detected || false,
          }));
        }
      }
    );

    newSocket.on('debug_toggled', (data: { enabled: boolean }) => {
      setDebugMode(data.enabled);
      if (!data.enabled) {
        setDebugReadings([]);
        setDebugShotLogs([]);
      }
    });

    newSocket.on('debug_shot', (data: DebugShotLog) => {
      setDebugShotLogs((prev) => {
        const updated = [...prev, data];
        // Keep only last 20 shot logs to prevent memory issues
        return updated.length > 20 ? updated.slice(-20) : updated;
      });
    });

    newSocket.on('debug_reading', (data: DebugReading) => {
      setDebugReadings((prev) => {
        const updated = [...prev, data];
        // Keep only last 50 readings to prevent memory issues
        return updated.length > 50 ? updated.slice(-50) : updated;
      });
    });

    newSocket.on('radar_config', (data: RadarConfig) => {
      setRadarConfig(data);
    });

    // Camera events
    newSocket.on('camera_status', (data: CameraStatus) => {
      setCameraStatus(data);
    });

    newSocket.on('ball_detection', (data: { detected: boolean; confidence: number }) => {
      setCameraStatus((prev) => ({
        ...prev,
        ball_detected: data.detected,
        ball_confidence: data.confidence,
      }));
    });

    newSocket.on('session_cleared', () => {
      clearShotsRef.current();
    });

    newSocket.on('trigger_diagnostic', (data: TriggerDiagnostic) => {
      setTriggerDiagnostics((prev) => {
        const updated = [...prev, data];
        return updated.length > 50 ? updated.slice(-50) : updated;
      });
      setTriggerStatus((prev) => ({
        ...prev,
        triggers_total: prev.triggers_total + 1,
        triggers_accepted: prev.triggers_accepted + (data.accepted ? 1 : 0),
        triggers_rejected: prev.triggers_rejected + (data.accepted ? 0 : 1),
      }));
    });

    newSocket.on('trigger_status', (data: TriggerStatus) => {
      setTriggerStatus(data);
    });

    newSocket.on('accessibility_prefs_update', (data: unknown) => {
      if (data && typeof data === 'object') {
        const p = data as Record<string, unknown>;
        const a11y = p.accessibility;
        if (a11y && typeof a11y === 'object') {
          setRemoteA11yPrefs(a11y as Partial<A11yPrefs>);
        }
      }
    });

    socketRef.current = newSocket;

    return () => {
      newSocket.close();
      socketRef.current = null;
    };
  }, []);

  const clearSession = useCallback(() => {
    socketRef.current?.emit('clear_session', { token: adminTokenRef.current });
  }, []);

  const setClub = useCallback((club: string) => {
    socketRef.current?.emit('set_club', { club, token: adminTokenRef.current });
  }, []);

  const simulateShot = useCallback(() => {
    socketRef.current?.emit('simulate_shot', { token: adminTokenRef.current });
  }, []);

  const toggleDebug = useCallback(() => {
    socketRef.current?.emit('toggle_debug', { token: adminTokenRef.current });
  }, []);

  const updateRadarConfig = useCallback((config: Partial<RadarConfig>) => {
    socketRef.current?.emit('set_radar_config', { ...config, token: adminTokenRef.current });
  }, []);

  // Camera controls
  const toggleCamera = useCallback(() => {
    socketRef.current?.emit('toggle_camera', { token: adminTokenRef.current });
  }, []);

  const toggleCameraStream = useCallback(() => {
    socketRef.current?.emit('toggle_camera_stream', { token: adminTokenRef.current });
  }, []);

  const shutdown = useCallback((): Promise<boolean> => {
    return fetch('/api/shutdown', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: adminTokenRef.current }),
    })
      .then((res) => res.ok)
      .catch(() => false);
  }, []);

  /** Phone/tablet web-remote (/remote route) → relay a D-pad key to the display. */
  const sendRemoteKey = useCallback((key: 'up' | 'down' | 'left' | 'right' | 'ok' | 'back') => {
    socketRef.current?.emit('remote_key', { key });
  }, []);

  return {
    connected,
    adminToken,
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
  };
}
