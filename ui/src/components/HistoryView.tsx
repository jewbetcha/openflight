import { useEffect, useState } from 'react';
import { useUnitPreference } from '../state/useUnitPreference';
import { useLanguage } from '../state/useLanguage';
import { convertSpeedFromMph, getSpeedUnit } from '../utils/units';
import type { Shot } from '../types/shot';
import { ShotList } from './ShotList';
import './HistoryView.css';

interface SessionSummary {
  id: string;
  started_at: string | null;
  filename: string;
  shot_count: number;
  max_ball_speed: number | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function HistoryView() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SessionSummary | null>(null);
  const [sessionShots, setSessionShots] = useState<Shot[] | null>(null);
  const [loadingShots, setLoadingShots] = useState(false);
  const { speedUnit } = useUnitPreference();
  const { t } = useLanguage();

  useEffect(() => {
    fetch('/api/history')
      .then((r) => r.json())
      .then((d) => { setSessions(d.sessions ?? []); setLoading(false); })
      .catch(() => { setError('Could not load history.'); setLoading(false); });
  }, []);

  const openSession = (s: SessionSummary) => {
    if (s.shot_count === 0) return;
    setSelected(s);
    setSessionShots(null);
    setLoadingShots(true);
    fetch(`/api/history/${encodeURIComponent(s.id)}/shots`)
      .then((r) => r.json())
      .then((d) => {
        const shots = Array.isArray(d.shots) ? d.shots : [];
        setSessionShots(shots);
        setLoadingShots(false);
      })
      .catch(() => { setSessionShots([]); setLoadingShots(false); });
  };

  const closeSession = () => {
    setSelected(null);
    setSessionShots(null);
  };

  const speedLabel = getSpeedUnit(speedUnit);

  if (loading) {
    return (
      <div className="history-view history-view--empty">
        <p className="history-view__message">{t('loading')}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="history-view history-view--empty">
        <p className="history-view__message">{t('historyError')}</p>
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <div className="history-view history-view--empty">
        <p className="history-view__message">{t('historyEmpty')}</p>
        <p className="history-view__sub">{t('historyEmptySub')}</p>
      </div>
    );
  }

  // Session drill-down view
  if (selected) {
    return (
      <div className="history-view history-view--session">
        <div className="history-session__header">
          <button className="history-session__back" onClick={closeSession} aria-label={t('a11yBackToSessions')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16" aria-hidden="true">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
            {t('back')}
          </button>
          <div className="history-session__info">
            <span className="history-session__date">{formatDate(selected.started_at)}</span>
            <span className="history-session__count">{selected.shot_count} {t('shotCount')}</span>
          </div>
        </div>
        {loadingShots ? (
          <div className="history-session__loading">
            <p className="history-view__message">{t('loading')}</p>
          </div>
        ) : (
          <div className="history-session__shots">
            <ShotList shots={sessionShots ?? []} />
          </div>
        )}
      </div>
    );
  }

  // Session list view
  return (
    <div className="history-view">
      <h2 className="history-view__heading">{t('pastSessions')}</h2>
      <ul className="history-list" role="list">
        {sessions.map((s) => {
          const speed = s.max_ball_speed != null
            ? `${convertSpeedFromMph(s.max_ball_speed, speedUnit).toFixed(0)} ${speedLabel}`
            : null;
          const clickable = s.shot_count > 0;
          return (
            <li
              key={s.id}
              className={`history-card${clickable ? ' history-card--clickable' : ''}`}
              onClick={clickable ? () => openSession(s) : undefined}
              role={clickable ? 'button' : undefined}
              tabIndex={clickable ? 0 : undefined}
              onKeyDown={clickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openSession(s); } } : undefined}
              aria-label={clickable ? `${formatDate(s.started_at)}, ${s.shot_count} shots` : undefined}
            >
              <div className="history-card__meta">
                <span className="history-card__date">{formatDate(s.started_at)}</span>
                <span className="history-card__shots">{s.shot_count} {t('shotCount')}</span>
              </div>
              {speed && (
                <div className="history-card__stat">
                  <span className="history-card__stat-label">{t('bestSpeed')}</span>
                  <span className="history-card__stat-value">{speed}</span>
                </div>
              )}
              {clickable && (
                <svg className="history-card__chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="16" height="16" aria-hidden="true">
                  <path d="M9 18l6-6-6-6" />
                </svg>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
