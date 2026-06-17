import { createPortal } from 'react-dom';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { A11yPrefs } from '../state/useAccessibilitySettings';
import { useUnitPreference } from '../state/useUnitPreference';
import { useLanguage } from '../state/useLanguage';
import type { LangCode } from '../i18n/translations';
import { UNIT_COMBOS } from '../utils/units';
import { useViewMode } from '../state/useViewMode';
import { PairingQR } from './PairingQR';
import './SettingsPanel.css';

/** A single labelled on/off switch row, shared by every settings toggle. */
export function A11yToggleRow({
  label,
  sub,
  checked,
  onToggle,
  last = false,
}: {
  label: string;
  sub: string;
  checked: boolean;
  onToggle: (next: boolean) => void;
  last?: boolean;
}) {
  return (
    <label className={`a11y-panel__row${last ? ' a11y-panel__row--last' : ''}`}>
      <div className="a11y-panel__row-text">
        <span className="a11y-panel__row-label">{label}</span>
        <span className="a11y-panel__row-sub">{sub}</span>
      </div>
      <button
        role="switch"
        aria-checked={checked}
        className={`a11y-toggle ${checked ? 'a11y-toggle--on' : ''}`}
        onClick={() => onToggle(!checked)}
        aria-label={label}
      >
        <span className="a11y-toggle__thumb" />
      </button>
    </label>
  );
}

const LANGUAGES: { code: LangCode; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Português' },
  { code: 'it', label: 'Italiano' },
  { code: 'nl', label: 'Nederlands' },
  { code: 'sv', label: 'Svenska' },
  { code: 'no', label: 'Norsk' },
  { code: 'da', label: 'Dansk' },
  { code: 'fi', label: 'Suomi' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'th', label: 'ภาษาไทย' },
  { code: 'zh-hans', label: '中文简体' },
  { code: 'zh-hant', label: '中文繁體' },
];

interface Props {
  open: boolean;
  onClose: () => void;
  prefs: A11yPrefs;
  onToggle: (key: keyof A11yPrefs, value: boolean) => void;
  /**
   * Optional surface-specific sections rendered just before the pairing block.
   * The kiosk/TV shell injects its tab-visibility toggles here (see
   * KioskSettingsPanel); the passive /display view passes nothing.
   */
  extraSections?: ReactNode;
}

export function SettingsPanel({ open, onClose, prefs, onToggle, extraSections }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const { speedUnit, distanceUnit, setUnitCombo } = useUnitPreference();
  const { language, setLanguage, t } = useLanguage();
  const { isInteractive, setMode } = useViewMode();

  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const langBtnRef = useRef<HTMLButtonElement>(null);
  const [langBtnRect, setLangBtnRect] = useState<DOMRect | null>(null);

  const openLangDropdown = () => {
    if (langBtnRef.current) setLangBtnRect(langBtnRef.current.getBoundingClientRect());
    setLangDropdownOpen(true);
  };

  const selectLang = (code: LangCode) => {
    setLanguage(code);
    setLangDropdownOpen(false);
  };

  useEffect(() => {
    if (!langDropdownOpen) return;
    const close = () => setLangDropdownOpen(false);
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [langDropdownOpen]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const selectedLang = LANGUAGES.find((l) => l.code === language);

  return (
    <>
      {/* aria-modal + inert are gated on `open`: when closed the panel stays in
          the DOM (opacity:0), so without this the spatial-nav focus trap would
          scope the whole D-pad into the invisible panel. inert also removes its
          controls from the Tab order when closed. */}
      <div
        ref={panelRef}
        className={`a11y-panel ${open ? 'a11y-panel--open' : ''}`}
        role="dialog"
        aria-label={t('settingsTitle')}
        aria-modal={open ? true : undefined}
        inert={!open}
      >
        <div className="a11y-panel__header">
          <span className="a11y-panel__title">{t('settingsTitle')}</span>
          <button className="a11y-panel__close" onClick={onClose} aria-label={t('a11yCloseSettings')} data-modal-dismiss>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
              <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="a11y-panel__section-label">{t('unitsSection')}</div>
        <div className="a11y-panel__row a11y-panel__row--last a11y-panel__row--col">
          <div className="a11y-panel__row-text">
            <span className="a11y-panel__row-label">{t('unitsLabel')}</span>
            <span className="a11y-panel__row-sub">{t('unitsSub')}</span>
          </div>
          <div className="a11y-combo-grid" role="group" aria-label={t('unitsLabel')}>
            {UNIT_COMBOS.map((combo) => {
              const active = combo.speed === speedUnit && combo.distance === distanceUnit;
              return (
                <button
                  key={combo.label}
                  type="button"
                  className={`a11y-combo-btn ${active ? 'a11y-combo-btn--active' : ''}`}
                  onClick={() => setUnitCombo(combo.speed, combo.distance)}
                  aria-pressed={active}
                >
                  {combo.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="a11y-panel__section-label">{t('langSection')}</div>
        <div className="a11y-panel__row a11y-panel__row--last">
          <div className="a11y-panel__row-text">
            <span className="a11y-panel__row-label">{t('langLabel')}</span>
            <span className="a11y-panel__row-sub">{t('langSub')}</span>
          </div>
          <button
            ref={langBtnRef}
            className="a11y-lang-btn"
            onClick={openLangDropdown}
            aria-haspopup="listbox"
            aria-expanded={langDropdownOpen}
            aria-label={t('langLabel')}
          >
            {selectedLang?.label}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="12" height="12" aria-hidden="true">
              <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        <div className="a11y-panel__section-label">{t('motionSection')}</div>
        <A11yToggleRow
          label={t('reduceMotion')}
          sub={t('reduceMotionSub')}
          checked={prefs.reduceMotion}
          onToggle={(v) => onToggle('reduceMotion', v)}
        />

        <div className="a11y-panel__section-label">{t('displaySection')}</div>
        <A11yToggleRow
          label={t('highContrast')}
          sub={t('highContrastSub')}
          checked={prefs.highContrast}
          onToggle={(v) => onToggle('highContrast', v)}
        />
        <A11yToggleRow
          label={t('largerText')}
          sub={t('largerTextSub')}
          checked={prefs.largeText}
          onToggle={(v) => onToggle('largeText', v)}
          last
        />

        <div className="a11y-panel__section-label">{t('accessibilitySection')}</div>
        <A11yToggleRow
          label={t('colorBlindMode')}
          sub={t('colorBlindModeSub')}
          checked={prefs.colorBlind}
          onToggle={(v) => onToggle('colorBlind', v)}
          last
        />

        <div className="a11y-panel__section-label">{t('viewModeSection')}</div>
        <A11yToggleRow
          label={t('interactiveModeLabel')}
          sub={t('interactiveModeSub')}
          checked={isInteractive}
          onToggle={(v) => setMode(v ? 'interactive' : 'scoreboard')}
          last
        />

        {extraSections}

        <div className="a11y-panel__section-label">{t('pairSection')}</div>
        <div className="a11y-panel__pair">
          <PairingQR />
        </div>

        <p className="a11y-panel__footer">{t('settingsFooter')}</p>
      </div>

      {langDropdownOpen && langBtnRect && createPortal(
        <ul
          className="a11y-lang-dropdown"
          role="listbox"
          aria-label={t('langLabel')}
          style={{
            top: langBtnRect.bottom + 6,
            right: window.innerWidth - langBtnRect.right,
          }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {LANGUAGES.map((lang) => (
            <li
              key={lang.code}
              role="option"
              aria-selected={lang.code === language}
              className={`a11y-lang-option ${lang.code === language ? 'a11y-lang-option--selected' : ''}`}
              onClick={() => selectLang(lang.code)}
            >
              {lang.label}
            </li>
          ))}
        </ul>,
        document.body
      )}
    </>
  );
}

interface TriggerProps {
  open: boolean;
  onClick: () => void;
}

export function SettingsTrigger({ open, onClick }: TriggerProps) {
  const { t } = useLanguage();
  return (
    <button
      className={`a11y-trigger ${open ? 'a11y-trigger--active' : ''}`}
      onClick={onClick}
      aria-label={t('settingsTitle')}
      aria-expanded={open}
      aria-haspopup="dialog"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18" aria-hidden="true" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    </button>
  );
}
