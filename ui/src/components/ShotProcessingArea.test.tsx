import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ShotProcessingArea } from './ShotProcessingArea';

describe('ShotProcessingArea', () => {
  it('keeps current metrics rendered while calculation status is visible', () => {
    const html = renderToString(
      <ShotProcessingArea phase="calculating">
        <div className="current-shot-metrics">145.2 mph · 258 yds</div>
      </ShotProcessingArea>
    );

    expect(html).toContain('Shot captured');
    expect(html).toContain('Calculating metrics…');
    expect(html).toContain('shot-processing-overlay');
    expect(html).toContain('progress-indicator--dialog');
    expect(html).toContain('current-shot-metrics');
    expect(html).toContain('145.2 mph · 258 yds');
  });

  it('reports capture activity before metric calculation starts', () => {
    const html = renderToString(
      <ShotProcessingArea phase="capturing">
        <div>Previous metrics</div>
      </ShotProcessingArea>
    );

    expect(html).toContain('Impact detected');
    expect(html).toContain('Capturing radar data…');
    expect(html).toContain('Previous metrics');
  });
});
