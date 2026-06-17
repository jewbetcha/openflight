import { useContext } from 'react';
import { ShotDataContext, type ShotData } from './shotContext';

/** Subscribe to shot data (latestShot/shots/isNewShot/shotVersion). Re-renders on every shot. */
export function useShotData(): ShotData {
  const ctx = useContext(ShotDataContext);
  if (!ctx) {
    throw new Error('useShotData must be used within a <ShotProvider>');
  }
  return ctx;
}
