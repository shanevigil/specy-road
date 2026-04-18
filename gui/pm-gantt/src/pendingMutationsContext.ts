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
