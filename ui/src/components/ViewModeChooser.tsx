import { useEffect, useRef, useState } from 'react';
import { suggestedViewMode } from '../state/displayDetect';
import { useViewMode } from '../state/useViewMode';
import { useLanguage } from '../state/useLanguage';
import './ViewModeChooser.css';

/** Crafted line/fill icons (gold, via currentColor) - no emoji. */
function ControlsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
      <line x1="3.5" y1="8" x2="20.5" y2="8" />
      <circle cx="9" cy="8" r="2.6" fill="var(--color-bg-card)" />
      <line x1="3.5" y1="16" x2="20.5" y2="16" />
      <circle cx="15" cy="16" r="2.6" fill="var(--color-bg-card)" />
    </svg>
  );
}

function BarsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="3.5" y="13" width="4.2" height="7" rx="1.3" opacity="0.55" />
      <rect x="9.9" y="8.5" width="4.2" height="11.5" rx="1.3" opacity="0.8" />
      <rect x="16.3" y="4.5" width="4.2" height="15.5" rx="1.3" />
    </svg>
  );
}

/**
 * First-run view-mode chooser (Interactive vs Scoreboard). Shown once on larger
 * screens when no mode is saved (the small kiosk panel defaults to Interactive
 * and never sees this). The pick is persisted and applied live. The Pi's
 * EDID/CEC auto-detection pre-highlights the likely option ("Detected").
 * Switchable later in Settings.
 *
 * It renders before a mode is chosen, so it carries its own arrow-key handler
 * and focus ring rather than relying on the `.tv` machinery - operable by a
 * D-pad-only remote regardless of the suggestion.
 */
export function ViewModeChooser() {
  const { setMode } = useViewMode();
  const { t } = useLanguage();
  const [suggested] = useState(suggestedViewMode);
  const interactiveRef = useRef<HTMLButtonElement>(null);
  const scoreboardRef = useRef<HTMLButtonElement>(null);

  // One label per option so VoiceOver reads a single clean stop
  // (label, then hint, then the recommendation) instead of stitching fragments.
  const label = (name: string, hint: string, recommended: boolean) =>
    recommended ? `${name}, ${hint}, ${t('vmRecommended')}` : `${name}, ${hint}`;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        interactiveRef.current?.focus();
        e.preventDefault();
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        scoreboardRef.current?.focus();
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <main className="mode-chooser" role="dialog" aria-modal="true" aria-label={t('vmChooserAria')}>
      <div className="mode-chooser__head">
        <img className="mode-chooser__logo" src="/openflighttransparentlogo.png" alt="OpenFlight" />
        <h1 className="mode-chooser__title">{t('vmChooserTitle')}</h1>
        <p className="mode-chooser__sub">{t('vmChooserSub')}</p>
      </div>

      <div className="mode-chooser__options" role="group" aria-label={t('vmChooserAria')}>
        <button
          ref={interactiveRef}
          type="button"
          className={`mode-chooser__opt${suggested === 'interactive' ? ' mode-chooser__opt--suggested' : ''}`}
          onClick={() => setMode('interactive')}
          autoFocus={suggested === 'interactive'}
          aria-label={label(t('vmInteractive'), t('vmInteractiveHint'), suggested === 'interactive')}
        >
          <span className="mode-chooser__medallion" aria-hidden="true">
            <ControlsIcon />
          </span>
          <span className="mode-chooser__label">{t('vmInteractive')}</span>
          <span className="mode-chooser__hint">{t('vmInteractiveHint')}</span>
          {suggested === 'interactive' && (
            <span className="mode-chooser__badge" aria-hidden="true">
              <span className="mode-chooser__badge-dot" />
              {t('vmDetected')}
            </span>
          )}
        </button>

        <button
          ref={scoreboardRef}
          type="button"
          className={`mode-chooser__opt${suggested === 'scoreboard' ? ' mode-chooser__opt--suggested' : ''}`}
          onClick={() => setMode('scoreboard')}
          autoFocus={suggested === 'scoreboard'}
          aria-label={label(t('vmScoreboard'), t('vmScoreboardHint'), suggested === 'scoreboard')}
        >
          <span className="mode-chooser__medallion" aria-hidden="true">
            <BarsIcon />
          </span>
          <span className="mode-chooser__label">{t('vmScoreboard')}</span>
          <span className="mode-chooser__hint">{t('vmScoreboardHint')}</span>
          {suggested === 'scoreboard' && (
            <span className="mode-chooser__badge" aria-hidden="true">
              <span className="mode-chooser__badge-dot" />
              {t('vmDetected')}
            </span>
          )}
        </button>
      </div>
    </main>
  );
}
