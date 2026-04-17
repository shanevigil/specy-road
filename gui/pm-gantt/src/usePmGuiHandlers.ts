import { useContext } from "react";

import {
  PmGuiHandlersContext,
  type PmGuiHandlers,
} from "./pmGuiContext";

export function usePmGuiHandlers(): PmGuiHandlers {
  const v = useContext(PmGuiHandlersContext);
  if (!v) {
    throw new Error("usePmGuiHandlers must be used within PmGuiHandlersProvider");
  }
  return v;
}
