import { io, type Socket } from 'socket.io-client';
import { useSessionStore } from '../stores/useSessionStore';
import { saveServerUrl } from '../storage/connection';
import type { SessionStatePayload, ShotEnvelope } from '../types';

// Singleton Socket.IO client, mirroring the web app's socketService shape: one
// place that maps every server event onto a store mutation. Kept out of the
// React tree so a reconnect or a background disconnect doesn't depend on any
// screen being mounted.
//
// Reconnection is handled by Socket.IO itself (exponential backoff, enabled by
// default); the handlers here just reflect the resulting connection state and
// re-sync the session on every (re)connect.
class SocketService {
  private socket: Socket | null = null;

  connect(url: string): void {
    // Already connected/connecting to something — ignore. Callers must
    // disconnect first to point at a different server.
    if (this.socket) return;

    useSessionStore.getState().setConnectionState('connecting');

    const socket = io(url, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5000,
    });
    this.socket = socket;
    this.registerHandlers(socket, url);
  }

  disconnect(): void {
    this.socket?.close();
    this.socket = null;
    useSessionStore.getState().setConnectionState('disconnected');
  }

  simulateShot(): void {
    this.socket?.emit('simulate_shot');
  }

  private registerHandlers(socket: Socket, url: string): void {
    const store = useSessionStore.getState;

    socket.on('connect', () => {
      store().setConnectionState('connected');
      // Remember a URL only once it actually connects, so we never persist a
      // typo'd address that never worked.
      void saveServerUrl(url);
      // Re-sync the full session on every (re)connect, not just the first.
      socket.emit('get_session');
    });

    socket.on('disconnect', () => {
      // A transient drop: Socket.IO will attempt to reconnect in the
      // background. Surface it as disconnected until 'connect' fires again.
      store().setConnectionState('disconnected');
    });

    socket.on('connect_error', () => {
      store().setConnectionState('error');
    });

    socket.on('session_state', (data: SessionStatePayload) => {
      store().setShots(data.shots);
    });

    socket.on('shot', (data: ShotEnvelope) => {
      store().addShot(data.shot);
    });
  }
}

export const socketService = new SocketService();
