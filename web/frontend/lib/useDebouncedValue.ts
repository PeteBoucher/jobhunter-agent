import { useEffect, useState } from "react";

/**
 * Return `value` once it has stopped changing for `delayMs`.
 *
 * Used by the feed's keyword search: without it every keystroke started a
 * GET /jobs (each a 10s+ description ILIKE scan), and typing a word ran
 * several at once and OOM-killed the 512MB Render API instance.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
