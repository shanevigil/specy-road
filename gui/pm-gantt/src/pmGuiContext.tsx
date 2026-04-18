/* Context + provider only; hook lives in usePmGuiHandlers.ts for react-refresh. */
/* eslint-disable react-refresh/only-export-components -- share PmGuiHandlersContext with hook module */
import { createContext, type ReactNode } from "react";

export type PmGuiHandlers = {
  /** Reload roadmap after 412/428 so the client matches the server. */
  onConcurrencyConflict: () => Promise<void>;
};

export const PmGuiHandlersContext = createContext<PmGuiHandlers | null>(null);

export function PmGuiHandlersProvider({
  children,
  value,
}: {
  children: ReactNode;
  value: PmGuiHandlers;
}) {
  return (
    <PmGuiHandlersContext.Provider value={value}>
      {children}
    </PmGuiHandlersContext.Provider>
  );
}
