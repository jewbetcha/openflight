import { create } from 'zustand';

export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'openflight.theme';

export function applyThemeToDocument(theme: Theme): void {
  if (typeof document === 'undefined') {
    return;
  }

  document.documentElement.setAttribute('data-theme', theme);
}

export function readStoredTheme(): Theme {
  if (typeof window === 'undefined') {
    return 'dark';
  }

  try {
    const storedValue = window.localStorage.getItem(THEME_STORAGE_KEY);
    return storedValue === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readStoredTheme(),
  setTheme: (theme) => {
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, theme);
      } catch {
        // Ignore quota / private browsing failures.
      }
    }

    applyThemeToDocument(theme);
    set({ theme });
  },
  toggleTheme: () => {
    const nextTheme: Theme = get().theme === 'light' ? 'dark' : 'light';
    get().setTheme(nextTheme);
  },
}));

// Sync DOM on module load (FOUC script usually already set this).
applyThemeToDocument(readStoredTheme());
