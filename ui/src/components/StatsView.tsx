import { useMemo, useState } from 'react';
import { useUnitPreference } from '../state/useUnitPreference';
import type { Shot } from '../types/shot';
import { computeStats, computeSwingSpeedStats, getUniqueClubs, isSwingSpeedShot } from '../types/shot';
import { formatDistance, formatSpeed, getDistanceUnit, getSpeedUnit } from '../utils/units';
import './StatsView.css';

interface StatsViewProps {
  shots: Shot[];
  activeClub: string;
  onClearSession: () => void;
}

export function StatsView({ shots, activeClub, onClearSession }: StatsViewProps) {
  const hasShotsForActiveClub = shots.some((s) => s.club === activeClub);
  const [selectedClub, setSelectedClub] = useState<string | null>(hasShotsForActiveClub ? activeClub : null);
  const [prevActiveClub, setPrevActiveClub] = useState(activeClub);

  // React recommended pattern: update state during render when a prop changes, rather than in useEffect
  if (activeClub !== prevActiveClub) {
    setPrevActiveClub(activeClub);
    setSelectedClub(hasShotsForActiveClub ? activeClub : null);
  }

  const { unitSystem } = useUnitPreference();
  const speedUnit = getSpeedUnit(unitSystem);
  const distanceUnit = getDistanceUnit(unitSystem);

  const availableClubs = useMemo(() => getUniqueClubs(shots), [shots]);

  const clubCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const shot of shots) {
      counts[shot.club] = (counts[shot.club] || 0) + 1;
    }
    return counts;
  }, [shots]);

  const filteredShots = useMemo(() => {
    if (selectedClub === null) return shots;
    return shots.filter((s) => s.club === selectedClub);
  }, [shots, selectedClub]);

  const stats = useMemo(() => computeStats(filteredShots), [filteredShots]);
  const isSwingSpeedSession = filteredShots.length > 0 && filteredShots.every(isSwingSpeedShot);
  const swingStats = useMemo(() => computeSwingSpeedStats(filteredShots), [filteredShots]);

  if (shots.length === 0) {
    return (
      <div className="stats-view stats-view--empty">
        <p>No shots recorded yet</p>
      </div>
    );
  }

  return (
    <div className="stats-view">
      <div className="club-tabs">
        <button
          className={`club-tabs__tab ${selectedClub === null ? 'club-tabs__tab--active' : ''}`}
          onClick={() => setSelectedClub(null)}
        >
          All ({shots.length})
        </button>
        {availableClubs.map((club) => (
          <button
            key={club}
            className={`club-tabs__tab ${selectedClub === club ? 'club-tabs__tab--active' : ''}`}
            onClick={() => setSelectedClub(club)}
          >
            {club.toUpperCase()} ({clubCounts[club] || 0})
          </button>
        ))}
      </div>

      {isSwingSpeedSession ? (
        <div className="stats-grid stats-grid--swing-speed">
          <div className="stat-card">
            <span className="stat-card__value">{swingStats.count}</span>
            <span className="stat-card__label">Swings</span>
          </div>
          <div className="stat-card stat-card--primary">
            <span className="stat-card__value">{formatSpeed(swingStats.last_speed_mph, unitSystem, 1)}</span>
            <span className="stat-card__label">Last ({speedUnit})</span>
          </div>
          <div className="stat-card stat-card--primary">
            <span className="stat-card__value">{formatSpeed(swingStats.best_speed_mph, unitSystem, 1)}</span>
            <span className="stat-card__label">Best ({speedUnit})</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value">{formatSpeed(swingStats.avg_speed_mph, unitSystem, 1)}</span>
            <span className="stat-card__label">Average ({speedUnit})</span>
          </div>
        </div>
      ) : (
        <div className="stats-grid">
          <div className="stat-card">
            <span className="stat-card__value">{stats.shot_count}</span>
            <span className="stat-card__label">Shots</span>
          </div>
          <div className="stat-card stat-card--primary">
            <span className="stat-card__value">{formatSpeed(stats.avg_ball_speed, unitSystem, 1)}</span>
            <span className="stat-card__label">Avg Ball ({speedUnit})</span>
          </div>
          <div className="stat-card">
            <span className="stat-card__value">{formatSpeed(stats.max_ball_speed, unitSystem, 1)}</span>
            <span className="stat-card__label">Max Ball ({speedUnit})</span>
          </div>
          <div className="stat-card stat-card--primary">
            <span className="stat-card__value">{formatDistance(stats.avg_carry_est, unitSystem, 0)}</span>
            <span className="stat-card__label">Avg Carry ({distanceUnit})</span>
          </div>
          {stats.avg_club_speed && (
            <div className="stat-card">
              <span className="stat-card__value">{formatSpeed(stats.avg_club_speed, unitSystem, 1)}</span>
              <span className="stat-card__label">Avg Club ({speedUnit})</span>
            </div>
          )}
          {stats.avg_smash_factor && (
            <div className="stat-card">
              <span className="stat-card__value">{stats.avg_smash_factor.toFixed(2)}</span>
              <span className="stat-card__label">Avg Smash</span>
            </div>
          )}
        </div>
      )}

      <button className="clear-button" onClick={onClearSession}>
        Clear Session
      </button>
    </div>
  );
}
