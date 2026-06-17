import { useEffect } from 'react';

/**
 * 10-foot D-pad navigation for the kiosk/TV shell. A remote's directional
 * buttons arrive as Arrow keys (HDMI-CEC, FLIRC, or any USB remote all map to
 * the keyboard - see docs/tv-remote-control.md), and "OK/Select" arrives as
 * Enter, which focused <button>s activate natively. So all the web layer needs
 * is to move focus toward the nearest control in the pressed direction.
 *
 * Pure geometry lives in pickInDirection() so it can be unit-tested without a
 * DOM. The hook only runs when enabled (TV mode) so it never hijacks arrow
 * keys on the touchscreen kiosk.
 */
export type Direction = 'up' | 'down' | 'left' | 'right';

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Candidate<T> {
  el: T;
  rect: Rect;
}

const KEY_TO_DIR: Record<string, Direction> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
};

function center(r: Rect): { x: number; y: number } {
  return { x: (r.left + r.right) / 2, y: (r.top + r.bottom) / 2 };
}

/**
 * Choose the best candidate in `dir` relative to `current`. The element must
 * lie in the pressed direction; among those, prefer the closest along the
 * travel axis while penalising orthogonal drift so focus tracks straight.
 * Returns null when nothing lies that way (focus stays put).
 */
export function pickInDirection<T>(current: Rect, candidates: Candidate<T>[], dir: Direction): T | null {
  const cc = center(current);
  let best: T | null = null;
  let bestScore = Infinity;

  for (const cand of candidates) {
    const rc = center(cand.rect);
    const dx = rc.x - cc.x;
    const dy = rc.y - cc.y;

    let primary: number;
    let ortho: number;
    let inDir: boolean;
    switch (dir) {
      case 'right':
        inDir = dx > 1;
        primary = dx;
        ortho = Math.abs(dy);
        break;
      case 'left':
        inDir = dx < -1;
        primary = -dx;
        ortho = Math.abs(dy);
        break;
      case 'down':
        inDir = dy > 1;
        primary = dy;
        ortho = Math.abs(dx);
        break;
      case 'up':
        inDir = dy < -1;
        primary = -dy;
        ortho = Math.abs(dx);
        break;
    }
    if (!inDir) continue;

    // Orthogonal drift weighted ~2x so an aligned-but-farther control beats a
    // closer one that is far off to the side.
    const score = primary + ortho * 2;
    if (score < bestScore) {
      bestScore = score;
      best = cand.el;
    }
  }

  return best;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/** A rect intersects the viewport box. */
export function isInViewport(r: Rect, vw: number, vh: number): boolean {
  return r.right > 0 && r.bottom > 0 && r.left < vw && r.top < vh;
}

/** Excluded if hidden, disabled-by-ancestor (aria-hidden), or inert (a closed
 *  dialog is marked inert so its controls drop out of D-pad/Tab order). */
function isReachable(el: HTMLElement): boolean {
  if (el.offsetParent === null && el.getClientRects().length === 0) return false;
  return !el.closest('[aria-hidden="true"]') && !el.closest('[inert]');
}

/**
 * Collect focusable controls within `scope`, each with its rect taken ONCE
 * (avoids per-element layout thrash). By default only on-screen controls are
 * returned; pass includeOffscreen for the scroll fallback so the D-pad can
 * step toward a below-the-fold control and scroll it into view.
 */
function getFocusablesIn(
  scope: ParentNode,
  vw: number,
  vh: number,
  includeOffscreen = false,
): Array<Candidate<HTMLElement>> {
  const els = Array.from(scope.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  const out: Array<Candidate<HTMLElement>> = [];
  for (const el of els) {
    if (!isReachable(el)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    if (!includeOffscreen && !isInViewport(rect, vw, vh)) continue;
    out.push({ el, rect });
  }
  return out;
}

/** Topmost open modal dialog, if any - used to trap focus inside it. aria-modal
 *  is gated on the dialog being open, so a closed panel is never matched. */
function getModalRoot(vw: number, vh: number): HTMLElement | null {
  const modals = Array.from(document.querySelectorAll<HTMLElement>('[aria-modal="true"]'));
  for (let i = modals.length - 1; i >= 0; i--) {
    const el = modals[i];
    if (el.closest('[inert]')) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && isInViewport(r, vw, vh)) return el;
  }
  return null;
}

/** Don't hijack keys while a text field or native select is being edited. */
function isTextEntry(el: Element | null): boolean {
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (el as HTMLElement).isContentEditable;
}

function moveFocus(el: HTMLElement): void {
  // Mark that the user is navigating by key/remote so a focus ring shows even in
  // Display (monitor) mode, where the always-on `.tv` ring isn't present. The
  // class is cleared on the next pointer interaction (see useSpatialNavigation).
  document.documentElement.classList.add('using-dpad');
  el.focus();
  // Pull off-screen targets into view (tvOS/APG: focus + scroll together).
  el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

/**
 * Move focus to the nearest control in `dir`. The single source of truth for
 * navigation - called directly by both the keyboard handler and the web-remote
 * bridge, so there are NO synthesized KeyboardEvents (WebKit/Tizen/webOS drop
 * `.key` from the KeyboardEvent constructor, which would silently break the
 * remote on the exact TVs we target). Returns whether focus moved.
 */
export function navigate(dir: Direction): boolean {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const modalRoot = getModalRoot(vw, vh);
  const scope: ParentNode = modalRoot ?? document;
  const focusables = getFocusablesIn(scope, vw, vh);
  if (focusables.length === 0) return false;

  const active = document.activeElement as HTMLElement | null;
  const activeEntry = active && focusables.find((f) => f.el === active);
  if (!activeEntry) {
    moveFocus(focusables[0].el);
    return true;
  }

  const rivals = focusables.filter((f) => f.el !== active);
  let next = pickInDirection(activeEntry.rect, rivals, dir);
  if (!next) {
    // Nothing on-screen that way - step to a just-off-viewport control (long
    // history/stats lists) and scroll it in.
    const all = getFocusablesIn(scope, vw, vh, true).filter((f) => f.el !== active);
    next = pickInDirection(activeEntry.rect, all, dir);
  }
  if (next) {
    moveFocus(next);
    return true;
  }
  return false;
}

/** Activate (click) the focused control - OK/Select. No-op on body/null. */
export function activateFocused(): void {
  const el = document.activeElement as HTMLElement | null;
  if (el && el !== document.body) el.click();
}

/** Dismiss the topmost open dialog by clicking its [data-modal-dismiss] control
 *  - Back. Avoids a synthetic Escape (unreliable on WebKit TVs). */
export function dismissTopModal(): boolean {
  const modal = getModalRoot(window.innerWidth, window.innerHeight);
  const dismiss = modal?.querySelector<HTMLElement>('[data-modal-dismiss]');
  if (dismiss) {
    dismiss.click();
    return true;
  }
  return false;
}

const REMOTE_TO_DIR: Record<string, Direction> = {
  up: 'up',
  down: 'down',
  left: 'left',
  right: 'right',
};

/**
 * Phone/tablet web-remote bridge: a relayed D-pad key (delivered as the
 * 'openflight:remotekey' window event by useSocket) calls the focus engine
 * DIRECTLY - no synthesized DOM events - so it behaves identically to the
 * keyboard path and works on WebKit-based TV browsers.
 */
export function useRemoteKeyBridge(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const onRemote = (e: Event) => {
      const key = (e as CustomEvent<string>).detail;
      if (key in REMOTE_TO_DIR) navigate(REMOTE_TO_DIR[key]);
      else if (key === 'ok') activateFocused();
      else if (key === 'back') dismissTopModal();
    };
    window.addEventListener('openflight:remotekey', onRemote);
    return () => window.removeEventListener('openflight:remotekey', onRemote);
  }, [enabled]);
}

export function useSpatialNavigation(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;

    const handler = (e: KeyboardEvent) => {
      // Ignore OS key-repeat: a held D-pad must not stride many cells per press.
      if (e.repeat || e.altKey || e.ctrlKey || e.metaKey) return;

      const active = document.activeElement as HTMLElement | null;
      if (isTextEntry(active)) return;

      // Trap Tab/Shift-Tab inside an open dialog (keyboards/some remotes emit Tab).
      if (e.key === 'Tab') {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const modalRoot = getModalRoot(vw, vh);
        if (modalRoot) {
          const items = getFocusablesIn(modalRoot, vw, vh).map((c) => c.el);
          if (items.length > 0) {
            const idx = active ? items.indexOf(active) : -1;
            const nextIdx = e.shiftKey
              ? idx <= 0
                ? items.length - 1
                : idx - 1
              : idx === -1 || idx === items.length - 1
                ? 0
                : idx + 1;
            moveFocus(items[nextIdx]);
            e.preventDefault();
          }
        }
        return;
      }

      const dir = KEY_TO_DIR[e.key];
      if (!dir) return;

      // In TV mode the page must never scroll out from under focus, so consume
      // the arrow even when focus can't move (already at the edge).
      e.preventDefault();
      navigate(dir);
    };

    // Pointer use means the user isn't on the D-pad - drop the focus-ring marker.
    const clearDpad = () => document.documentElement.classList.remove('using-dpad');

    window.addEventListener('keydown', handler);
    window.addEventListener('pointerdown', clearDpad, true);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('pointerdown', clearDpad, true);
    };
  }, [enabled]);
}
