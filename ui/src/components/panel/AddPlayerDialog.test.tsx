import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AddPlayerDialog } from './AddPlayerDialog';

describe('AddPlayerDialog', () => {
  it('is a modal with an app-styled name field and Add player action', () => {
    const html = renderToString(<AddPlayerDialog name="" onChange={() => {}} onAdd={() => {}} onCancel={() => {}} />);

    expect(html).toContain('add-player-modal');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('aria-label="Add player"');
    expect(html).toContain('add-player-modal__input');
    expect(html).toContain('placeholder="Name"');
    expect(html).toContain('>Add player<');
    expect(html).toContain('>Cancel<');
    expect(html).not.toContain('shutdown-dialog');
  });

  it('disables Add player until a name is entered', () => {
    const empty = renderToString(
      <AddPlayerDialog name="   " onChange={() => {}} onAdd={() => {}} onCancel={() => {}} />
    );
    const filled = renderToString(
      <AddPlayerDialog name="Alex" onChange={() => {}} onAdd={() => {}} onCancel={() => {}} />
    );

    expect(empty).toMatch(/disabled[^>]*>Add player</);
    expect(filled).not.toMatch(/disabled[^>]*>Add player</);
  });
});
