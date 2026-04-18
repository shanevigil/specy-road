import { type ReactNode } from "react";

import type { PendingMutationsApi } from "./pendingMutationsCore";
import { PendingMutationsContext } from "./pendingMutationsContext";

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
