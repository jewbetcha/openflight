import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ConfidenceDots } from './ConfidenceDots';

const labels = { low: 'Left', medium: 'Perfect', high: 'Right' };

describe('ConfidenceDots', () => {
  it('renders the resolved label for the quality', () => {
    const html = renderToString(<ConfidenceDots quality="medium" labels={labels} scope="card" />);
    expect(html).toContain('Perfect');
    expect(html).toContain('metric-card__confidence--medium');
  });

  it('uses the display class set for the display scope', () => {
    const html = renderToString(<ConfidenceDots quality="high" labels={labels} scope="display" />);
    expect(html).toContain('display-metric__confidence--high');
    expect(html).toContain('Right');
  });

  it('fills the dot pattern: perfect=●●● (three filled)', () => {
    const html = renderToString(<ConfidenceDots quality="medium" labels={labels} scope="card" />);
    expect((html.match(/dot filled/g) ?? []).length).toBe(3);
  });

  it('fills the dot pattern: low=●○○ (one filled)', () => {
    const html = renderToString(<ConfidenceDots quality="low" labels={labels} scope="card" />);
    expect((html.match(/dot filled/g) ?? []).length).toBe(1);
  });
});
