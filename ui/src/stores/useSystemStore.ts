import { create } from 'zustand';
import type { SimShotInfo, SimStatus } from '../types/socket';

interface SystemState {
  connected: boolean;
  mockMode: boolean;
  debugMode: boolean;
  simStatuses: Record<string, SimStatus>;
  latestSimShots: Record<string, SimShotInfo>;
  serverClub: string | null;
  setConnected: (connected: boolean) => void;
  setMockMode: (mockMode: boolean) => void;
  setDebugMode: (debugMode: boolean) => void;
  setSimStatus: (status: SimStatus) => void;
  setLatestSimShot: (shot: SimShotInfo) => void;
  setServerClub: (club: string | null) => void;
}

export const useSystemStore = create<SystemState>((set) => ({
  connected: false,
  mockMode: false,
  debugMode: false,
  simStatuses: {},
  latestSimShots: {},
  serverClub: null,
  setConnected: (connected) => set({ connected }),
  setMockMode: (mockMode) => set({ mockMode }),
  setDebugMode: (debugMode) => set({ debugMode }),
  setSimStatus: (status) =>
    set((state) => ({
      simStatuses: { ...state.simStatuses, [status.target]: status },
    })),
  setLatestSimShot: (shot) =>
    set((state) => ({
      latestSimShots: { ...state.latestSimShots, [shot.target]: shot },
    })),
  setServerClub: (serverClub) => set({ serverClub }),
}));
