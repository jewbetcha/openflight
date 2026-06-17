import { useState, useCallback, useRef, useMemo, type ReactNode } from 'react';
import type { Shot } from '../types/shot';
import { ShotDataContext, ShotActionsContext } from './shotContext';

/** Duration to keep isNewShot true - covers the longest animation (shot-glow: 2s) */
const NEW_SHOT_DURATION_MS = 2500;

export function ShotProvider({ children }: { children: ReactNode }) {
  const [latestShot, setLatestShot] = useState<Shot | null>(null);
  const [shots, setShotsState] = useState<Shot[]>([]);
  const [isNewShot, setIsNewShot] = useState(false);
  const [shotVersion, setShotVersion] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const addShot = useCallback((shot: Shot) => {
    setLatestShot(shot);
    setShotsState((prev) => {
      const updated = [...prev, shot];
      // Keep only last 200 shots in UI state to prevent memory issues
      return updated.length > 200 ? updated.slice(-200) : updated;
    });

    setIsNewShot(true);
    setShotVersion((v) => v + 1);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setIsNewShot(false), NEW_SHOT_DURATION_MS);
  }, []);

  const setShots = useCallback((newShots: Shot[]) => {
    setShotsState(newShots);
    if (newShots.length > 0) {
      setLatestShot(newShots[newShots.length - 1]);
    }
    // Session restore - don't trigger animations
  }, []);

  const clearShots = useCallback(() => {
    setLatestShot(null);
    setShotsState([]);
    setIsNewShot(false);
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  // Memoized so the data value is referentially stable between renders that
  // don't change shots, and the actions value is stable for the whole lifetime
  // (callbacks are useCallback'd), letting action-only consumers skip re-renders.
  const data = useMemo(
    () => ({ latestShot, shots, isNewShot, shotVersion }),
    [latestShot, shots, isNewShot, shotVersion],
  );
  const actions = useMemo(
    () => ({ addShot, setShots, clearShots }),
    [addShot, setShots, clearShots],
  );

  return (
    <ShotActionsContext.Provider value={actions}>
      <ShotDataContext.Provider value={data}>{children}</ShotDataContext.Provider>
    </ShotActionsContext.Provider>
  );
}
