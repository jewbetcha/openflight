import { io, type Socket } from 'socket.io-client';
import { useSystemStore } from '../stores/useSystemStore';
import { useShotStore } from '../stores/useShotStore';
import { useCameraStore, type CameraStatus } from '../stores/useCameraStore';
import { useDebugStore } from '../stores/useDebugStore';
import type { Shot, SessionStats, SessionState, TriggerDiagnostic, TriggerStatus } from '../types/shot';
import type { DebugReading, RadarConfig, DebugShotLog, SimShotInfo, SimStatus } from '../types/socket';
import { getServerOrigin } from '../utils/serverOrigin';

const SOCKET_URL = getServerOrigin();

class SocketService {
  private socket: Socket | null = null;

  connect() {
    if (this.socket) return;

    this.socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
    });

    this.setupListeners();
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  private setupListeners() {
    if (!this.socket) return;

    this.socket.on('connect', () => {
      console.log('Connected to server');
      useSystemStore.getState().setConnected(true);
      this.socket?.emit('get_session');
      this.socket?.emit('get_trigger_status');
    });

    this.socket.on('disconnect', () => {
      console.log('Disconnected from server');
      useSystemStore.getState().setConnected(false);
    });

    this.socket.on('shot', (data: { shot: Shot; stats: SessionStats }) => {
      // Need to get latest state of addShot to prevent stale closures
      useShotStore.getState().addShot(data.shot);
    });

    this.socket.on('sim_status', (data: SimStatus) => {
      useSystemStore.getState().setSimStatus(data);
    });

    this.socket.on('sim_shot', (data: SimShotInfo) => {
      useSystemStore.getState().setLatestSimShot(data);
    });

    this.socket.on('sim_send_failed', (data: { target: string; reason: string }) => {
      console.warn(`Sim send failed (${data.target}): ${data.reason}`);
    });

    this.socket.on('sim_shot_dropped', (data: { reason: string }) => {
      console.warn(`Sim shot dropped: ${data.reason}`);
    });

    this.socket.on('club_changed', (data: { club: string }) => {
      useSystemStore.getState().setServerClub(data.club);
    });

    this.socket.on(
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
        // Need to get latest state of setShots
        useShotStore.getState().setShots(data.shots);

        const systemStore = useSystemStore.getState();
        if (data.mock_mode !== undefined) {
          systemStore.setMockMode(data.mock_mode);
        }
        if (data.debug_mode !== undefined) {
          systemStore.setDebugMode(data.debug_mode);
        }

        // Update camera status from session state
        if (data.camera_available !== undefined) {
          useCameraStore.getState().setCameraStatus({
            available: data.camera_available!,
            enabled: data.camera_enabled || false,
            streaming: data.camera_streaming || false,
            ball_detected: data.ball_detected || false,
          });
        }
      }
    );

    this.socket.on('debug_toggled', (data: { enabled: boolean }) => {
      useSystemStore.getState().setDebugMode(data.enabled);
      if (!data.enabled) {
        useDebugStore.getState().clearDebugData();
      }
    });

    this.socket.on('debug_shot', (data: DebugShotLog) => {
      useDebugStore.getState().addDebugShotLog(data);
    });

    this.socket.on('debug_reading', (data: DebugReading) => {
      useDebugStore.getState().addDebugReading(data);
    });

    this.socket.on('radar_config', (data: RadarConfig) => {
      useDebugStore.getState().setRadarConfig(data);
    });

    this.socket.on('camera_status', (data: CameraStatus) => {
      useCameraStore.getState().setCameraStatus(data);
    });

    this.socket.on('ball_detection', (data: { detected: boolean; confidence: number }) => {
      useCameraStore.getState().setCameraStatus({
        ball_detected: data.detected,
        ball_confidence: data.confidence,
      });
    });

    this.socket.on('session_cleared', () => {
      useShotStore.getState().clearShots();
    });

    this.socket.on('trigger_diagnostic', (data: TriggerDiagnostic) => {
      const debugStore = useDebugStore.getState();
      debugStore.addTriggerDiagnostic(data);
      debugStore.updateTriggerStatusStats(data.accepted);
    });

    this.socket.on('trigger_status', (data: TriggerStatus) => {
      useDebugStore.getState().setTriggerStatus(data);
    });
  }

  // Emitters
  clearSession() {
    this.socket?.emit('clear_session');
  }

  setClub(club: string) {
    this.socket?.emit('set_club', { club });
  }

  simulateShot() {
    this.socket?.emit('simulate_shot');
  }

  toggleDebug() {
    this.socket?.emit('toggle_debug');
  }

  setRadarConfig(config: Partial<RadarConfig>) {
    this.socket?.emit('set_radar_config', config);
  }

  toggleCamera() {
    this.socket?.emit('toggle_camera');
  }

  toggleCameraStream() {
    this.socket?.emit('toggle_camera_stream');
  }
}

export const socketService = new SocketService();
