import { useState } from 'react';

/**
 * Centralized detection for the kiosk's pathname-based routes (there is no
 * client-side router): the passive `/scoreboard` display and the `/remote`
 * web-remote. Kept in one place so every surface reasons about routes from a
 * single, testable source.
 */

/** Pure: does this pathname address the /scoreboard display route (trailing slash ok)? */
export function isScoreboardPath(pathname: string): boolean {
  return pathname.replace(/\/+$/, '') === '/scoreboard';
}

/** Pure: does this pathname address the /remote web-remote route? */
export function isRemotePath(pathname: string): boolean {
  return pathname.replace(/\/+$/, '') === '/remote';
}

/**
 * The kiosk has no client-side router, so the route is fixed for the life of
 * the document - read it once on mount.
 */
export function useScoreboardRoute(): boolean {
  return useState(() => (typeof window !== 'undefined' ? isScoreboardPath(window.location.pathname) : false))[0];
}

export function useRemoteRoute(): boolean {
  return useState(() => (typeof window !== 'undefined' ? isRemotePath(window.location.pathname) : false))[0];
}
