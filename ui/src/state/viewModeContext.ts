import { createContext } from 'react';
import type { ViewMode } from './viewMode';

export interface ViewModeValue {
  /** The chosen mode, or null until the first-run chooser is answered. */
  mode: ViewMode | null;
  /** Effective interactive (kiosk) mode - chosen mode, else the suggestion. */
  isInteractive: boolean;
  /** Whether the user has made a first-run choice yet. */
  chosen: boolean;
  /** Set + persist the mode live (no reload). */
  setMode: (mode: ViewMode) => void;
}

export const ViewModeContext = createContext<ViewModeValue | null>(null);
