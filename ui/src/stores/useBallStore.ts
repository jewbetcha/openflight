import { create } from 'zustand';

export const DEFAULT_BALLS = [
  'Unknown Ball',
  'Range Ball',
  'Titleist Pro V1',
  'Titleist Pro V1x',
  'Titleist AVX',
  'Titleist Tour Soft',
  'Callaway Chrome Tour',
  'Callaway Chrome Tour X',
  'Callaway Chrome Soft',
  'Callaway ERC Soft',
  'Callaway Supersoft',
  'TaylorMade TP5',
  'TaylorMade TP5x',
  'TaylorMade Tour Response',
  'TaylorMade SpeedSoft',
  'Srixon Z-Star',
  'Srixon Z-Star XV',
  'Srixon Q-Star Tour',
  'Srixon Soft Feel',
  'Bridgestone Tour B X',
  'Bridgestone Tour B XS',
  'Bridgestone Tour B RX',
  'Bridgestone Tour B RXS',
  'Wilson Staff Model',
  'Wilson Duo Soft',
  'Maxfli Tour',
  'Maxfli Tour X',
  'Vice Pro',
  'Vice Pro Plus',
  'Mizuno RB Tour',
];

const BALLS_STORAGE_KEY = 'openflight-balls';
const SELECTED_BALL_STORAGE_KEY = 'openflight-selected-ball';
const DEFAULT_BALL = 'Unknown Ball';

function cleanBallName(name: string): string {
  return name.trim().slice(0, 64);
}

function dedupeBalls(balls: string[]): string[] {
  const seen = new Set<string>();
  return balls.filter((ball) => {
    const key = ball.toLowerCase();
    if (!ball || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function loadCustomBalls(): string[] {
  if (typeof window === 'undefined') return [];

  try {
    const raw = window.localStorage.getItem(BALLS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed)) {
      return parsed.map((name) => cleanBallName(String(name))).filter(Boolean).slice(0, 24);
    }
  } catch {
    // Ignore broken localStorage data and fall back to defaults.
  }
  return [];
}

function saveCustomBalls(customBalls: string[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(BALLS_STORAGE_KEY, JSON.stringify(customBalls));
  } catch {
    // Ignore storage failures; the picker still works for the current session.
  }
}

function saveSelectedBall(ballName: string) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SELECTED_BALL_STORAGE_KEY, ballName);
  } catch {
    // Ignore storage failures; the picker still works for the current session.
  }
}

function loadSelectedBall(): string {
  if (typeof window === 'undefined') return '';
  try {
    return cleanBallName(window.localStorage.getItem(SELECTED_BALL_STORAGE_KEY) ?? '');
  } catch {
    return '';
  }
}

interface BallState {
  balls: string[];
  customBalls: string[];
  selectedBall: string;
  addBall: (name: string) => string;
  removeBall: (name: string) => void;
  selectBall: (name: string) => void;
}

const initialCustomBalls = loadCustomBalls();
const initialBalls = dedupeBalls([...DEFAULT_BALLS, ...initialCustomBalls]);
const savedSelected = loadSelectedBall();
const initialSelected = initialBalls.includes(savedSelected) ? savedSelected : DEFAULT_BALL;

export const useBallStore = create<BallState>((set, get) => ({
  balls: initialBalls,
  customBalls: initialCustomBalls,
  selectedBall: initialSelected,
  addBall: (name) => {
    const ballName = cleanBallName(name) || DEFAULT_BALL;
    const nextCustomBalls = dedupeBalls([...get().customBalls, ballName]).slice(0, 24);
    const nextBalls = dedupeBalls([...DEFAULT_BALLS, ...nextCustomBalls]);
    saveCustomBalls(nextCustomBalls);
    saveSelectedBall(ballName);
    set({ balls: nextBalls, customBalls: nextCustomBalls, selectedBall: ballName });
    return ballName;
  },
  removeBall: (name) => {
    const current = get();
    const nextCustomBalls = current.customBalls.filter((ball) => ball !== name);
    const nextBalls = dedupeBalls([...DEFAULT_BALLS, ...nextCustomBalls]);
    const selectedBall = current.selectedBall === name ? DEFAULT_BALL : current.selectedBall;
    saveCustomBalls(nextCustomBalls);
    saveSelectedBall(selectedBall);
    set({ balls: nextBalls, customBalls: nextCustomBalls, selectedBall });
  },
  selectBall: (name) => {
    const ballName = cleanBallName(name) || DEFAULT_BALL;
    const current = get();
    const customBalls = current.balls.some((ball) => ball.toLowerCase() === ballName.toLowerCase())
      ? current.customBalls
      : dedupeBalls([...current.customBalls, ballName]).slice(0, 24);
    const balls = dedupeBalls([...DEFAULT_BALLS, ...customBalls]);
    saveCustomBalls(customBalls);
    saveSelectedBall(ballName);
    set({ balls, customBalls, selectedBall: ballName });
  },
}));
