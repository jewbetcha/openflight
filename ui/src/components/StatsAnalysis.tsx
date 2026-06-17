import { useMemo, useCallback } from 'react';
import type { DistanceUnit } from '../utils/units';
import type { Shot } from '../types/shot';
import { useThemeColors } from '../state/useThemeColors';
import { useLanguage } from '../state/useLanguage';
import {
  computeStrikeQuality,
  buildDistanceProfiles,
  generateInsights,
  buildRootCause,
  suggestDrills,
  type StrikeQuality,
  type InsightPriority,
} from '../utils/analysis';
import { interpolate, type TKey } from '../i18n/translations';
import './StatsAnalysis.css';

interface Props {
  shots: Shot[];
  allShots: Shot[];
  distUnit: DistanceUnit;
}

// ── Score Gauge (SVG arc) ──────────────────────────────────────────────────────

const GCX = 50, GCY = 52, GR = 38;
const START_DEG = 145, SWEEP = 250;

function polarToXY(deg: number) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: GCX + GR * Math.cos(rad), y: GCY + GR * Math.sin(rad) };
}

function arcD(startDeg: number, endDeg: number): string {
  const s = polarToXY(startDeg);
  const e = polarToXY(endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${GR} ${GR} 0 ${large} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
}

function ScoreGauge({ sq }: { sq: StrikeQuality }) {
  const theme = useThemeColors();
  const { t } = useLanguage();
  const fillEnd = START_DEG + (sq.score / 100) * SWEEP;
  const color = theme.scoreColors[sq.label] ?? theme.gold;
  const translatedLabel =
    sq.label === 'Elite' ? t('scoreLabelElite') :
    sq.label === 'Solid' ? t('scoreLabelSolid') :
    sq.label === 'Developing' ? t('scoreLabelDeveloping') :
    t('scoreLabelOpportunity');

  return (
    <div className="sq-gauge">
      <svg viewBox="0 0 100 100" className="sq-gauge__svg" role="img" aria-label={`Strike quality score: ${sq.score} out of 100`}>
        {/* Track */}
        <path d={arcD(START_DEG, START_DEG + SWEEP)} fill="none" stroke="rgba(245,240,230,0.07)" strokeWidth="7" strokeLinecap="round" />
        {/* Fill */}
        {sq.score > 1 && (
          <path
            d={arcD(START_DEG, fillEnd)}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 5px ${color}99)` }}
          />
        )}
        {/* Score */}
        <text x={GCX} y={GCY - 3} textAnchor="middle" fontSize="22" fontWeight="700" fill={color} fontFamily="inherit">
          {sq.score}
        </text>
        <text x={GCX} y={GCY + 11} textAnchor="middle" fontSize="7" fill="rgba(245,240,230,0.38)" fontFamily="inherit" letterSpacing="0.06em">
          / 100
        </text>
      </svg>
      <div className="sq-gauge__label" style={{ color }}>{translatedLabel}</div>
      {sq.distanceLostYds > 0 && (
        <div className="sq-gauge__upside">+{sq.distanceLostYds} {t('distancePotential')}</div>
      )}
    </div>
  );
}

// ── Priority helpers ───────────────────────────────────────────────────────────

// ── Main component ─────────────────────────────────────────────────────────────

export function StatsAnalysis({ shots, allShots, distUnit }: Props) {
  const theme    = useThemeColors();
  const { t }    = useLanguage();
  const pLabel = (priority: InsightPriority) =>
    priority === 'high' ? t('insightPriority') :
    priority === 'medium' ? t('insightOpportunity') :
    t('insightGood');
  const ti = useCallback(
    (key: TKey, vars?: Record<string, string | number>) => vars ? interpolate(t(key), vars) : t(key),
    [t],
  );
  const sq       = useMemo(() => computeStrikeQuality(shots),               [shots]);
  const profiles = useMemo(() => buildDistanceProfiles(allShots, distUnit), [allShots, distUnit]);
  const insights = useMemo(() => generateInsights(shots, distUnit, ti),     [shots, distUnit, ti]);
  const rootCause= useMemo(() => buildRootCause(shots, ti),                 [shots, ti]);
  const drills   = useMemo(() => suggestDrills(shots, t),                   [shots, t]);

  if (shots.length < 3) {
    return (
      <div className="stats-analysis stats-analysis--empty">
        <p>{t('analysisMinShots')}</p>
      </div>
    );
  }

  return (
    <div className="stats-analysis">

      {/* ── Top row: Strike Quality + Insights ── */}
      <div className="analysis-top">

        {sq && (
          <div className="analysis-card analysis-card--sq">
            <span className="analysis-card__title">{t('strikeQuality')}</span>
            <ScoreGauge sq={sq} />
            <div className="sq-stats">
              <div className="sq-stat">
                <span className="sq-stat__val">{sq.smashAvg.toFixed(2)}</span>
                <span className="sq-stat__lbl">{t('smashAvg')}</span>
              </div>
              <div className="sq-stat__sep" aria-hidden="true" />
              <div className="sq-stat">
                <span className="sq-stat__val">{sq.smashTarget.toFixed(2)}</span>
                <span className="sq-stat__lbl">{t('smashTarget')}</span>
              </div>
              <div className="sq-stat__sep" aria-hidden="true" />
              <div className="sq-stat">
                <span className="sq-stat__val">{sq.consistencyPct}%</span>
                <span className="sq-stat__lbl">{t('spreadCV')}</span>
              </div>
            </div>
          </div>
        )}

        <div className="analysis-card analysis-card--insights">
          <span className="analysis-card__title">{t('insightsTitle')}</span>
          {insights.length === 0 ? (
            <p className="analysis-empty-note">{t('noInsights')}</p>
          ) : (
            <div className="insights-list">
              {insights.slice(0, 3).map((ins) => (
                <div key={ins.id} className="insight">
                  <div
                    className="insight__dot"
                    style={{ background: theme.priorityColors[ins.priority] }}
                    aria-hidden="true"
                  />
                  <div className="insight__body">
                    <div className="insight__meta">
                      <span className="insight__priority" style={{ color: theme.priorityColors[ins.priority] }}>
                        {pLabel(ins.priority)}
                      </span>
                      <span className="insight__category">{t(ins.category as import('../i18n/translations').TKey)}</span>
                      {ins.opportunity && (
                        <span className="insight__opp">{ins.opportunity}</span>
                      )}
                    </div>
                    <p className="insight__headline">{ins.headline}</p>
                    <p className="insight__detail">{ins.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Distance table ── */}
      {profiles.length >= 2 && (
        <div className="analysis-card">
          <span className="analysis-card__title">{t('knowYourDistances')}</span>
          <div className="distance-table-wrap">
            <table className="distance-table" aria-label={t('a11yCarryByClub')}>
              <thead>
                <tr>
                  <th className="dt__h dt__h--club">{t('clubLabel')}</th>
                  <th className="dt__h dt__h--num">{t('colAvg')}</th>
                  <th className="dt__h dt__h--num">±</th>
                  <th className="dt__h dt__h--num">{t('colReliable')}</th>
                  <th className="dt__h dt__h--num">{t('colConservative')}</th>
                  <th className="dt__h dt__h--num">{t('colCount')}</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.club} className="dt__row">
                    <td className="dt__d dt__d--club">{p.club.toUpperCase()}</td>
                    <td className="dt__d dt__d--primary">{p.avg}</td>
                    <td className="dt__d">±{p.sd}</td>
                    <td className="dt__d">{p.reliable}</td>
                    <td className="dt__d">{p.conservative}</td>
                    <td className="dt__d">{p.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="distance-table__note">
            {t('distanceTableNote')} {distUnit === 'meters' ? 'm' : 'yds'}
          </p>
        </div>
      )}

      {/* ── Bottom row: Root Cause + Drills ── */}
      {(rootCause || drills.length > 0) && (
        <div className="analysis-bottom">

          {rootCause && (
            <div className="analysis-card">
              <span className="analysis-card__title">{t('rootCauseChain')}</span>
              <div className="cause-chain">
                {rootCause.chain.map((node, i) => (
                  <div key={i} className="cause-node">
                    <div className="cause-node__marker" aria-hidden="true" />
                    <div className="cause-node__text">
                      <span className="cause-node__label">{node.label}</span>
                      {node.sub && <span className="cause-node__sub">{node.sub}</span>}
                    </div>
                    {i < rootCause.chain.length - 1 && (
                      <div className="cause-node__connector" aria-hidden="true" />
                    )}
                  </div>
                ))}
                <div className="cause-fix">
                  <span className="cause-fix__label">{t('causeFix')}</span>
                  <span className="cause-fix__text">{rootCause.fix}</span>
                </div>
              </div>
            </div>
          )}

          {drills.length > 0 && (
            <div className="analysis-card">
              <span className="analysis-card__title">{t('practiceDrills')}</span>
              <div className="drills">
                {drills.map((drill) => (
                  <div key={drill.number} className="drill">
                    <div className="drill__num" aria-hidden="true">{drill.number}</div>
                    <div className="drill__body">
                      <p className="drill__title">{drill.title}</p>
                      <p className="drill__desc">{drill.description}</p>
                      <p className="drill__thought">{drill.keyThought}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
