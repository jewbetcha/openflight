import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ALL_CLUBS } from '../data/clubs';
import { LanguageProvider } from '../state/LanguageProvider';
import { ClubSelectScreen } from './ClubSelectScreen';

const noop = () => {};

/** ClubSelectScreen calls useLanguage(), so it must render inside LanguageProvider. */
function render(selectedClub: string) {
  return renderToString(
    <LanguageProvider>
      <ClubSelectScreen selectedClub={selectedClub} onSelect={noop} onSkip={noop} />
    </LanguageProvider>,
  );
}

describe('ClubSelectScreen', () => {
  it('renders every club option', () => {
    const html = render('driver');
    for (const club of ALL_CLUBS) {
      expect(html).toContain(`>${club.label}</button>`);
    }
  });

  it('renders the category headings', () => {
    const html = render('driver');
    expect(html).toContain('Irons');
    expect(html).toContain('Hybrids');
    expect(html).toContain('Woods');
  });

  it('marks the current club for assistive tech, with no visual pre-highlight', () => {
    const html = render('7-iron');
    // no gold pre-highlight on load
    expect(html).not.toContain('club-select__option--selected');
    // current club still conveyed to screen readers via aria-pressed
    expect(html).toMatch(/aria-pressed="true"[^>]*>7i</);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
  });

  it('renders a close (dismiss) button instead of a skip button', () => {
    const html = render('driver');
    expect(html).toContain('aria-label="Close club selection"');
    expect(html).not.toContain('Skip');
  });
});
