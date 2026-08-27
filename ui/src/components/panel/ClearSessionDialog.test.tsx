import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ClearSessionDialog } from './ClearSessionDialog';

const noop = () => {};

describe('ClearSessionDialog', () => {
  it('asks before clearing and names the player', () => {
    const html = renderToString(<ClearSessionDialog playerName="Alex" onConfirm={noop} onCancel={noop} />);

    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('id="clear-session-title"');
    expect(html).toContain('Clear Alex&#x27;s session?');
    expect(html).toContain('This removes Alex&#x27;s shots. Other players are kept.');
    expect(html).toContain('>Clear session<');
    expect(html).toContain('>Cancel<');
    expect(html).toContain('add-player-modal');
    expect(html).toContain('panel-action--danger');
  });

  it('keeps the confirm control as Clear session, matching the header action', () => {
    const html = renderToString(<ClearSessionDialog playerName="Player 1" onConfirm={noop} onCancel={noop} />);

    expect(html).toContain('Clear Player 1&#x27;s session?');
    expect(html).toMatch(/panel-action--danger[^>]*>Clear session</);
  });
});
