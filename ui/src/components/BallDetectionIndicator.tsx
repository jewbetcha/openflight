import './BallDetectionIndicator.css';

interface BallDetectionIndicatorProps {
  available: boolean;
  enabled: boolean;
  detected: boolean;
  confidence: number;
  onToggle: () => void;
}

export function BallDetectionIndicator({
  available,
  enabled,
  detected,
  confidence,
  onToggle,
}: BallDetectionIndicatorProps) {
  if (!available) {
    return null;
  }

  const getStatusClass = () => {
    if (!enabled) return 'ball-indicator--disabled';
    if (detected) return 'ball-indicator--detected';
    return 'ball-indicator--searching';
  };

  const getStatusText = () => {
    if (!enabled) return 'Camera Off';
    if (detected) return `Ball ${Math.round(confidence * 100)}%`;
    return 'No Ball';
  };

  return (
    <button
      className={`ball-indicator ${getStatusClass()}`}
      onClick={onToggle}
      title={enabled ? 'Click to disable camera' : 'Click to enable camera'}
    >
      <span className="ball-indicator__icon">{detected ? '⚪' : '◯'}</span>
      <span className="ball-indicator__text">{getStatusText()}</span>
    </button>
  );
}
