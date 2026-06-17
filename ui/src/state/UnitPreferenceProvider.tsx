import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { SpeedUnit, DistanceUnit, UnitSystem } from '../utils/units';
import { deriveUnitSystem } from '../utils/units';
import { UnitPreferenceContext } from './UnitPreferenceContext';

const SPEED_KEY = 'openflight.speedUnit';
const DISTANCE_KEY = 'openflight.distanceUnit';

function readSpeedUnit(): SpeedUnit {
  if (typeof window === 'undefined') return 'mph';
  const v = window.localStorage.getItem(SPEED_KEY);
  if (v === 'kmh' || v === 'mps') return v;
  // Migrate legacy 'openflight.unit-system'
  const legacy = window.localStorage.getItem('openflight.unit-system');
  return legacy === 'metric' ? 'kmh' : 'mph';
}

function readDistanceUnit(): DistanceUnit {
  if (typeof window === 'undefined') return 'yards';
  const v = window.localStorage.getItem(DISTANCE_KEY);
  if (v === 'meters') return 'meters';
  const legacy = window.localStorage.getItem('openflight.unit-system');
  return legacy === 'metric' ? 'meters' : 'yards';
}

export function UnitPreferenceProvider({ children }: { children: ReactNode }) {
  const [speedUnit, setSpeedUnitState] = useState<SpeedUnit>(readSpeedUnit);
  const [distanceUnit, setDistanceUnitState] = useState<DistanceUnit>(readDistanceUnit);

  useEffect(() => {
    window.localStorage.setItem(SPEED_KEY, speedUnit);
    window.localStorage.setItem(DISTANCE_KEY, distanceUnit);
  }, [speedUnit, distanceUnit]);

  const setUnitCombo = useCallback((speed: SpeedUnit, distance: DistanceUnit) => {
    setSpeedUnitState(speed);
    setDistanceUnitState(distance);
  }, []);

  const setUnitSystem = useCallback((system: UnitSystem) => {
    setUnitCombo(system === 'imperial' ? 'mph' : 'kmh', system === 'imperial' ? 'yards' : 'meters');
  }, [setUnitCombo]);

  const unitSystem = useMemo(() => deriveUnitSystem(speedUnit, distanceUnit), [speedUnit, distanceUnit]);

  const value = useMemo(
    () => ({ unitSystem, speedUnit, distanceUnit, setUnitCombo, setUnitSystem }),
    [unitSystem, speedUnit, distanceUnit, setUnitCombo, setUnitSystem],
  );

  return <UnitPreferenceContext.Provider value={value}>{children}</UnitPreferenceContext.Provider>;
}
