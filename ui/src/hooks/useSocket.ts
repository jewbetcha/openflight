import { useEffect, useState, useCallback, useRef } from 'react';
import { io, type Socket } from 'socket.io-client';
import type { Shot, SessionStats, SessionState, TriggerDiagnostic, TriggerStatus } from '../types/shot';

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL || 'http://localhost:8080';

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
  const [connected, setConnected] = useState(false);
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
  const [latestShot, setLatestShot] = useState<Shot | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  // Camera state
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>({
    available: false,
    enabled: false,
    streaming: false,
    ball_detected: false,
    ball_confidence: 0,
  });
  // Trigger diagnostics state
  const [triggerDiagnostics, setTriggerDiagnostics] = useState<TriggerDiagnostic[]>([]);
  const [triggerStatus, setTriggerStatus] = useState<TriggerStatus>({
    mode: 'streaming',
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
      newSocket.emit('get_session');
      newSocket.emit('get_trigger_status');
    });

    newSocket.on('disconnect', () => {
      console.log('Disconnected from server');
      setConnected(false);
    });

    newSocket.on('shot', (data: { shot: Shot; stats: SessionStats }) => {
      setLatestShot(data.shot);
      setShots((prev) => {
        const updated = [...prev, data.shot];
        // Keep only last 200 shots in UI state to prevent memory issues
        return updated.length > 200 ? updated.slice(-200) : updated;
      });

    });

    newSocket.on('session_state', (data: SessionState & {
      mock_mode?: boolean;
      debug_mode?: boolean;
      camera_available?: boolean;
      camera_enabled?: boolean;
      camera_streaming?: boolean;
      ball_detected?: boolean;
    }) => {
      console.log('Session state received:', data);
      setShots(data.shots);

      if (data.mock_mode !== undefined) {
        setMockMode(data.mock_mode);
      }
      if (data.debug_mode !== undefined) {
        setDebugMode(data.debug_mode);
      }
      if (data.shots.length > 0) {
        setLatestShot(data.shots[data.shots.length - 1]);
      }
      // Update camera status from session state
      if (data.camera_available !== undefined) {
        setCameraStatus(prev => ({
          ...prev,
          available: data.camera_available!,
          enabled: data.camera_enabled || false,
          streaming: data.camera_streaming || false,
          ball_detected: data.ball_detected || false,
        }));
      }
    });

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
      setCameraStatus(prev => ({
        ...prev,
        ball_detected: data.detected,
        ball_confidence: data.confidence,
      }));
    });

    newSocket.on('session_cleared', () => {
      setShots([]);
      setLatestShot(null);
    });

    newSocket.on('trigger_diagnostic', (data: TriggerDiagnostic) => {
      setTriggerDiagnostics((prev) => {
        const updated = [...prev, data];
        return updated.length > 50 ? updated.slice(-50) : updated;
      });
      setTriggerStatus(prev => ({
        ...prev,
        triggers_total: prev.triggers_total + 1,
        triggers_accepted: prev.triggers_accepted + (data.accepted ? 1 : 0),
        triggers_rejected: prev.triggers_rejected + (data.accepted ? 0 : 1),
      }));
    });

    newSocket.on('trigger_status', (data: TriggerStatus) => {
      setTriggerStatus(data);
    });

    socketRef.current = newSocket;

    return () => {
      newSocket.close();
      socketRef.current = null;
    };
  }, []);

  const clearSession = useCallback(() => {
    socketRef.current?.emit('clear_session');
  }, []);

  const setClub = useCallback((club: string) => {
    socketRef.current?.emit('set_club', { club });
  }, []);

  const simulateShot = useCallback(() => {
    socketRef.current?.emit('simulate_shot');
  }, []);

  const toggleDebug = useCallback(() => {
    socketRef.current?.emit('toggle_debug');
  }, []);

  const updateRadarConfig = useCallback((config: Partial<RadarConfig>) => {
    socketRef.current?.emit('set_radar_config', config);
  }, []);

  // Camera controls
  const toggleCamera = useCallback(() => {
    socketRef.current?.emit('toggle_camera');
  }, []);

  const toggleCameraStream = useCallback(() => {
    socketRef.current?.emit('toggle_camera_stream');
  }, []);

  return {
    connected,
    mockMode,
    debugMode,
    debugReadings,
    debugShotLogs,
    radarConfig,
    latestShot,
    shots,
    cameraStatus,
    triggerDiagnostics,
    triggerStatus,
    clearSession,
    setClub,
    simulateShot,
    toggleDebug,
    updateRadarConfig,
    toggleCamera,
    toggleCameraStream,
  };
}
