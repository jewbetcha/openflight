import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LanguageProvider } from '../state/LanguageProvider';
import type { Shot } from '../types/shot';
import { DisplayShotVisualizer } from './DisplayShotVisualizer';

function makeShot(club: string, timestamp: string, overrides: Partial<Shot> = {}): Shot {
  return {
    ball_speed_mph: 150,
    club_speed_mph: 100,
    smash_factor: 1.5,
    estimated_carry_yards: 240,
    carry_range: [230, 250],
    club,
    timestamp,
    peak_magnitude: 40,
    launch_angle_vertical: 14,
    launch_angle_horizontal: 1,
    launch_angle_confidence: 0.8,
    angle_source: 'radar',
    club_angle_deg: 2,
    club_path_deg: 1,
    spin_axis_deg: -1,
    spin_rpm: 2400,
    spin_confidence: 0.8,
    spin_quality: 'high',
    carry_spin_adjusted: 245,
    ...overrides,
  };
}

function render(node: React.ReactElement) {
  return renderToString(<LanguageProvider>{node}</LanguageProvider>);
}

const dotCount = (html: string) =>
  (html.match(/r="3\.5"/g) ?? []).length + (html.match(/r="4\.5"/g) ?? []).length;

describe('DisplayShotVisualizer', () => {
  it('renders both the trajectory and dispersion charts', () => {
    const shots = [makeShot('driver', 't1'), makeShot('driver', 't2'), makeShot('driver', 't3')];
    const html = render(
      <DisplayShotVisualizer shots={shots} latestShot={shots[2]} distUnit="yards" reduceMotion={false} />,
    );
    expect(html).toContain('trajectory-chart');
    expect(html).toContain('dispersion-chart');
  });

  it('plots only the current club (latest shot club)', () => {
    const shots = [
      makeShot('driver', 't1'),
      makeShot('7-iron', 't2'),
      makeShot('driver', 't3'),
      makeShot('7-iron', 't4'),
    ];
    // latest is a driver → only the 2 driver dots should be plotted, not the 7-irons
    const html = render(
      <DisplayShotVisualizer shots={shots} latestShot={shots[2]} distUnit="yards" reduceMotion={false} />,
    );
    expect(dotCount(html)).toBe(2);
  });

  it('animates the latest shot in when motion is allowed', () => {
    const shots = [makeShot('driver', 't1'), makeShot('driver', 't2')];
    const html = render(
      <DisplayShotVisualizer shots={shots} latestShot={shots[1]} distUnit="yards" reduceMotion={false} />,
    );
    expect(html).toContain('traj-arc--animate');
    expect(html).toContain('disp-dot--slam');
  });

  it('omits the animation when Reduce Motion is on', () => {
    const shots = [makeShot('driver', 't1'), makeShot('driver', 't2')];
    const html = render(
      <DisplayShotVisualizer shots={shots} latestShot={shots[1]} distUnit="yards" reduceMotion={true} />,
    );
    expect(html).not.toContain('traj-arc--animate');
    expect(html).not.toContain('disp-dot--slam');
  });

  it('hides the decorative chart SVGs from screen readers', () => {
    const shots = [makeShot('driver', 't1'), makeShot('driver', 't2'), makeShot('driver', 't3')];
    const html = render(
      <DisplayShotVisualizer shots={shots} latestShot={shots[2]} distUnit="yards" reduceMotion={false} />,
    );
    const hiddenSvgs = html.match(/<svg[^>]*aria-hidden="true"/g) ?? [];
    expect(hiddenSvgs.length).toBe(2); // trajectory + dispersion
  });

  it('shows the ready state when there is no shot', () => {
    const html = render(
      <DisplayShotVisualizer shots={[]} latestShot={null} distUnit="yards" reduceMotion={false} />,
    );
    expect(html).toContain('display-viz--empty');
  });
});
