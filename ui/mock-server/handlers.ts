/**
 * Socket.IO event handlers mirroring the Flask server contract the UI uses.
 */

import type { Server, Socket } from 'socket.io';
import type { RadarConfig } from '../src/types/socket.js';
import type { MockSession } from './session.js';

const BALL_DETECTION_INTERVAL_MS = 1500;

export function registerHandlers(io: Server, session: MockSession): void {
  // Shared timer so all connected clients see the same fake detections
  const ballTimer = setInterval(() => {
    const detection = session.tickBallDetection();
    if (!detection) return;
    io.emit('ball_detection', detection);
  }, BALL_DETECTION_INTERVAL_MS);

  // Avoid keeping the process alive solely for the timer if nobody imported this module oddly;
  // the HTTP server keeps the process running either way.
  if (typeof ballTimer.unref === 'function') {
    ballTimer.unref();
  }

  io.on('connection', (socket: Socket) => {
    console.log('[mock-server] client connected');

    socket.emit('session_state', session.sessionStatePayload(true));
    socket.emit('trigger_status', session.triggerStatus());
    socket.emit('radar_config', session.radarConfig);
    socket.emit('camera_status', session.cameraStatus());

    socket.on('get_session', () => {
      socket.emit('session_state', session.sessionStatePayload(true));
    });

    socket.on('get_trigger_status', () => {
      socket.emit('trigger_status', session.triggerStatus());
    });

    socket.on('get_radar_config', () => {
      socket.emit('radar_config', session.radarConfig);
    });

    socket.on('get_camera_status', () => {
      socket.emit('camera_status', session.cameraStatus());
    });

    socket.on('get_debug_status', () => {
      socket.emit('debug_status', {
        enabled: session.debugMode,
        log_path: null,
      });
    });

    socket.on('simulate_shot', () => {
      const { shot, stats } = session.simulateShot();
      io.emit('shot', { shot, stats });
      io.emit('trigger_status', session.triggerStatus());
    });

    socket.on('set_club', (data: { club?: string }) => {
      const club = session.setClub(data?.club ?? 'driver');
      io.emit('club_changed', { club });
    });

    socket.on('set_player', (data: { player_name?: string }) => {
      const playerName = session.setPlayer(data?.player_name);
      io.emit('player_changed', { player_name: playerName });
    });

    socket.on('set_training_implement', (data: { implement?: string }) => {
      const implement = session.setTrainingImplement(data?.implement ?? 'driver');
      io.emit('training_implement_changed', {
        implement,
        label: implement,
      });
    });

    socket.on('clear_session', () => {
      session.clear();
      io.emit('session_cleared');
      io.emit('session_state', session.sessionStatePayload(true));
    });

    socket.on('delete_shot', (data: { timestamp?: string }) => {
      const deleted = session.deleteShot(data?.timestamp);
      if (!deleted) {
        socket.emit('delete_shot_error', { error: 'Shot not found' });
        return;
      }
      io.emit('session_state', session.sessionStatePayload(true));
    });

    socket.on('upload_cloud', () => {
      io.emit('cloud_upload_status', {
        state: 'running',
        message: 'Uploading...',
      });
      setTimeout(() => {
        io.emit('cloud_upload_status', {
          state: 'complete',
          message: 'Mock upload complete',
        });
      }, 400);
    });

    socket.on('toggle_debug', () => {
      const enabled = session.toggleDebug();
      io.emit('debug_toggled', {
        enabled,
        log_path: enabled ? '/tmp/openflight-mock-debug.jsonl' : undefined,
      });
    });

    socket.on('set_radar_config', (data: Partial<RadarConfig>) => {
      const config = session.updateRadarConfig(data ?? {});
      io.emit('radar_config', config);
    });

    socket.on('toggle_camera', () => {
      io.emit('camera_status', session.toggleCamera());
    });

    socket.on('toggle_camera_stream', () => {
      io.emit('camera_status', session.toggleCameraStream());
    });

    socket.on('disconnect', () => {
      console.log('[mock-server] client disconnected');
    });
  });
}
