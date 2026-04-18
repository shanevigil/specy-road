import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  createPendingStore,
  type PendingKind,
  type PendingMutationsApi,
  type PendingStore,
} from "./pendingMutationsCore";

export type { PendingKind, PendingMutationsApi, PendingPhase } from "./pendingMutationsCore";
export { nextPendingToken, SETTLE_MS, FAIL_MS } from "./pendingMutationsCore";

/**
 * React adapter around :func:`createPendingStore`.
 *
 * The adapter only exposes ``pendingIds`` / ``pendingFor`` / ``begin``
 * / ``end`` / ``fail`` to React consumers; the underlying store's
 * ``dispose`` is wired into the unmount cleanup.
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

  // ``tick`` is referenced so the memo is recomputed on every change.
  const snapshot = useMemo(() => {
    void tick;
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

const PendingMutationsContext = createContext<PendingMutationsApi | null>(null);

export function PendingMutationsProvider({
  api,
  children,
}: {
  api: PendingMutationsApi;
  children: ReactNode;
}) {
  return (
    <PendingMutationsContext.Provider value={api}>
      {children}
    </PendingMutationsContext.Provider>
  );
}

const EMPTY_API: PendingMutationsApi = {
  pendingIds: new Set<string>(),
  pendingFor: () => null,
};

/** Read the pending state inside any descendant of ``PendingMutationsProvider``. */
export function usePendingMutations(): PendingMutationsApi {
  return useContext(PendingMutationsContext) ?? EMPTY_API;
}
