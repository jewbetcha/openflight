import { useEffect, useMemo, useState } from 'react';
import type { Shot } from '../types/shot';
import { computeStats, getUniqueClubs } from '../types/shot';

export interface SessionSummary {
  id: string;
  started_at: string | null;
  filename: string;
  shot_count: number;
}

export interface StatsData {
  sessionList: SessionSummary[];
  selectedSessionId: string | null;
  setSelectedSessionId: (id: string | null) => void;
  selectedClub: string | null;
  setSelectedClub: (club: string | null) => void;
  /** Live shots, or the loaded historical session's shots. */
  activeShots: Shot[];
  isHistorical: boolean;
  activeSession: SessionSummary | undefined;
  availableClubs: string[];
  clubCounts: Record<string, number>;
  /** activeShots narrowed to selectedClub (or all if none selected). */
  filteredShots: Shot[];
  stats: ReturnType<typeof computeStats>;
  loadingSession: boolean;
}

/**
 * Owns the Stats view's data orchestration: the session list, per-session shot
 * loading, the live-vs-historical switch, the club filter, and all derived
 * aggregates. Extracted from StatsView so this logic is isolated from the (very
 * large) rendering layer and can be exercised on its own.
 */
export function useStatsData(liveShots: Shot[]): StatsData {
  const [selectedClub, setSelectedClub] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionList, setSessionList] = useState<SessionSummary[]>([]);
  const [historicalShots, setHistoricalShots] = useState<Shot[] | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);

  useEffect(() => {
    fetch('/api/history')
      .then((r) => r.json())
      .then((d) => setSessionList(d.sessions ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Legitimate "fetch when the selected session changes" effect: reset to the
    // live session when cleared, otherwise show a spinner and load that
    // session's shots. The synchronous resets give immediate loading feedback,
    // which the set-state-in-effect heuristic over-flags for this valid pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (selectedSessionId === null) { setHistoricalShots(null); return; }
    setLoadingSession(true);
    setSelectedClub(null);
    fetch(`/api/history/${selectedSessionId}/shots`)
      .then((r) => r.json())
      .then((d) => { setHistoricalShots(d.shots ?? []); setLoadingSession(false); })
      .catch(() => { setHistoricalShots([]); setLoadingSession(false); });
  }, [selectedSessionId]);

  const activeShots = historicalShots ?? liveShots;
  const isHistorical = selectedSessionId !== null;
  const activeSession = sessionList.find((s) => s.id === selectedSessionId);
  const availableClubs = useMemo(() => getUniqueClubs(activeShots), [activeShots]);

  const clubCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const shot of activeShots) counts[shot.club] = (counts[shot.club] || 0) + 1;
    return counts;
  }, [activeShots]);

  const filteredShots = useMemo(
    () => (selectedClub === null ? activeShots : activeShots.filter((s) => s.club === selectedClub)),
    [activeShots, selectedClub],
  );

  const stats = useMemo(() => computeStats(filteredShots), [filteredShots]);

  return {
    sessionList,
    selectedSessionId,
    setSelectedSessionId,
    selectedClub,
    setSelectedClub,
    activeShots,
    isHistorical,
    activeSession,
    availableClubs,
    clubCounts,
    filteredShots,
    stats,
    loadingSession,
  };
}
