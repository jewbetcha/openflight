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

  it('marks the selected club with the selected modifier class', () => {
    const html = render('7-iron');
    // The 7-iron button carries the selected modifier...
    expect(html).toMatch(/club-select__option club-select__option--selected[^>]*>7i</);
    // ...and exactly one option is selected.
    expect(html.match(/club-select__option--selected/g)).toHaveLength(1);
  });

  it('renders a close (dismiss) button instead of a skip button', () => {
    const html = render('driver');
    expect(html).toContain('aria-label="Close club selection"');
    expect(html).not.toContain('Skip');
  });
});
