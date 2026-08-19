import { create } from 'zustand';
import type { ConnectionState, Shot } from '../types';

// Single source of truth for connection + session state, shared across tabs.
// The socket service (services/socket.ts) is the only writer during normal
// operation; components read via selectors. Kept deliberately small and
// framework-agnostic so the transitions are unit-testable in isolation.

interface SessionState {
  connectionState: ConnectionState;
  // Shots are held newest-first (index 0 is the latest), which is the order
  // every screen wants. The server sends them oldest-first, so `setShots`
  // inverts on the way in.
  shots: Shot[];

  setConnectionState: (state: ConnectionState) => void;
  // Replace the whole list from a `session_state` payload (server order:
  // oldest-first). Inverted here to preserve the newest-first invariant.
  setShots: (serverShots: Shot[]) => void;
  // Prepend a single shot from a `shot` event.
  addShot: (shot: Shot) => void;
  clearShots: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  connectionState: 'disconnected',
  shots: [],

  setConnectionState: (state) => set({ connectionState: state }),
  setShots: (serverShots) => set({ shots: [...serverShots].reverse() }),
  addShot: (shot) => set((prev) => ({ shots: [shot, ...prev.shots] })),
  clearShots: () => set({ shots: [] }),
}));
