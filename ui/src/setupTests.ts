// Vitest global setup for component/DOM tests.
// - jest-dom adds matchers like toBeInTheDocument() / toBeDisabled().
// - cleanup() unmounts React trees between tests so they don't leak into
//   each other (jsdom persists the document across a file otherwise).
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom under vitest does not reliably expose a working window.localStorage
// (Node's disabled experimental global shadows it), yet the app reads/writes
// it for language, unit, column, and tab preferences. Provide a minimal
// in-memory implementation so that storage-backed code runs in tests.
if (typeof window !== 'undefined' && !window.localStorage) {
  const store = new Map<string, string>();
  const memoryStorage: Storage = {
    getItem: (key) => (store.has(key) ? store.get(key)! : null),
    setItem: (key, value) => {
      store.set(key, String(value));
    },
    removeItem: (key) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
  Object.defineProperty(window, 'localStorage', { value: memoryStorage, configurable: true });
}

afterEach(() => {
  cleanup();
  window.localStorage?.clear();
});
