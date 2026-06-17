import { useAccessibilitySettings } from './useAccessibilitySettings';

export interface ThemeColors {
  isColorBlind: boolean;
  gold: string;
  goldDim: string;
  pos: string;
  neg: string;
  neutral: string;
  /** rgba() string helper - goldA(0.5) → "rgba(212, 175, 55, 0.5)" */
  goldA: (alpha: number) => string;
  scoreColors: Record<string, string>;
  priorityColors: Record<'high' | 'medium' | 'low', string>;
}

type BaseColors = Omit<ThemeColors, 'isColorBlind' | 'goldA'>;

const DEFAULT: BaseColors = {
  gold:    '#d4af37',
  goldDim: '#a68b2a',
  pos:     '#34d399',
  neg:     '#f87171',
  neutral: '#fbbf24',
  scoreColors: {
    Elite:       '#d4af37',
    Solid:       '#34d399',
    Developing:  '#fbbf24',
    Opportunity: '#f87171',
  },
  priorityColors: {
    high:   '#f87171',
    medium: '#fbbf24',
    low:    '#34d399',
  },
};

const COLOR_BLIND: BaseColors = {
  gold:    '#E8B830',
  goldDim: '#B89020',
  pos:     '#4E8CF5',
  neg:     '#F28C00',
  neutral: '#9B72F5',
  scoreColors: {
    Elite:       '#E8B830',
    Solid:       '#4E8CF5',
    Developing:  '#9B72F5',
    Opportunity: '#F28C00',
  },
  priorityColors: {
    high:   '#F28C00',
    medium: '#9B72F5',
    low:    '#4E8CF5',
  },
};

export function useThemeColors(): ThemeColors {
  const { prefs } = useAccessibilitySettings();
  const isColorBlind = prefs.colorBlind;
  const base = isColorBlind ? COLOR_BLIND : DEFAULT;
  const goldRgb = isColorBlind ? '232, 184, 48' : '212, 175, 55';
  return { ...base, isColorBlind, goldA: (alpha: number) => `rgba(${goldRgb}, ${alpha})` };
}
