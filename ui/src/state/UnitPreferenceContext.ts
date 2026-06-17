import { createContext } from 'react';
import type { UnitSystem, SpeedUnit, DistanceUnit } from '../utils/units';

export interface UnitPreferenceContextValue {
  unitSystem: UnitSystem;
  speedUnit: SpeedUnit;
  distanceUnit: DistanceUnit;
  setUnitCombo: (speed: SpeedUnit, distance: DistanceUnit) => void;
  setUnitSystem: (unitSystem: UnitSystem) => void;
}

export const UnitPreferenceContext = createContext<UnitPreferenceContextValue | null>(null);
