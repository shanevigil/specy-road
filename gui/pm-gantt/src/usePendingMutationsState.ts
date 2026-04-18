import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  createPendingStore,
  type PendingKind,
  type PendingMutationsApi,
  type PendingStore,
} from "./pendingMutationsCore";

/**
 * React adapter around :func:`createPendingStore`.
 *
 * The adapter exposes ``pendingIds`` / ``pendingFor`` / ``begin`` /
 * ``end`` / ``fail`` to React consumers; the underlying store's
 * ``dispose`` is wired into the unmount cleanup. Lives in its own
 * file so the React Refresh plugin can fast-reload the provider
 * component independently.
 */
export function usePendingMutationsState(): PendingMutationsApi & {
  begin: PendingStore["begin"];
  end: PendingStore["end"];
  fail: PendingStore["fail"];
} {
  const [tick, setTick] = useState(0);
  const storeRef = useRef<PendingStore | null>(null);
  if (!storeRef.current) {
    storeRef.current = createPendingStore({
      onChange: () => setTick((n) => (n + 1) | 0),
    });
  }
  const store = storeRef.current;

  useEffect(() => {
    return () => {
      store.dispose();
    };
  }, [store]);

  const snapshot = useMemo(() => {
    void tick; // re-run when the store fires onChange
    return {
      pendingIds: store.pendingIds,
      pendingFor: (id: string) => store.pendingFor(id),
    };
  }, [store, tick]);

  const begin = useCallback(
    (token: string, ids: string[], kind: PendingKind) =>
      store.begin(token, ids, kind),
    [store],
  );
  const end = useCallback((token: string) => store.end(token), [store]);
  const fail = useCallback((token: string) => store.fail(token), [store]);

  return useMemo(
    () => ({ ...snapshot, begin, end, fail }),
    [snapshot, begin, end, fail],
  );
}
