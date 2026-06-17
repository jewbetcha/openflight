import { useCallback, useState } from 'react';

/**
 * Boolean state backed by localStorage. Centralizes the read/write try/catch
 * that was duplicated across several UI toggles, and gives a single seam for
 * future versioning. Storage failures (private mode, quota, disabled) fall
 * back to the in-memory value rather than throwing.
 *
 * Only `'true'`/`'false'` are ever persisted; a missing key uses defaultValue.
 */
export function usePersistentBoolean(
  key: string,
  defaultValue: boolean,
): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored === null ? defaultValue : stored === 'true';
    } catch {
      return defaultValue;
    }
  });

  const set = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        localStorage.setItem(key, String(next));
      } catch {
        /* ignore storage quota/availability errors */
      }
    },
    [key],
  );

  return [value, set];
}
