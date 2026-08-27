import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { Shot } from '../../types/shot';
import { PlayersPanel } from './PlayersPanel';

function text(html: string): string {
  return html.replace(/<!-- -->/g, '');
}

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    ball_speed_mph: 90,
    club_speed_mph: 67,
    smash_factor: 1.34,
    estimated_carry_yards: 200,
    carry_range: [195, 205],
    club: 'driver',
    player_name: 'James',
    timestamp: '2026-08-19T10:00:00Z',
    peak_magnitude: 100,
    launch_angle_vertical: 13,
    launch_angle_horizontal: 0,
    launch_angle_confidence: 0.8,
    angle_source: 'radar',
    club_angle_deg: null,
    club_path_deg: null,
    spin_axis_deg: null,
    spin_rpm: 2600,
    spin_confidence: 0.9,
    spin_quality: 'high',
    spin_source: 'measured',
    spin_method: null,
    carry_spin_adjusted: null,
    ...overrides,
  };
}

function render(overrides: Partial<Parameters<typeof PlayersPanel>[0]> = {}) {
  return text(
    renderToString(
      <PlayersPanel
        players={['James']}
        selectedPlayer="James"
        shots={[]}
        onSelectPlayer={() => {}}
        onRemovePlayer={() => {}}
        {...overrides}
      />
    )
  );
}

describe('PlayersPanel', () => {
  it('renders a Players header with the selected name', () => {
    const html = render();

    expect(html).toContain('panel-header__title">Players<');
    expect(html).toContain('panel-header__subtitle">James<');
  });

  it('places Add player in the header', () => {
    const html = render({
      headerAction: (
        <button type="button" className="panel-action">
          Add player
        </button>
      ),
    });
    const header = html.match(/<header class="panel-header">[\s\S]*?<\/header>/)?.[0] ?? '';

    expect(header).toContain('Add player');
  });

  it('lays out player cards in a vertically scrollable grid', () => {
    const html = render({ players: ['James', 'Alex'] });

    expect(html).toContain('players-panel__grid');
    expect(html).toContain('aria-label="Players"');
    expect(html).toContain('James');
    expect(html).toContain('Alex');
  });

  it('marks the selected player and hides remove when only one remains', () => {
    const html = render();

    expect(html).toContain('aria-pressed="true"');
    expect(html).not.toContain('Remove James');
  });

  it('does not offer remove on the active player', () => {
    const html = render({ players: ['James', 'Alex'], selectedPlayer: 'James' });

    expect(html).not.toContain('aria-label="Remove James"');
    expect(html).toContain('aria-label="Remove Alex"');
  });

  it('counts shots for each player independently', () => {
    const html = render({
      players: ['James', 'Alex'],
      shots: [
        makeShot({ player_name: 'James', timestamp: 'a' }),
        makeShot({ player_name: 'James', timestamp: 'b' }),
        makeShot({ player_name: 'Alex', timestamp: 'c' }),
      ],
    });

    expect(html).toContain('2 shots');
    expect(html).toContain('1 shot');
  });
});
