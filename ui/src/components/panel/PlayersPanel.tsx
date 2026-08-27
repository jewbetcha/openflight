import { useMemo, useRef, type ReactNode } from 'react';
import type { Shot } from '../../types/shot';
import { filterShotsByPlayer } from '../../types/shot';
import { useDragScroll } from '../../hooks/useDragScroll';
import { useI18n } from '../../i18n/useI18n';
import { PanelHeader } from './PanelHeader';

interface PlayersPanelProps {
  players: string[];
  selectedPlayer: string;
  shots: Shot[];
  onSelectPlayer: (name: string) => void;
  onRemovePlayer: (name: string) => void;
  /** Pinned header control, e.g. Add player. */
  headerAction?: ReactNode;
}

export function PlayersPanel({
  players,
  selectedPlayer,
  shots,
  onSelectPlayer,
  onRemovePlayer,
  headerAction,
}: PlayersPanelProps) {
  const { t } = useI18n();
  const rosterRef = useRef<HTMLDivElement>(null);
  const dragScroll = useDragScroll(rosterRef);
  const canRemove = players.length > 1;
  const shotCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const playerName of players) {
      counts[playerName] = filterShotsByPlayer(shots, playerName).length;
    }
    return counts;
  }, [players, shots]);

  return (
    <div className="panel">
      <PanelHeader title={t('nav.players')} subtitle={selectedPlayer} actions={headerAction} />
      <div
        className="panel__body players-panel__grid"
        role="region"
        aria-label={t('players.rosterAria')}
        ref={rosterRef}
        onPointerDown={dragScroll.onPointerDown}
        onPointerMove={dragScroll.onPointerMove}
        onPointerUp={dragScroll.onPointerUp}
        onPointerCancel={dragScroll.onPointerCancel}
        onClickCapture={dragScroll.onClickCapture}
      >
        {players.map((playerName) => {
          const selected = playerName === selectedPlayer;
          const count = shotCounts[playerName] ?? 0;
          const shotLabel = t(count === 1 ? 'players.shot' : 'players.shots', { count });

          return (
            <div className="players-panel__card-wrap" key={playerName}>
              <button
                type="button"
                className={`players-panel__card${selected ? ' players-panel__card--selected' : ''}`}
                aria-pressed={selected}
                onClick={() => onSelectPlayer(playerName)}
              >
                <span className="players-panel__name">{playerName}</span>
                <span className="players-panel__count">{shotLabel}</span>
              </button>
              {canRemove && !selected ? (
                <button
                  type="button"
                  className="players-panel__remove"
                  aria-label={t('menu.removePlayer', { name: playerName })}
                  onClick={() => onRemovePlayer(playerName)}
                >
                  ✕
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
