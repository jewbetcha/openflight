import { render, screen, waitFor } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

// Full-app behaviour tests: the kiosk's primary user journeys, driven through a
// fake socket and a mocked fetch so no real backend is required.
const { fakeSocket } = vi.hoisted(() => ({
  fakeSocket: { on: vi.fn(), emit: vi.fn(), close: vi.fn() },
}));
vi.mock('socket.io-client', () => ({ io: () => fakeSocket }));

let shutdownReject = false;

beforeEach(() => {
  shutdownReject = false;
  // These flows test the interactive kiosk; seed the saved view mode so neither
  // the first-run chooser nor Scoreboard mode (the passive view) gates the app.
  localStorage.setItem('openflight.viewMode', 'interactive');
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const u = String(url);
      if (u.includes('/api/shutdown')) {
        return shutdownReject ? Promise.reject(new Error('down')) : Promise.resolve({ ok: true });
      }
      if (u.includes('/api/history')) {
        return Promise.resolve({ json: () => Promise.resolve({ sessions: [] }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }) as unknown as typeof fetch,
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function dismissClubSelect(user: UserEvent) {
  await user.click(await screen.findByRole('button', { name: 'Close club selection' }));
}

describe('App flows', () => {
  it('shows the club-select interstitial on load and dismisses it', async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole('dialog', { name: 'Select your club' })).toBeInTheDocument();
    await dismissClubSelect(user);

    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Select your club' })).not.toBeInTheDocument(),
    );
  });

  it('switches to the lazily-loaded Analytics tab', async () => {
    const user = userEvent.setup();
    render(<App />);
    await dismissClubSelect(user);

    await user.click(screen.getByRole('button', { name: /Analytics/ }));

    // StatsView is a lazy chunk; with no shots it renders the empty state.
    expect(await screen.findByText('No shots recorded yet')).toBeInTheDocument();
  });

  it('completes the shutdown happy path', async () => {
    const user = userEvent.setup();
    render(<App />);
    await dismissClubSelect(user);

    await user.click(screen.getByRole('button', { name: 'Shut down OpenFlight?' }));
    await user.click(screen.getByRole('button', { name: 'Shut Down' }));

    expect(await screen.findByText('Server stopped. You can close this window.')).toBeInTheDocument();
  });

  it('surfaces an error when the server is unreachable on shutdown', async () => {
    shutdownReject = true;
    const user = userEvent.setup();
    render(<App />);
    await dismissClubSelect(user);

    await user.click(screen.getByRole('button', { name: 'Shut down OpenFlight?' }));
    await user.click(screen.getByRole('button', { name: 'Shut Down' }));

    expect(await screen.findByText(/Could not reach the server/)).toBeInTheDocument();
  });
});
