import { useEffect, useState, useCallback } from 'react';
import { io, type Socket } from 'socket.io-client';
import type { Shot, SessionStats, SessionState } from '../types/shot';

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

export function useSocket() {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [mockMode, setMockMode] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [debugReadings, setDebugReadings] = useState<DebugReading[]>([]);
  const [radarConfig, setRadarConfig] = useState<RadarConfig>({
    min_speed: 10,
    max_speed: 220,
    min_magnitude: 0,
    transmit_power: 0,
  });
  const [latestShot, setLatestShot] = useState<Shot | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [stats, setStats] = useState<SessionStats | null>(null);

  useEffect(() => {
    const newSocket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
    });

    newSocket.on('connect', () => {
      console.log('Connected to server');
      setConnected(true);
      newSocket.emit('get_session');
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
      setStats(data.stats);
    });

    newSocket.on('session_state', (data: SessionState & { mock_mode?: boolean; debug_mode?: boolean }) => {
      console.log('Session state received:', data);
      setShots(data.shots);
      setStats(data.stats);
      if (data.mock_mode !== undefined) {
        setMockMode(data.mock_mode);
      }
      if (data.debug_mode !== undefined) {
        setDebugMode(data.debug_mode);
      }
      if (data.shots.length > 0) {
        setLatestShot(data.shots[data.shots.length - 1]);
      }
    });

    newSocket.on('debug_toggled', (data: { enabled: boolean }) => {
      setDebugMode(data.enabled);
      if (!data.enabled) {
        setDebugReadings([]);
      }
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

    newSocket.on('session_cleared', () => {
      setShots([]);
      setStats(null);
      setLatestShot(null);
    });

    setSocket(newSocket);

    return () => {
      newSocket.close();
    };
  }, []);

  const clearSession = useCallback(() => {
    socket?.emit('clear_session');
  }, [socket]);

  const setClub = useCallback((club: string) => {
    socket?.emit('set_club', { club });
  }, [socket]);

  const simulateShot = useCallback(() => {
    socket?.emit('simulate_shot');
  }, [socket]);

  const toggleDebug = useCallback(() => {
    socket?.emit('toggle_debug');
  }, [socket]);

  const updateRadarConfig = useCallback((config: Partial<RadarConfig>) => {
    socket?.emit('set_radar_config', config);
  }, [socket]);

  const getRadarConfig = useCallback(() => {
    socket?.emit('get_radar_config');
  }, [socket]);

  return {
    connected,
    mockMode,
    debugMode,
    debugReadings,
    radarConfig,
    latestShot,
    shots,
    stats,
    clearSession,
    setClub,
    simulateShot,
    toggleDebug,
    updateRadarConfig,
    getRadarConfig,
  };
}
