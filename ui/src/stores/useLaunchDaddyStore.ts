import { create } from 'zustand';

const SECRET_TAP_WINDOW_MS = 2000;
const SECRET_TAP_TARGET = 5;
const EXPLOSION_DURATION_MS = 2500;

let secretTapCountRef = 0;
let lastTapTime = 0;
let explosionTimer: ReturnType<typeof setTimeout> | null = null;

interface LaunchDaddyState {
  isLaunchDaddyMode: boolean;
  isExploding: boolean;
  secretTapCount: number;
  toggleLaunchDaddy: () => void;
  triggerExplosion: () => void;
  handleSecretTap: () => void;
}

export const useLaunchDaddyStore = create<LaunchDaddyState>((set, get) => ({
  isLaunchDaddyMode: false,
  isExploding: false,
  secretTapCount: 0,
  toggleLaunchDaddy: () => {
    secretTapCountRef = 0;
    set((state) => ({
      isLaunchDaddyMode: !state.isLaunchDaddyMode,
      secretTapCount: 0,
    }));
  },
  triggerExplosion: () => {
    if (!get().isLaunchDaddyMode) return;

    if (explosionTimer) {
      clearTimeout(explosionTimer);
    }

    set({ isExploding: true });

    explosionTimer = setTimeout(() => {
      set({ isExploding: false });
      explosionTimer = null;
    }, EXPLOSION_DURATION_MS);
  },
  handleSecretTap: () => {
    const now = Date.now();
    const nextCount = now - lastTapTime > SECRET_TAP_WINDOW_MS ? 1 : secretTapCountRef + 1;

    if (nextCount >= SECRET_TAP_TARGET) {
      secretTapCountRef = 0;
      set((state) => ({
        isLaunchDaddyMode: !state.isLaunchDaddyMode,
        secretTapCount: 0,
      }));
    } else {
      secretTapCountRef = nextCount;
      set({ secretTapCount: nextCount });
    }

    lastTapTime = now;
  },
}));
