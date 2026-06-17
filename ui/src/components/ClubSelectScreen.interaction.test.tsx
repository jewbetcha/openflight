import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ALL_CLUBS } from '../data/clubs';
import { LanguageProvider } from '../state/LanguageProvider';
import { ClubSelectScreen } from './ClubSelectScreen';

/**
 * Behaviour tests - exercise real clicks against a jsdom DOM (React Testing
 * Library + user-event). This is what renderToString markup tests could not do.
 * Doubles as the smoke test proving the jsdom test environment is wired up.
 */
function renderScreen(overrides: Partial<{ onSelect: (c: string) => void; onSkip: () => void }> = {}) {
  return render(
    <LanguageProvider>
      <ClubSelectScreen
        selectedClub="driver"
        onSelect={overrides.onSelect ?? (() => {})}
        onSkip={overrides.onSkip ?? (() => {})}
      />
    </LanguageProvider>,
  );
}

const labelFor = (id: string) => ALL_CLUBS.find((c) => c.id === id)!.label;

describe('ClubSelectScreen interaction', () => {
  it('calls onSelect with the club id when a club is tapped', async () => {
    const onSelect = vi.fn();
    renderScreen({ onSelect });

    await userEvent.click(screen.getByRole('button', { name: labelFor('7-iron') }));

    expect(onSelect).toHaveBeenCalledWith('7-iron');
  });

  it('marks the current club as pressed for assistive tech', () => {
    renderScreen();

    const driverButton = screen.getByRole('button', { name: labelFor('driver') });
    expect(driverButton).toBeInTheDocument();
    expect(driverButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('calls onSkip when the close button is tapped', async () => {
    const onSkip = vi.fn();
    renderScreen({ onSkip });

    await userEvent.click(screen.getByRole('button', { name: 'Close club selection' }));

    expect(onSkip).toHaveBeenCalledTimes(1);
  });
});
