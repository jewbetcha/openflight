// Per-club gauge maximums for the speed gauges. Pure data + lookups, kept out
// of the SpeedGauge component file so that module only exports a component.

// Ball speed maximums based on fastest recorded tour shots per club.
// Grouped so similar clubs share a range for a cleaner gauge fill.
const CLUB_GAUGE_MAX: Record<string, number> = {
  driver:    220,
  '3-wood':  200,
  '5-wood':  190,
  '7-wood':  185,
  '3-hybrid': 185,
  '5-hybrid': 178,
  '7-hybrid': 168,
  '9-hybrid': 158,
  '2-iron':  175,
  '3-iron':  170,
  '4-iron':  165,
  '5-iron':  160,
  '6-iron':  155,
  '7-iron':  150,
  '8-iron':  145,
  '9-iron':  140,
  pw:        135,
  gw:        130,
  sw:        120,
  lw:        115,
};

export function getGaugeMax(clubId: string): number {
  return CLUB_GAUGE_MAX[clubId] ?? 200;
}

const CLUB_HEAD_SPEED_MAX: Record<string, number> = {
  driver: 145, '3-wood': 130, '5-wood': 125, '7-wood': 120,
  '3-hybrid': 118, '5-hybrid': 114, '7-hybrid': 110, '9-hybrid': 106,
  '2-iron': 112, '3-iron': 108, '4-iron': 106, '5-iron': 102,
  '6-iron': 100, '7-iron': 96, '8-iron': 93, '9-iron': 90,
  pw: 86, gw: 84, sw: 80, lw: 76,
};

export function getClubHeadGaugeMax(clubId: string): number {
  return CLUB_HEAD_SPEED_MAX[clubId] ?? 130;
}
