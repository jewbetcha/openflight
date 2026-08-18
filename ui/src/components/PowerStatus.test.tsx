import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { PowerStatus } from '../types/power';
import { PowerIndicator, PowerWarning } from './PowerStatus';

const status = (overrides: Partial<PowerStatus> = {}): PowerStatus => ({
  available: true,
  provider: 'geekworm',
  state: 'on_battery',
  battery_percent: 42.4,
  battery_voltage_v: 3.72,
  external_power: false,
  updated_at: '2026-08-15T12:00:00+00:00',
  error: null,
  ...overrides,
});

describe('PowerIndicator', () => {
  it('shows plugged-in state and rounded battery percentage', () => {
    const html = renderToString(
      <PowerIndicator status={status({ state: 'plugged_in', external_power: true, battery_percent: 81.6 })} />
    );

    expect(html).toContain('Plugged in, 82% battery');
    expect(html).toContain('power-status--plugged_in');
    expect(html).toContain('power-status__bolt');
  });

  it('shows an explicit unavailable state without inventing a percentage', () => {
    const html = renderToString(
      <PowerIndicator
        status={status({
          available: false,
          state: 'unavailable',
          battery_percent: null,
          battery_voltage_v: null,
          external_power: null,
          error: 'I2C device 0x36 missing',
        })}
      />
    );

    expect(html).toContain('Battery status unavailable');
    expect(html).toContain('I2C device 0x36 missing');
    expect(html).toContain('--');
  });
});

describe('PowerWarning', () => {
  it('renders a dismissible 20 percent warning', () => {
    const html = renderToString(<PowerWarning level="low" percentage={20} />);

    expect(html).toContain('Battery low');
    expect(html).toContain('20%');
    expect(html).toContain('>Dismiss</button>');
    expect(html).toContain('role="alertdialog"');
  });

  it('uses stronger language for the 10 percent warning', () => {
    const html = renderToString(<PowerWarning level="critical" percentage={10} />);

    expect(html).toContain('Battery critically low');
    expect(html).toContain('external power now');
  });
});
