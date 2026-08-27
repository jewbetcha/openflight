export type PanelView = 'live' | 'players' | 'stats' | 'shots' | 'camera' | 'debug';

/**
 * Footer tabs, in order. Design doc 6a uses text-only tabs, so no icons here.
 */
export const PANEL_VIEWS: ReadonlyArray<{ id: PanelView; label: string }> = [
  { id: 'live', label: 'Live' },
  { id: 'stats', label: 'Stats' },
  { id: 'shots', label: 'Shots' },
  { id: 'camera', label: 'Camera' },
  { id: 'players', label: 'Players' },
  { id: 'debug', label: 'Debug' },
];
