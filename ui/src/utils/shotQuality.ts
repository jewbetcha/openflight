// Source: PGA Tour averages & coaching norms by club group.
// Quality: 'low' = below ideal, 'medium' = PERFECT, 'high' = above ideal.

export type Quality = 'low' | 'medium' | 'high';
export type Range = { min: number; max: number };

export interface ClubRanges {
  vLaunch: Range;
  aoa: Range;
  hLaunch: Range; // absolute value - ±symmetrical
  spin: Range;
}

const CLUB_RANGES: Record<string, ClubRanges> = {
  driver:      { vLaunch: { min: 12, max: 15 }, aoa: { min:  2, max:  5 }, hLaunch: { min: 0, max: 1  }, spin: { min: 2000, max: 2600  } },
  '3-wood':    { vLaunch: { min: 11, max: 14 }, aoa: { min: -2, max:  1 }, hLaunch: { min: 0, max: 2  }, spin: { min: 2500, max: 3500  } },
  '5-wood':    { vLaunch: { min: 13, max: 16 }, aoa: { min: -2, max:  0 }, hLaunch: { min: 0, max: 2  }, spin: { min: 3000, max: 3800  } },
  '7-wood':    { vLaunch: { min: 13, max: 17 }, aoa: { min: -2, max:  0 }, hLaunch: { min: 0, max: 2  }, spin: { min: 3200, max: 4200  } },
  '3-hybrid':  { vLaunch: { min: 14, max: 18 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 3500, max: 5000  } },
  '5-hybrid':  { vLaunch: { min: 14, max: 18 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 4000, max: 5500  } },
  '7-hybrid':  { vLaunch: { min: 15, max: 19 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 4500, max: 6000  } },
  '9-hybrid':  { vLaunch: { min: 16, max: 20 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 5000, max: 6500  } },
  '2-iron':    { vLaunch: { min: 14, max: 17 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 3500, max: 5000  } },
  '3-iron':    { vLaunch: { min: 14, max: 18 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 4000, max: 5500  } },
  '4-iron':    { vLaunch: { min: 15, max: 18 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 4500, max: 6000  } },
  '5-iron':    { vLaunch: { min: 15, max: 19 }, aoa: { min: -4, max: -2 }, hLaunch: { min: 0, max: 2  }, spin: { min: 5000, max: 6500  } },
  '6-iron':    { vLaunch: { min: 16, max: 20 }, aoa: { min: -4, max: -3 }, hLaunch: { min: 0, max: 2  }, spin: { min: 5500, max: 7000  } },
  '7-iron':    { vLaunch: { min: 16, max: 22 }, aoa: { min: -5, max: -3 }, hLaunch: { min: 0, max: 2  }, spin: { min: 6000, max: 8000  } },
  '8-iron':    { vLaunch: { min: 18, max: 24 }, aoa: { min: -5, max: -3 }, hLaunch: { min: 0, max: 2  }, spin: { min: 7000, max: 8500  } },
  '9-iron':    { vLaunch: { min: 20, max: 26 }, aoa: { min: -5, max: -3 }, hLaunch: { min: 0, max: 2  }, spin: { min: 7500, max: 9000  } },
  pw:          { vLaunch: { min: 25, max: 30 }, aoa: { min: -6, max: -4 }, hLaunch: { min: 0, max: 1  }, spin: { min: 7000, max: 9000  } },
  gw:          { vLaunch: { min: 26, max: 31 }, aoa: { min: -6, max: -4 }, hLaunch: { min: 0, max: 1  }, spin: { min: 7500, max: 9000  } },
  sw:          { vLaunch: { min: 28, max: 34 }, aoa: { min: -8, max: -6 }, hLaunch: { min: 0, max: 1  }, spin: { min: 9000, max: 11000 } },
  lw:          { vLaunch: { min: 30, max: 36 }, aoa: { min: -10, max: -6 }, hLaunch: { min: 0, max: 1  }, spin: { min: 9000, max: 12000 } },
};

export const DEFAULT_RANGES: ClubRanges = {
  vLaunch: { min: 14, max: 22 },
  aoa:     { min: -5, max:  0 },
  hLaunch: { min:  0, max:  2 },
  spin:    { min: 4000, max: 8000 },
};

export function getRanges(clubId: string): ClubRanges {
  return CLUB_RANGES[clubId] ?? DEFAULT_RANGES;
}

export function inRange(value: number, range: Range): Quality {
  if (value < range.min) return 'low';
  if (value > range.max) return 'high';
  return 'medium';
}

export function hLaunchQuality(deg: number | null, range: Range): Quality | null {
  if (deg === null) return null;
  return inRange(Math.abs(deg), range);
}
