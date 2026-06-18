import { create } from 'zustand';
import type { TriggerDiagnostic, TriggerStatus } from '../types/shot';
import type { DebugReading, RadarConfig, DebugShotLog } from '../types/socket';

interface DebugState {
  debugReadings: DebugReading[];
  debugShotLogs: DebugShotLog[];
  radarConfig: RadarConfig;
  triggerDiagnostics: TriggerDiagnostic[];
  triggerStatus: TriggerStatus;

  addDebugReading: (reading: DebugReading) => void;
  addDebugShotLog: (log: DebugShotLog) => void;
  clearDebugData: () => void;
  setRadarConfig: (config: RadarConfig) => void;
  addTriggerDiagnostic: (diagnostic: TriggerDiagnostic) => void;
  setTriggerStatus: (status: TriggerStatus) => void;
  updateTriggerStatusStats: (accepted: boolean) => void;
}

export const useDebugStore = create<DebugState>((set) => ({
  debugReadings: [],
  debugShotLogs: [],
  radarConfig: {
    min_speed: 10,
    max_speed: 220,
    min_magnitude: 0,
    transmit_power: 0,
  },
  triggerDiagnostics: [],
  triggerStatus: {
    mode: 'rolling-buffer',
    trigger_type: null,
    radar_connected: false,
    radar_port: null,
    triggers_total: 0,
    triggers_accepted: 0,
    triggers_rejected: 0,
  },

  addDebugReading: (reading) => set((state) => {
    const updated = [...state.debugReadings, reading];
    return { debugReadings: updated.length > 50 ? updated.slice(-50) : updated };
  }),

  addDebugShotLog: (log) => set((state) => {
    const updated = [...state.debugShotLogs, log];
    return { debugShotLogs: updated.length > 20 ? updated.slice(-20) : updated };
  }),

  clearDebugData: () => set({ debugReadings: [], debugShotLogs: [] }),

  setRadarConfig: (config) => set({ radarConfig: config }),

  addTriggerDiagnostic: (diagnostic) => set((state) => {
    const updated = [...state.triggerDiagnostics, diagnostic];
    return { triggerDiagnostics: updated.length > 50 ? updated.slice(-50) : updated };
  }),

  setTriggerStatus: (status) => set({ triggerStatus: status }),

  updateTriggerStatusStats: (accepted) => set((state) => ({
    triggerStatus: {
      ...state.triggerStatus,
      triggers_total: state.triggerStatus.triggers_total + 1,
      triggers_accepted: state.triggerStatus.triggers_accepted + (accepted ? 1 : 0),
      triggers_rejected: state.triggerStatus.triggers_rejected + (accepted ? 0 : 1),
    }
  })),
}));
