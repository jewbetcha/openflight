import { create } from 'zustand';
import type { UnitSystem } from '../utils/units';

const STORAGE_KEY = 'openflight.unit-system';

function readStoredUnitSystem(): UnitSystem {
  if (typeof window === 'undefined') {
    return 'imperial';
  }

  const storedValue = window.localStorage.getItem(STORAGE_KEY);
  return storedValue === 'metric' ? 'metric' : 'imperial';
}

interface UnitPreferenceState {
  unitSystem: UnitSystem;
  setUnitSystem: (unitSystem: UnitSystem) => void;
}

export const useUnitPreferenceStore = create<UnitPreferenceState>((set) => ({
  unitSystem: readStoredUnitSystem(),
  setUnitSystem: (unitSystem) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, unitSystem);
    }

    set({ unitSystem });
  },
}));
