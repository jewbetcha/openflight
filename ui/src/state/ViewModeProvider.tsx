import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ViewModeContext } from './viewModeContext';
import { readSavedMode, saveMode, type ViewMode } from './viewMode';
import { isLowPowerSearch, suggestedViewMode } from './displayDetect';

/**
 * Holds the view mode (Interactive vs Scoreboard) as reactive state so switching
 * it takes effect LIVE - no page reload, so keyboard/remote/SR focus is
 * preserved (WCAG 3.2.2). Owns the `tv` (big-screen scaling) / `low-power`
 * <html> classes (applied for Interactive mode) and announces the switch via a
 * polite live region.
 *
 * `mode` is null until the first-run chooser is answered; the effective mode
 * falls back to the auto-detected suggestion in the meantime.
 */
export function ViewModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ViewMode | null>(readSavedMode);
  const [suggested] = useState(suggestedViewMode);
  const [announcement, setAnnouncement] = useState('');

  const isInteractive = (mode ?? suggested) === 'interactive';
  const lowPower =
    isInteractive || (typeof window !== 'undefined' && isLowPowerSearch(window.location.search));

  // Apply the big-screen scaling classes live whenever the effective mode changes.
  useEffect(() => {
    const el = document.documentElement;
    el.classList.toggle('tv', isInteractive);
    el.classList.toggle('low-power', lowPower);
  }, [isInteractive, lowPower]);

  const setMode = useCallback((m: ViewMode) => {
    saveMode(m);
    setModeState(m);
    setAnnouncement(m === 'interactive' ? 'Interactive mode' : 'Scoreboard mode');
  }, []);

  const value = useMemo(
    () => ({ mode, isInteractive, chosen: mode !== null, setMode }),
    [mode, isInteractive, setMode],
  );

  return (
    <ViewModeContext.Provider value={value}>
      {children}
      <div className="sr-only" role="status" aria-live="polite">
        {announcement}
      </div>
    </ViewModeContext.Provider>
  );
}
