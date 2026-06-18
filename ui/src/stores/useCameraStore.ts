import { create } from 'zustand';

export interface CameraStatus {
  available: boolean;
  enabled: boolean;
  streaming: boolean;
  ball_detected: boolean;
  ball_confidence: number;
}

interface CameraState {
  cameraStatus: CameraStatus;
  setCameraStatus: (status: Partial<CameraStatus>) => void;
}

export const useCameraStore = create<CameraState>((set) => ({
  cameraStatus: {
    available: false,
    enabled: false,
    streaming: false,
    ball_detected: false,
    ball_confidence: 0,
  },
  setCameraStatus: (status) =>
    set((state) => ({
      cameraStatus: { ...state.cameraStatus, ...status },
    })),
}));
