import type { Quality } from '../utils/shotQuality';
import type { QualityLabels } from '../utils/shotMetrics';

/**
 * Shared three-dot confidence indicator used by both the kiosk live view
 * (MetricCard) and the passive /display scoreboard (DisplayTile). The dot
 * pattern is the single source of truth: low=●○○  perfect=●●●  high=○○●.
 *
 * The two surfaces keep their own CSS namespaces (different sizing), so `scope`
 * selects the class set - this dedups the LOGIC without forcing a CSS merge.
 */
type Scope = 'card' | 'display';

const CLASSES: Record<Scope, { wrap: string; dots: string; dot: string; filled: string; label: string }> = {
  card: {
    wrap: 'metric-card__confidence',
    dots: 'metric-card__confidence-dots',
    dot: 'dot',
    filled: 'filled',
    label: 'metric-card__confidence-label',
  },
  display: {
    wrap: 'display-metric__confidence',
    dots: 'display-metric__dots',
    dot: 'display-metric__dot',
    filled: 'is-filled',
    label: 'display-metric__confidence-label',
  },
};

export function ConfidenceDots({
  quality,
  labels,
  scope,
}: {
  quality: Quality;
  labels: QualityLabels;
  scope: Scope;
}) {
  const c = CLASSES[scope];
  // low=●○○  perfect=●●●  high=○○●
  const filled = [quality !== 'high', quality === 'medium', quality !== 'low'];
  return (
    <div className={`${c.wrap} ${c.wrap}--${quality}`}>
      <span className={c.dots} aria-hidden="true">
        {filled.map((on, i) => (
          <span key={i} className={on ? `${c.dot} ${c.filled}` : c.dot} />
        ))}
      </span>
      <span className={c.label}>{labels[quality]}</span>
    </div>
  );
}
