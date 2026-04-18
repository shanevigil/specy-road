import { createContext, useContext } from "react";

import type { PendingMutationsApi } from "./pendingMutationsCore";

const EMPTY_API: PendingMutationsApi = {
  pendingIds: new Set<string>(),
  pendingFor: () => null,
};

/** Internal — exported only for ``PendingMutationsProvider`` to wrap with. */
export const PendingMutationsContext =
  createContext<PendingMutationsApi | null>(null);

/** Read the pending state inside any descendant of ``PendingMutationsProvider``. */
export function usePendingMutations(): PendingMutationsApi {
  return useContext(PendingMutationsContext) ?? EMPTY_API;
}

/**
 * True if ``id`` is currently mid-mutation (server hasn't acked yet).
 * The brief post-success ``settling`` window does NOT count as locked
 * — the server has already returned, the row is safe to act on. The
 * post-failure ``fail`` window doesn't count either; the row has
 * reverted and the user can retry immediately.
 */
export function isRowLocked(api: PendingMutationsApi, id: string): boolean {
  const p = api.pendingFor(id);
  return p?.phase === "active";
}
