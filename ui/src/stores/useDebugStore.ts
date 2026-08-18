import { create } from 'zustand';
import type { IWR6843Diagnostic, TriggerDiagnostic, TriggerDiagnosticUpdate, TriggerStatus } from '../types/shot';
import type { DebugReading, RadarConfig, DebugShotLog } from '../types/socket';

interface DebugState {
  debugReadings: DebugReading[];
  debugShotLogs: DebugShotLog[];
  radarConfig: RadarConfig;
  triggerDiagnostics: TriggerDiagnostic[];
  triggerStatus: TriggerStatus;
  iwr6843Alert: IWR6843Diagnostic | null;
  iwr6843ErrorActive: boolean;

  addDebugReading: (reading: DebugReading) => void;
  addDebugShotLog: (log: DebugShotLog) => void;
  clearDebugData: () => void;
  setRadarConfig: (config: RadarConfig) => void;
  addTriggerDiagnostic: (diagnostic: TriggerDiagnostic) => void;
  updateTriggerDiagnostic: (update: TriggerDiagnosticUpdate) => void;
  dismissIWR6843Alert: () => void;
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
  iwr6843Alert: null,
  iwr6843ErrorActive: false,

  addDebugReading: (reading) =>
    set((state) => {
      const updated = [...state.debugReadings, reading];
      return { debugReadings: updated.length > 50 ? updated.slice(-50) : updated };
    }),

  addDebugShotLog: (log) =>
    set((state) => {
      const updated = [...state.debugShotLogs, log];
      return { debugShotLogs: updated.length > 20 ? updated.slice(-20) : updated };
    }),

  clearDebugData: () => set({ debugReadings: [], debugShotLogs: [] }),

  setRadarConfig: (config) => set({ radarConfig: config }),

  addTriggerDiagnostic: (diagnostic) =>
    set((state) => {
      const updated = [...state.triggerDiagnostics, diagnostic];
      return { triggerDiagnostics: updated.length > 50 ? updated.slice(-50) : updated };
    }),

  updateTriggerDiagnostic: (update) =>
    set((state) => {
      const triggerDiagnostics = state.triggerDiagnostics.map((diagnostic) =>
        diagnostic.timestamp === update.timestamp ? { ...diagnostic, iwr6843: update.iwr6843 } : diagnostic
      );
      if (update.iwr6843.state === 'error') {
        return {
          triggerDiagnostics,
          iwr6843Alert: state.iwr6843ErrorActive ? state.iwr6843Alert : update.iwr6843,
          iwr6843ErrorActive: true,
        };
      }
      return {
        triggerDiagnostics,
        iwr6843Alert: null,
        iwr6843ErrorActive: false,
      };
    }),

  dismissIWR6843Alert: () => set({ iwr6843Alert: null }),

  setTriggerStatus: (status) => set({ triggerStatus: status }),

  updateTriggerStatusStats: (accepted) =>
    set((state) => ({
      triggerStatus: {
        ...state.triggerStatus,
        triggers_total: state.triggerStatus.triggers_total + 1,
        triggers_accepted: state.triggerStatus.triggers_accepted + (accepted ? 1 : 0),
        triggers_rejected: state.triggerStatus.triggers_rejected + (accepted ? 0 : 1),
      },
    })),
}));
