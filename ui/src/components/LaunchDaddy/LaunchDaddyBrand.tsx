import { useLaunchDaddy } from './useLaunchDaddy';

export function LaunchDaddyBrand() {
  const { isLaunchDaddyMode, toggleLaunchDaddy } = useLaunchDaddy();

  if (!isLaunchDaddyMode) return null;

  return (
    <div className="launch-daddy-brand" onClick={toggleLaunchDaddy}>
      <span className="launch-daddy-brand__icon">🔥</span>
      <span className="launch-daddy-brand__text">Launch Daddy</span>
    </div>
  );
}

export function LaunchDaddySecretIndicator() {
  const { secretTapCount, isLaunchDaddyMode } = useLaunchDaddy();

  // Don't show if already in Launch Daddy mode or no taps yet
  if (isLaunchDaddyMode || secretTapCount === 0) return null;

  return (
    <div className="launch-daddy-secret-indicator">
      {[1, 2, 3, 4, 5].map((num) => (
        <div
          key={num}
          className={`launch-daddy-secret-dot ${num <= secretTapCount ? 'launch-daddy-secret-dot--active' : ''}`}
        />
      ))}
    </div>
  );
}
