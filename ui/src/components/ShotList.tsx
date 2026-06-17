import { useMemo, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import type { Shot } from '../types/shot';
import { useUnitPreference } from '../state/useUnitPreference';
import { useLanguage } from '../state/useLanguage';
import { useThemeColors } from '../state/useThemeColors';
import type { TKey } from '../i18n/translations';
import type { SpeedUnit, DistanceUnit } from '../utils/units';
import {
  formatDistance, formatSpeed,
  getDistanceUnit, getSpeedUnit,
  convertDistanceFromYards,
} from '../utils/units';
import { getRanges, inRange, hLaunchQuality } from '../utils/shotQuality';
import type { Quality } from '../utils/shotQuality';
import './ShotList.css';

const SHOTS_PER_PAGE = 12;

// ── Column definitions ────────────────────────────────────────────────────────

type ColGroup = 'distance' | 'speed' | 'launch' | 'club' | 'spin';

interface CellData {
  value: string;
  unit?: string;
  quality?: Quality | null;
  raw?: number | null;
}

interface ColDef {
  id: string;
  labelKey: TKey;
  group: ColGroup;
  defaultOn: boolean;
  render: (shot: Shot, du: DistanceUnit, su: SpeedUnit, t: (k: TKey) => string) => CellData;
}

const COLS: ColDef[] = [
  // ── Distance ──────────────────────────────────────────────────────────────
  {
    id: 'carry', labelKey: 'estCarry', group: 'distance', defaultOn: true,
    render: (s, du) => {
      const v = s.carry_spin_adjusted ?? s.estimated_carry_yards;
      return { value: formatDistance(v, du, 0), unit: getDistanceUnit(du), raw: v };
    },
  },
  {
    id: 'total', labelKey: 'colTotal', group: 'distance', defaultOn: false,
    render: (s, du) => {
      const v = s.total_distance_yards ?? null;
      return { value: v != null ? formatDistance(v, du, 0) : '-', unit: v != null ? getDistanceUnit(du) : undefined, raw: v };
    },
  },
  {
    id: 'roll', labelKey: 'colRoll', group: 'distance', defaultOn: false,
    render: (s, du) => {
      const carry = s.carry_spin_adjusted ?? s.estimated_carry_yards;
      const total = s.total_distance_yards;
      if (total == null) return { value: '-' };
      const raw = Math.max(0, total - carry);
      return { value: formatDistance(raw, du, 0), unit: getDistanceUnit(du), raw };
    },
  },
  {
    id: 'apex', labelKey: 'colApex', group: 'distance', defaultOn: false,
    render: (s, du) => {
      const v = s.apex_height_yards ?? null;
      return { value: v != null ? formatDistance(v, du, 0) : '-', unit: v != null ? getDistanceUnit(du) : undefined, raw: v };
    },
  },
  {
    id: 'deviation', labelKey: 'colDeviation', group: 'distance', defaultOn: false,
    render: (s, du) => {
      const v = s.carry_side_yards ?? null;
      if (v == null) return { value: '-' };
      const conv = convertDistanceFromYards(Math.abs(v), du);
      const formatted = (v >= 0 ? '+' : '−') + conv.toFixed(1);
      const abs = Math.abs(v);
      const quality: Quality = abs <= 5 ? 'medium' : 'low';
      return { value: formatted, unit: getDistanceUnit(du), quality, raw: v };
    },
  },
  // ── Speed ─────────────────────────────────────────────────────────────────
  {
    id: 'ballSpeed', labelKey: 'ballSpeed', group: 'speed', defaultOn: true,
    render: (s, _, su) => ({
      value: formatSpeed(s.ball_speed_mph, su, 1),
      unit: getSpeedUnit(su),
      raw: s.ball_speed_mph,
    }),
  },
  {
    id: 'clubSpeed', labelKey: 'clubSpeed', group: 'speed', defaultOn: true,
    render: (s, _, su) => {
      const v = s.club_speed_mph;
      return { value: v != null ? formatSpeed(v, su, 1) : '-', unit: v != null ? getSpeedUnit(su) : undefined, raw: v };
    },
  },
  {
    id: 'smash', labelKey: 'colSmash', group: 'speed', defaultOn: false,
    render: (s) => {
      const v = s.smash_factor;
      if (v == null) return { value: '-' };
      const ideal = s.club === 'driver' ? { min: 1.40, max: 1.50 } : { min: 1.28, max: 1.42 };
      return { value: v.toFixed(2), quality: inRange(v, ideal), raw: v };
    },
  },
  // ── Launch ────────────────────────────────────────────────────────────────
  {
    id: 'vLaunch', labelKey: 'vLaunch', group: 'launch', defaultOn: true,
    render: (s) => {
      const v = s.launch_angle_vertical;
      if (v == null) return { value: '-' };
      return { value: v.toFixed(1) + '°', quality: inRange(v, getRanges(s.club).vLaunch), raw: v };
    },
  },
  {
    id: 'hLaunch', labelKey: 'hLaunch', group: 'launch', defaultOn: false,
    render: (s) => {
      const v = s.launch_angle_horizontal;
      if (v == null) return { value: '-' };
      return {
        value: (v >= 0 ? '+' : '') + v.toFixed(1) + '°',
        quality: hLaunchQuality(v, getRanges(s.club).hLaunch),
        raw: v,
      };
    },
  },
  {
    id: 'aoa', labelKey: 'clubAoA', group: 'launch', defaultOn: false,
    render: (s) => {
      const v = s.club_angle_deg;
      if (v == null) return { value: '-' };
      return { value: (v >= 0 ? '+' : '') + v.toFixed(1) + '°', quality: inRange(v, getRanges(s.club).aoa), raw: v };
    },
  },
  // ── Club ──────────────────────────────────────────────────────────────────
  {
    id: 'clubPath', labelKey: 'clubPath', group: 'club', defaultOn: false,
    render: (s) => {
      const v = s.club_path_deg;
      if (v == null) return { value: '-' };
      return { value: (v >= 0 ? '+' : '') + v.toFixed(1) + '°', quality: inRange(v, { min: -3, max: 3 }), raw: v };
    },
  },
  {
    id: 'facePath', labelKey: 'colFacePath', group: 'club', defaultOn: false,
    render: (s) => {
      const v = s.face_to_path_deg ?? null;
      if (v == null) return { value: '-' };
      const q = inRange(Math.abs(v), { min: 0, max: 2 });
      return { value: (v >= 0 ? '+' : '') + v.toFixed(1) + '°', quality: q, raw: v };
    },
  },
  // ── Spin ──────────────────────────────────────────────────────────────────
  {
    id: 'spinRate', labelKey: 'spinRate', group: 'spin', defaultOn: true,
    render: (s) => {
      const v = s.spin_rpm;
      if (v == null) return { value: '-' };
      return {
        value: Math.round(v).toLocaleString('en-US'),
        unit: 'rpm',
        quality: inRange(v, getRanges(s.club).spin),
        raw: v,
      };
    },
  },
  {
    id: 'spinAxis', labelKey: 'spinAxis', group: 'spin', defaultOn: false,
    render: (s) => {
      const v = s.spin_axis_deg;
      if (v == null) return { value: '-' };
      const abs = Math.abs(v);
      const quality: Quality = abs <= 2 ? 'medium' : 'low';
      return { value: (v >= 0 ? '+' : '') + v.toFixed(1) + '°', quality, raw: v };
    },
  },
  {
    id: 'backSpin', labelKey: 'colBackSpin', group: 'spin', defaultOn: false,
    render: (s) => {
      if (s.spin_rpm == null || s.spin_axis_deg == null) return { value: '-' };
      const v = Math.round(s.spin_rpm * Math.cos(s.spin_axis_deg * Math.PI / 180));
      return { value: Math.abs(v).toLocaleString('en-US'), unit: 'rpm', raw: v };
    },
  },
  {
    id: 'sideSpin', labelKey: 'colSideSpin', group: 'spin', defaultOn: false,
    render: (s) => {
      if (s.spin_rpm == null || s.spin_axis_deg == null) return { value: '-' };
      const v = Math.round(s.spin_rpm * Math.sin(s.spin_axis_deg * Math.PI / 180));
      return { value: (v >= 0 ? '+' : '') + Math.abs(v).toLocaleString('en-US'), unit: 'rpm', raw: v };
    },
  },
  {
    id: 'shotShape', labelKey: 'colShotShape', group: 'spin', defaultOn: false,
    render: (s, _du, _su, t) => {
      const deg = s.spin_axis_deg;
      if (deg == null) return { value: '-' };
      let label: string;
      if (deg < -4)      label = t('strongDraw');
      else if (deg < -1) label = t('draw');
      else if (deg <= 1) label = t('straight');
      else if (deg <= 4) label = t('slightFade');
      else               label = t('strongFade');
      const abs = Math.abs(deg);
      const quality: Quality = abs <= 2 ? 'medium' : 'low';
      return { value: label, quality, raw: deg };
    },
  },
];

const DEFAULT_ON = new Set(COLS.filter((c) => c.defaultOn).map((c) => c.id));

const GROUPS: { id: ColGroup; labelKey: TKey }[] = [
  { id: 'distance', labelKey: 'grpDistance' },
  { id: 'speed',    labelKey: 'grpSpeed' },
  { id: 'launch',   labelKey: 'grpLaunch' },
  { id: 'club',     labelKey: 'grpClub' },
  { id: 'spin',     labelKey: 'grpSpin' },
];

// ── Quality color helpers ────────────────────────────────────────────────────

function qualityColor(q: Quality | null | undefined, pos: string, neg: string): string | undefined {
  if (!q || q === 'medium') return pos;
  return neg;
}

// ── Column Picker Panel ──────────────────────────────────────────────────────

interface ColPickerProps {
  open: boolean;
  onClose: () => void;
  enabled: Set<string>;
  onToggle: (id: string) => void;
  onReset: () => void;
}

function ColPicker({ open, onClose, enabled, onToggle, onReset }: ColPickerProps) {
  const { t } = useLanguage();

  return createPortal(
    <>
      {open && <div className="sl-picker-backdrop" onClick={onClose} aria-hidden="true" />}
      <div className={`sl-picker ${open ? 'sl-picker--open' : ''}`} role="dialog" aria-label={t('columnsBtn')} aria-modal="true">
        <div className="sl-picker__header">
          <span className="sl-picker__title">{t('columnsBtn')}</span>
          <div className="sl-picker__header-actions">
            <button className="sl-picker__reset" onClick={onReset}>{t('resetBtn')}</button>
            <button className="sl-picker__close" onClick={onClose} aria-label={t('doneBtn')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </div>

        <div className="sl-picker__body">
          {GROUPS.map((group) => {
            const groupCols = COLS.filter((c) => c.group === group.id);
            return (
              <div key={group.id}>
                <div className="sl-picker__section-label">{t(group.labelKey)}</div>
                {groupCols.map((col) => (
                  <label key={col.id} className="sl-picker__row">
                    <span className="sl-picker__col-name">{t(col.labelKey)}</span>
                    <button
                      role="switch"
                      aria-checked={enabled.has(col.id)}
                      className={`a11y-toggle${enabled.has(col.id) ? ' a11y-toggle--on' : ''}`}
                      onClick={() => onToggle(col.id)}
                      aria-label={t(col.labelKey)}
                    >
                      <span className="a11y-toggle__thumb" />
                    </button>
                  </label>
                ))}
              </div>
            );
          })}
        </div>

        <div className="sl-picker__footer">
          <button className="sl-picker__done" onClick={onClose}>{t('doneBtn')}</button>
        </div>
      </div>
    </>,
    document.body,
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface ShotListProps {
  shots: Shot[];
}

export function ShotList({ shots }: ShotListProps) {
  const [page, setPage] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [enabledCols, setEnabledCols] = useState<Set<string>>(() => new Set(DEFAULT_ON));
  const { speedUnit, distanceUnit } = useUnitPreference();
  const { t } = useLanguage();
  const theme = useThemeColors();

  const activeCols = useMemo(
    () => COLS.filter((c) => enabledCols.has(c.id)),
    [enabledCols],
  );

  const totalPages = Math.ceil(shots.length / SHOTS_PER_PAGE);

  const pageShots = useMemo(() => {
    const reversed = [...shots].reverse();
    const start = page * SHOTS_PER_PAGE;
    return reversed.slice(start, start + SHOTS_PER_PAGE);
  }, [shots, page]);

  const startIndex = page * SHOTS_PER_PAGE;

  const toggleCol = useCallback((id: string) => {
    setEnabledCols((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const resetCols = useCallback(() => setEnabledCols(new Set(DEFAULT_ON)), []);

  if (shots.length === 0) {
    return (
      <div className="shot-list shot-list--empty">
        <p>{t('noShots')}</p>
      </div>
    );
  }

  const posColor = theme.pos;
  const negColor = theme.neg;

  return (
    <div className="shot-list shot-list--table">
      {/* ── Toolbar ── */}
      <div className="sl-toolbar">
        <span className="sl-toolbar__count">
          {shots.length} {shots.length === 1 ? t('shotSingular') : t('shotCount')}
        </span>
        <button
          className="sl-col-btn"
          onClick={() => setPickerOpen((o) => !o)}
          aria-expanded={pickerOpen}
          aria-haspopup="dialog"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14" aria-hidden="true">
            <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {t('columnsBtn')}
          <span className="sl-col-btn__badge">{activeCols.length}</span>
        </button>
      </div>

      {/* ── Table ── */}
      <div className="sl-table-wrap">
        <table className="sl-table" aria-label={t('a11yShotList')}>
          <thead>
            <tr>
              <th className="sl-th sl-th--num" aria-label={t('a11yShotNumber')}>#</th>
              <th className="sl-th sl-th--club">{t('clubLabel')}</th>
              {activeCols.map((col) => (
                <th key={col.id} className="sl-th">{t(col.labelKey)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageShots.map((shot, rowIdx) => {
              const shotNumber = shots.length - startIndex - rowIdx;
              return (
                <tr key={shot.timestamp} className="sl-tr">
                  <td className="sl-td sl-td--num">#{shotNumber}</td>
                  <td className="sl-td sl-td--club">
                    <span className="sl-club-chip">{shot.club.toUpperCase()}</span>
                  </td>
                  {activeCols.map((col) => {
                    const cell = col.render(shot, distanceUnit, speedUnit, t);
                    const hasQuality = cell.quality != null && cell.value !== '-';
                    const color = hasQuality
                      ? qualityColor(cell.quality, posColor, negColor)
                      : undefined;
                    return (
                      <td key={col.id} className={`sl-td${hasQuality ? ` sl-td--${cell.quality}` : ''}`}>
                        <div className="sl-cell">
                          <span className="sl-cell__value" style={hasQuality && color ? { color } : undefined}>
                            {cell.value}
                          </span>
                          {cell.unit && cell.unit !== '°' && <span className="sl-cell__unit">{cell.unit}</span>}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="pagination" role="navigation" aria-label={t('a11yShotListPagination')}>
          <button
            className="pagination__button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label={t('prev')}
          >
            {t('prev')}
          </button>
          <span className="pagination__info" aria-live="polite" aria-atomic="true">
            {t('page')} {page + 1} / {totalPages}
          </span>
          <button
            className="pagination__button"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
            aria-label={t('next')}
          >
            {t('next')}
          </button>
        </div>
      )}

      {/* ── Column Picker Panel ── */}
      <ColPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        enabled={enabledCols}
        onToggle={toggleCol}
        onReset={resetCols}
      />
    </div>
  );
}
