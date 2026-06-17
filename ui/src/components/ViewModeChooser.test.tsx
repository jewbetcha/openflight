import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ViewModeChooser } from './ViewModeChooser';
import { ViewModeProvider } from '../state/ViewModeProvider';
import { LanguageProvider } from '../state/LanguageProvider';

const renderChooser = () =>
  render(
    <LanguageProvider>
      <ViewModeProvider>
        <ViewModeChooser />
      </ViewModeProvider>
    </LanguageProvider>,
  );

describe('ViewModeChooser', () => {
  it('offers both Interactive and Scoreboard options', () => {
    renderChooser();
    expect(screen.getByText('Interactive')).toBeTruthy();
    expect(screen.getByText('Scoreboard')).toBeTruthy();
  });

  it('marks the auto-detected option as Detected', () => {
    // jsdom UA is not a TV and there's no ?viewmode hint, so the suggestion is
    // 'scoreboard' - exactly one option carries the Detected badge.
    renderChooser();
    expect(screen.getByText('Detected')).toBeTruthy();
  });
});
