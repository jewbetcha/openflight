import { useContext } from 'react';
import { ShotActionsContext, type ShotActions } from './shotContext';

/** Dispatch shot actions (addShot/setShots/clearShots). Stable - does not re-render on shots. */
export function useShotActions(): ShotActions {
  const ctx = useContext(ShotActionsContext);
  if (!ctx) {
    throw new Error('useShotActions must be used within a <ShotProvider>');
  }
  return ctx;
}
