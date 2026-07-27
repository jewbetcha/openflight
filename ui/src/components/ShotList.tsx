import { useMemo, useState, memo } from 'react';
import type { Shot } from '../types/shot';
import { useUnitPreference } from '../state/useUnitPreference';
import type { UnitSystem } from '../utils/units';
import { formatDistance, formatSpeed, getDistanceUnit } from '../utils/units';
import './ShotList.css';

const SHOTS_PER_PAGE = 5;

interface ShotListProps {
  shots: Shot[];
}

interface ShotRowProps {
  shot: Shot;
  shotNumber: number;
  unitSystem: UnitSystem;
  distanceUnit: string;
}

const ShotRow = memo(function ShotRow({ shot, shotNumber, unitSystem, distanceUnit }: ShotRowProps) {
  return (
    <div className="shot-row">
      <span className="shot-row__number">#{shotNumber}</span>
      <span className="shot-row__club">{shot.club}</span>
      <span className="shot-row__ball">{shot.ball_name ?? 'Unknown Ball'}</span>
      <span className="shot-row__stat">
        <span className="shot-row__value">{formatSpeed(shot.ball_speed_mph, unitSystem, 1)}</span>
        <span className="shot-row__label">ball</span>
      </span>
      <span className="shot-row__stat">
        <span className="shot-row__value">
          {shot.club_speed_mph ? formatSpeed(shot.club_speed_mph, unitSystem, 1) : '—'}
        </span>
        <span className="shot-row__label">club</span>
      </span>
      <span className="shot-row__stat">
        <span className="shot-row__value">
          {shot.launch_angle_vertical !== null ? `${shot.launch_angle_vertical.toFixed(1)}°` : '—'}
        </span>
        <span className="shot-row__label">launch</span>
      </span>
      <span className="shot-row__stat">
        <span className="shot-row__value">
          {shot.spin_rpm !== null ? shot.spin_rpm.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—'}
        </span>
        <span className="shot-row__label">spin</span>
      </span>
      <span className="shot-row__stat shot-row__stat--carry">
        <span className="shot-row__value">{formatDistance(shot.estimated_carry_yards, unitSystem, 0)}</span>
        <span className="shot-row__label">{distanceUnit}</span>
      </span>
    </div>
  );
});

export function ShotList({ shots }: ShotListProps) {
  const [page, setPage] = useState(0);
  const { unitSystem } = useUnitPreference();
  const distanceUnit = getDistanceUnit(unitSystem);

  const totalPages = Math.ceil(shots.length / SHOTS_PER_PAGE);

  const pageShots = useMemo(() => {
    const reversed = [...shots].reverse();
    const startIndex = page * SHOTS_PER_PAGE;
    return reversed.slice(startIndex, startIndex + SHOTS_PER_PAGE);
  }, [shots, page]);

  const startIndex = page * SHOTS_PER_PAGE;

  if (shots.length === 0) {
    return (
      <div className="shot-list shot-list--empty">
        <p>No shots recorded yet</p>
      </div>
    );
  }

  return (
    <div className="shot-list">
      <div className="shot-list__rows">
        {pageShots.map((shot, index) => (
          <ShotRow
            key={shot.timestamp}
            shot={shot}
            shotNumber={shots.length - startIndex - index}
            unitSystem={unitSystem}
            distanceUnit={distanceUnit}
          />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="pagination__button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            Prev
          </button>
          <span className="pagination__info">
            {page + 1} / {totalPages}
          </span>
          <button
            className="pagination__button"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
