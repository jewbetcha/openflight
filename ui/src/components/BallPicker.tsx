import { useEffect, useState } from 'react';
import { DEFAULT_BALLS, useBallStore } from '../stores/useBallStore';
import { useSystemStore } from '../stores/useSystemStore';
import { socketService } from '../services/socketService';
import './ClubPicker.css';

export function BallPicker() {
  const [isOpen, setIsOpen] = useState(false);
  const [newBall, setNewBall] = useState('');
  const { balls, customBalls, selectedBall, addBall, removeBall, selectBall } = useBallStore();
  const connected = useSystemStore((state) => state.connected);
  const serverBallName = useSystemStore((state) => state.serverBallName);

  useEffect(() => {
    if (connected) {
      socketService.setBall(selectedBall);
    }
  }, [connected, selectedBall]);

  useEffect(() => {
    if (serverBallName && serverBallName !== selectedBall) {
      selectBall(serverBallName);
    }
  }, [serverBallName, selectedBall, selectBall]);

  const handleSelect = (ballName: string) => {
    selectBall(ballName);
    socketService.setBall(ballName);
    setIsOpen(false);
  };

  const handleAdd = () => {
    const ballName = addBall(newBall);
    socketService.setBall(ballName);
    setNewBall('');
    setIsOpen(false);
  };

  const handleRemove = (ballName: string) => {
    removeBall(ballName);
    if (ballName === selectedBall) {
      socketService.setBall('Unknown Ball');
    }
  };

  return (
    <div className="club-picker club-picker--ball">
      <button className="club-picker__trigger" onClick={() => setIsOpen(!isOpen)} aria-expanded={isOpen}>
        <span className="club-picker__label">Ball</span>
        <span className="club-picker__value club-picker__value--ball">{selectedBall}</span>
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
          <div className="club-picker__overlay" onClick={() => setIsOpen(false)} />
          <div className="club-picker__dropdown club-picker__dropdown--ball">
            <div className="club-picker__section">
              <span className="club-picker__section-title">Golf Ball</span>
              <div className="club-picker__ball-list">
                {balls.map((ballName) => {
                  const removable = customBalls.includes(ballName) && !DEFAULT_BALLS.includes(ballName);
                  return (
                    <div className="club-picker__ball-row" key={ballName}>
                      <button
                        className={`club-picker__option club-picker__option--ball ${
                          selectedBall === ballName ? 'club-picker__option--selected' : ''
                        }`}
                        onClick={() => handleSelect(ballName)}
                      >
                        {ballName}
                      </button>
                      {removable && (
                        <button
                          className="club-picker__remove"
                          type="button"
                          aria-label={`Remove ${ballName}`}
                          title="Remove"
                          onClick={() => handleRemove(ballName)}
                        >
                          X
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="club-picker__add-row">
              <input
                className="club-picker__input"
                type="text"
                placeholder="Add ball"
                value={newBall}
                maxLength={64}
                onChange={(event) => setNewBall(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    handleAdd();
                  }
                }}
              />
              <button className="club-picker__add" type="button" onClick={handleAdd}>
                Add
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
