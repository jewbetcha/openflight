import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SpeedGauge } from './SpeedGauge';

function render(speedMph: number, gaugeMax: number) {
  return renderToString(
    <SpeedGauge speedMph={speedMph} gaugeMax={gaugeMax} label="Ball Speed" displayValue="--" unit="mph" />,
  );
}

describe('SpeedGauge', () => {
  it('renders a finite arc path for normal input', () => {
    const html = render(150, 220);
    expect(html).not.toContain('NaN');
    expect(html).toContain('aria-valuenow="150"');
  });

  it('never emits NaN in the arc path for non-finite speed', () => {
    const html = render(Number.NaN, 220);
    expect(html).not.toContain('NaN');
  });

  it('never emits NaN for a degenerate range (gaugeMax === min)', () => {
    const html = render(40, 35);
    expect(html).not.toContain('NaN');
  });

  it('clamps aria-valuenow to the minimum when speed is non-finite', () => {
    const html = render(Number.POSITIVE_INFINITY, 220);
    expect(html).toContain('aria-valuenow="35"');
  });
});
