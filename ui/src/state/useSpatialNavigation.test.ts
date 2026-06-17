import { afterEach, describe, expect, it, vi } from 'vitest';
import { activateFocused, dismissTopModal, isInViewport, pickInDirection, type Rect } from './useSpatialNavigation';

const rect = (left: number, top: number, w = 40, h = 20): Rect => ({
  left,
  top,
  right: left + w,
  bottom: top + h,
});

const current = rect(100, 100);

describe('pickInDirection', () => {
  it('picks the nearest aligned candidate to the right', () => {
    const near = { el: 'near', rect: rect(160, 100) };
    const far = { el: 'far', rect: rect(300, 100) };
    expect(pickInDirection(current, [far, near], 'right')).toBe('near');
  });

  it('ignores candidates that are not in the pressed direction', () => {
    const left = { el: 'left', rect: rect(0, 100) };
    expect(pickInDirection(current, [left], 'right')).toBeNull();
  });

  it('prefers an aligned-but-farther target over a closer off-axis one', () => {
    // aligned is farther along X but on the same row; offAxis is closer in X
    // but far above - orthogonal drift should make aligned win.
    const aligned = { el: 'aligned', rect: rect(220, 100) };
    const offAxis = { el: 'offAxis', rect: rect(170, -200) };
    expect(pickInDirection(current, [aligned, offAxis], 'right')).toBe('aligned');
  });

  it('navigates up, down, and left', () => {
    const up = { el: 'up', rect: rect(100, 20) };
    const down = { el: 'down', rect: rect(100, 200) };
    const left = { el: 'left', rect: rect(20, 100) };
    const candidates = [up, down, left];
    expect(pickInDirection(current, candidates, 'up')).toBe('up');
    expect(pickInDirection(current, candidates, 'down')).toBe('down');
    expect(pickInDirection(current, candidates, 'left')).toBe('left');
  });

  it('returns null when there are no candidates', () => {
    expect(pickInDirection(current, [], 'down')).toBeNull();
  });
});

describe('isInViewport', () => {
  const vw = 1920;
  const vh = 1080;

  it('accepts a rect inside the viewport', () => {
    expect(isInViewport(rect(100, 100), vw, vh)).toBe(true);
  });

  it('rejects a panel parked off-screen to the right (closed slide-in)', () => {
    expect(isInViewport(rect(2000, 100), vw, vh)).toBe(false);
  });

  it('rejects rects fully above or below the viewport', () => {
    expect(isInViewport(rect(100, -100, 40, 20), vw, vh)).toBe(false);
    expect(isInViewport(rect(100, 1200), vw, vh)).toBe(false);
  });

  it('accepts a rect partially overlapping the edge', () => {
    expect(isInViewport(rect(1900, 100), vw, vh)).toBe(true); // right edge straddles 1920
  });
});

describe('activateFocused', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('clicks the focused control', () => {
    document.body.innerHTML = '<button id="b">go</button>';
    const btn = document.getElementById('b') as HTMLButtonElement;
    const onClick = vi.fn();
    btn.addEventListener('click', onClick);
    btn.focus();
    activateFocused();
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does nothing when focus is on <body>', () => {
    document.body.innerHTML = '<button id="b">go</button>';
    const onClick = vi.fn();
    document.getElementById('b')!.addEventListener('click', onClick);
    (document.activeElement as HTMLElement)?.blur();
    activateFocused();
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('dismissTopModal', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('clicks the [data-modal-dismiss] control inside the open modal', () => {
    document.body.innerHTML =
      '<div aria-modal="true"><button data-modal-dismiss id="x">close</button></div>';
    const modal = document.querySelector('[aria-modal="true"]') as HTMLElement;
    // jsdom returns zero-size rects; give the modal an on-screen rect so
    // getModalRoot accepts it.
    modal.getBoundingClientRect = () =>
      ({ left: 0, top: 0, right: 100, bottom: 100, width: 100, height: 100 }) as DOMRect;
    const onClick = vi.fn();
    document.getElementById('x')!.addEventListener('click', onClick);
    expect(dismissTopModal()).toBe(true);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('returns false when no modal is open', () => {
    document.body.innerHTML = '<button>not a modal</button>';
    expect(dismissTopModal()).toBe(false);
  });
});
