import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RemoteControl } from './RemoteControl';
import { LanguageProvider } from '../state/LanguageProvider';

const renderRemote = (props: Parameters<typeof RemoteControl>[0]) =>
  render(
    <LanguageProvider>
      <RemoteControl {...props} />
    </LanguageProvider>,
  );

describe('RemoteControl', () => {
  it('renders a labelled D-pad with OK and Back and a connection state', () => {
    renderRemote({ sendKey: () => {}, connected: true });
    for (const label of ['Up', 'Down', 'Left', 'Right', 'Select']) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    expect(screen.getByText('Back')).toBeTruthy();
    expect(screen.getByText('Connected')).toBeTruthy();
  });

  it('relays the matching key for each button press', () => {
    const sendKey = vi.fn();
    renderRemote({ sendKey, connected: true });
    fireEvent.click(screen.getByLabelText('Up'));
    fireEvent.click(screen.getByLabelText('Down'));
    fireEvent.click(screen.getByLabelText('Left'));
    fireEvent.click(screen.getByLabelText('Right'));
    fireEvent.click(screen.getByLabelText('Select'));
    fireEvent.click(screen.getByText('Back'));
    expect(sendKey.mock.calls.map((c) => c[0])).toEqual(['up', 'down', 'left', 'right', 'ok', 'back']);
  });

  it('shows a connecting state when not connected', () => {
    renderRemote({ sendKey: () => {}, connected: false });
    expect(screen.getByText('Connecting…')).toBeTruthy();
  });
});
