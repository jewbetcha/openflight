import { useCallback, useEffect, useState } from 'react';

export interface A11yPrefs {
  reduceMotion: boolean;
  highContrast: boolean;
  largeText: boolean;
  colorBlind: boolean;
}

const DEFAULTS: A11yPrefs = { reduceMotion: false, highContrast: false, largeText: false, colorBlind: false };

const STORAGE_KEY = 'openflight.a11y';

function load(): A11yPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    // ignore
  }
  return { ...DEFAULTS };
}

function save(prefs: A11yPrefs): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // ignore
  }
}

export function applyA11yClasses(prefs: A11yPrefs): void {
  const el = document.documentElement;
  el.classList.toggle('a11y-reduce-motion', prefs.reduceMotion);
  el.classList.toggle('a11y-high-contrast', prefs.highContrast);
  el.classList.toggle('a11y-large-text', prefs.largeText);
  el.classList.toggle('a11y-color-blind', prefs.colorBlind);
}

export function useAccessibilitySettings() {
  const [prefs, setPrefs] = useState<A11yPrefs>(load);

  useEffect(() => {
    applyA11yClasses(prefs);
  }, [prefs]);

  const setPref = useCallback((key: keyof A11yPrefs, value: boolean) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      save(next);
      return next;
    });
  }, []);

  const applyRemote = useCallback((remote: Partial<A11yPrefs>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...remote };
      save(next);
      return next;
    });
  }, []);

  return { prefs, setPref, applyRemote };
}
