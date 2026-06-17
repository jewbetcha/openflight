import { createContext } from 'react';
import type { Shot } from '../types/shot';

/**
 * Shot state is split into two contexts so that consumers which only dispatch
 * actions (e.g. the socket layer) do NOT re-render on every incoming shot, and
 * so that the chrome can avoid subscribing to data it doesn't display.
 *
 *  - ShotDataContext    changes on every shot (latestShot/shots/isNewShot/version)
 *  - ShotActionsContext is stable for the lifetime of the provider
 */

export interface ShotData {
  latestShot: Shot | null;
  shots: Shot[];
  isNewShot: boolean;
  /** Increments on every new shot - use as React key to force animation remount */
  shotVersion: number;
}

export interface ShotActions {
  addShot: (shot: Shot) => void;
  setShots: (shots: Shot[]) => void;
  clearShots: () => void;
}

export const ShotDataContext = createContext<ShotData | null>(null);
export const ShotActionsContext = createContext<ShotActions | null>(null);
