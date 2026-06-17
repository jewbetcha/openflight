import { CLUBS_BY_TYPE } from '../data/clubs';
import { useLanguage } from '../state/useLanguage';
import type { TKey } from '../i18n/translations';
import './ClubSelectScreen.css';

interface ClubSelectScreenProps {
  /** Currently selected club id; pre-highlighted on the grid. */
  selectedClub: string;
  /** Called with the chosen club id when the user picks a club. */
  onSelect: (club: string) => void;
  /** Called when the user dismisses (X) without changing the current club. */
  onSkip: () => void;
}

const SECTION_KEYS: Record<string, TKey> = {
  Irons: 'clubSectionIrons',
  Hybrids: 'clubSectionHybrids',
  Woods: 'clubSectionWoods',
};

/**
 * Full-screen interstitial shown on app load so the user confirms which club
 * they're hitting before the first shot. Dismissible via the X in the corner,
 * which keeps the current (default) club.
 */
export function ClubSelectScreen({ selectedClub, onSelect, onSkip }: ClubSelectScreenProps) {
  const { t } = useLanguage();
  return (
    <div className="club-select" role="dialog" aria-modal="true" aria-label={t('selectClubTitle')}>
      <div className="club-select__panel">
        <button type="button" className="club-select__close" onClick={onSkip} aria-label={t('a11yCloseClubSelect')}>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        <h1 className="club-select__title">{t('selectClubTitle')}</h1>
        <p className="club-select__subtitle">{t('selectClubSubtitle')}</p>

        {Object.entries(CLUBS_BY_TYPE).map(([type, clubs]) => (
          <div className="club-select__section" key={type}>
            <span className="club-select__section-title">{t(SECTION_KEYS[type] ?? 'clubSectionIrons')}</span>
            <div className="club-select__grid">
              {clubs.map((club) => (
                <button
                  type="button"
                  key={club.id}
                  className="club-select__option"
                  onClick={() => onSelect(club.id)}
                  aria-pressed={selectedClub === club.id}
                  // Land remote focus on the current club so the D-pad enters the
                  // grid immediately (Apple HIG: meaningful initial focus on entry).
                  autoFocus={selectedClub === club.id}
                >
                  {club.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
