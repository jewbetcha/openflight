export type UnitSystem = 'imperial' | 'metric';
export type SpeedUnit = 'mph' | 'kmh' | 'mps';
export type DistanceUnit = 'yards' | 'meters';

export type UnitCombo = { speed: SpeedUnit; distance: DistanceUnit; label: string };

export const UNIT_COMBOS: UnitCombo[] = [
  { speed: 'mph', distance: 'yards',  label: 'mph, yds' },
  { speed: 'mph', distance: 'meters', label: 'mph, m'   },
  { speed: 'kmh', distance: 'meters', label: 'km/h, m'  },
  { speed: 'kmh', distance: 'yards',  label: 'km/h, yds' },
  { speed: 'mps', distance: 'meters', label: 'm/s, m'   },
  { speed: 'mps', distance: 'yards',  label: 'm/s, yds' },
];

export function deriveUnitSystem(speed: SpeedUnit, distance: DistanceUnit): UnitSystem {
  return speed === 'mph' && distance === 'yards' ? 'imperial' : 'metric';
}

export function convertSpeedFromMph(speedMph: number, unit: SpeedUnit): number {
  if (unit === 'kmh') return speedMph * 1.60934;
  if (unit === 'mps') return speedMph * 0.44704;
  return speedMph;
}

export function convertDistanceFromYards(distanceYards: number, unit: DistanceUnit): number {
  return unit === 'meters' ? distanceYards * 0.9144 : distanceYards;
}

export function formatSpeed(speedMph: number, unit: SpeedUnit, digits = 1): string {
  return convertSpeedFromMph(speedMph, unit).toFixed(digits);
}

export function formatDistance(distanceYards: number, unit: DistanceUnit, digits = 0): string {
  return convertDistanceFromYards(distanceYards, unit).toFixed(digits);
}

export function getSpeedUnit(unit: SpeedUnit): string {
  const labels: Record<SpeedUnit, string> = { mph: 'mph', kmh: 'km/h', mps: 'm/s' };
  return labels[unit];
}

export function getDistanceUnit(unit: DistanceUnit): string {
  return unit === 'meters' ? 'm' : 'yds';
}

export function formatCarryRange(carryRange: [number, number], unit: DistanceUnit): string {
  const min = formatDistance(carryRange[0], unit, 0);
  const max = formatDistance(carryRange[1], unit, 0);
  return `${min}–${max} ${getDistanceUnit(unit)}`;
}
