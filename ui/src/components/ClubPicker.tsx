import { useState } from 'react';
import { ALL_CLUBS, CLUBS_BY_TYPE } from '../data/clubs';
import { useLanguage } from '../state/useLanguage';
import type { TKey } from '../i18n/translations';
import './ClubPicker.css';

const SECTION_KEYS: Record<string, TKey> = {
  Irons: 'clubSectionIrons',
  Hybrids: 'clubSectionHybrids',
  Woods: 'clubSectionWoods',
};

interface ClubPickerProps {
  selectedClub: string;
  onClubChange: (club: string) => void;
}

export function ClubPicker({ selectedClub, onClubChange }: ClubPickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { t } = useLanguage();

  const selectedLabel = ALL_CLUBS.find((c) => c.id === selectedClub)?.label || 'DR';

  const handleSelect = (clubId: string) => {
    onClubChange(clubId);
    setIsOpen(false);
  };

  return (
    <div className="club-picker">
      <button
        className="club-picker__trigger"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label={`Club: ${selectedLabel}. Press to change.`}
      >
        <span className="club-picker__label" aria-hidden="true">{t('clubLabel')}</span>
        <span className="club-picker__value" aria-hidden="true">{selectedLabel}</span>
        <svg
          className={`club-picker__arrow ${isOpen ? 'club-picker__arrow--open' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {isOpen && (
        <>
          <div className="club-picker__overlay" onClick={() => setIsOpen(false)} aria-hidden="true" />
          <div
            className="club-picker__dropdown"
            role="listbox"
            aria-label={t('a11ySelectClub')}
            aria-activedescendant={`club-option-${selectedClub}`}
          >
            {Object.entries(CLUBS_BY_TYPE).map(([type, clubs]) => {
              const sectionLabel = t(SECTION_KEYS[type] ?? 'clubSectionIrons');
              return (
                <div className="club-picker__section" key={type}>
                  <span className="club-picker__section-title" aria-hidden="true">{sectionLabel}</span>
                  <div className="club-picker__grid" role="group" aria-label={sectionLabel}>
                    {clubs.map((club) => (
                      <button
                        key={club.id}
                        id={`club-option-${club.id}`}
                        role="option"
                        aria-selected={selectedClub === club.id}
                        className={`club-picker__option ${
                          selectedClub === club.id ? 'club-picker__option--selected' : ''
                        }`}
                        onClick={() => handleSelect(club.id)}
                      >
                        {club.label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
