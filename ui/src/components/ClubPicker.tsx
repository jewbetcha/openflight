import { useState } from 'react';
import './ClubPicker.css';

const CLUBS_BY_TYPE = {
  Irons: [
    { id: '2-iron', label: '2i' },
    { id: '3-iron', label: '3i' },
    { id: '4-iron', label: '4i' },
    { id: '5-iron', label: '5i' },
    { id: '6-iron', label: '6i' },
    { id: '7-iron', label: '7i' },
    { id: '8-iron', label: '8i' },
    { id: '9-iron', label: '9i' },
    { id: 'pw', label: 'PW' },
    { id: 'gw', label: 'GW' },
    { id: 'sw', label: 'SW' },
    { id: 'lw', label: 'LW' },
  ],
  Hybrids: [
    { id: '3-hybrid', label: '3H' },
    { id: '5-hybrid', label: '5H' },
    { id: '7-hybrid', label: '7H' },
    { id: '9-hybrid', label: '9H' },
  ],
  Woods: [
    { id: 'driver', label: 'DR' },
    { id: '3-wood', label: '3W' },
    { id: '5-wood', label: '5W' },
    { id: '7-wood', label: '7W' },
  ],
};
const ALL_CLUBS = Object.values(CLUBS_BY_TYPE).flat();

interface ClubPickerProps {
  selectedClub: string;
  onClubChange: (club: string) => void;
}

export function ClubPicker({ selectedClub, onClubChange }: ClubPickerProps) {
  const [isOpen, setIsOpen] = useState(false);

  const selectedLabel =
    ALL_CLUBS.find(c => c.id === selectedClub)?.label || 'DR';

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
      >
        <span className="club-picker__label">Club</span>
        <span className="club-picker__value">{selectedLabel}</span>
        <svg
          className={`club-picker__arrow ${
            isOpen ? 'club-picker__arrow--open' : ''
          }`}
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
          <div
            className="club-picker__overlay"
            onClick={() => setIsOpen(false)}
          />
          <div className="club-picker__dropdown">
            {Object.entries(CLUBS_BY_TYPE).map(([type, clubs]) => (
              <div className="club-picker__section">
                <span className="club-picker__section-title">{type}</span>
                <div className="club-picker__grid">
                  {clubs.map(club => (
                    <button
                      key={club.id}
                      className={`club-picker__option ${
                        selectedClub === club.id
                          ? 'club-picker__option--selected'
                          : ''
                      }`}
                      onClick={() => handleSelect(club.id)}
                    >
                      {club.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
