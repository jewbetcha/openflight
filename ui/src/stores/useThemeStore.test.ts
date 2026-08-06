import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  THEME_STORAGE_KEY,
  applyThemeToDocument,
  readStoredTheme,
  useThemeStore,
} from './useThemeStore';

const storage = new Map<string, string>();

const documentElement = {
  attrs: new Map<string, string>(),
  setAttribute(name: string, value: string) {
    this.attrs.set(name, value);
  },
  getAttribute(name: string) {
    return this.attrs.get(name) ?? null;
  },
  removeAttribute(name: string) {
    this.attrs.delete(name);
  },
};

describe('useThemeStore', () => {
  beforeEach(() => {
    storage.clear();
    documentElement.attrs.clear();

    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        },
        clear: () => storage.clear(),
        removeItem: (key: string) => {
          storage.delete(key);
        },
      },
    });

    vi.stubGlobal('document', {
      documentElement,
    });

    useThemeStore.setState({ theme: 'dark' });
    applyThemeToDocument('dark');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('defaults to dark when nothing is stored', () => {
    expect(readStoredTheme()).toBe('dark');
  });

  it('reads a stored light preference', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    expect(readStoredTheme()).toBe('light');
  });

  it('persists theme and updates the document attribute', () => {
    useThemeStore.getState().setTheme('light');

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(useThemeStore.getState().theme).toBe('light');
  });

  it('toggles between light and dark', () => {
    useThemeStore.getState().setTheme('dark');
    useThemeStore.getState().toggleTheme();

    expect(useThemeStore.getState().theme).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');

    useThemeStore.getState().toggleTheme();

    expect(useThemeStore.getState().theme).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
