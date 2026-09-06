import { describe, expect, it } from "vitest";

import {
  BRAINSTORM_WINDOW_ID,
  isGraphWindow,
  orderWindowsForTile,
} from "./editModalLayout";
import type { RoadmapNode } from "./types";

/** A chain: M1 <- M2 <- M3, so dependency order is the reverse of id order. */
function chainNodes(): Record<string, RoadmapNode> {
  const mk = (id: string, key: string, deps: string[]) =>
    ({ id, node_key: key, dependencies: deps }) as unknown as RoadmapNode;
  return {
    M3: mk("M3", "k3", ["k2"]),
    M2: mk("M2", "k2", ["k1"]),
    M1: mk("M1", "k1", []),
  };
}

const ORDERED = ["M1", "M2", "M3"];

describe("isGraphWindow", () => {
  it("treats a roadmap node id as a graph window", () => {
    expect(isGraphWindow("M1.2.3")).toBe(true);
  });

  it("treats the brainstorm window as outside the graph", () => {
    expect(isGraphWindow(BRAINSTORM_WINDOW_ID)).toBe(false);
  });

  it("uses a prefix a roadmap node id cannot take", () => {
    // Node ids are dotted numerics like "M1.2"; the sentinel must never collide.
    expect(BRAINSTORM_WINDOW_ID.startsWith("@")).toBe(true);
  });
});

describe("orderWindowsForTile", () => {
  it("still sorts plain task windows by dependency order", () => {
    expect(orderWindowsForTile(["M3", "M1", "M2"], chainNodes(), ORDERED)).toEqual([
      "M1",
      "M2",
      "M3",
    ]);
  });

  it("puts a non-graph window last rather than sorting it into the chain", () => {
    const got = orderWindowsForTile(
      [BRAINSTORM_WINDOW_ID, "M3", "M1"],
      chainNodes(),
      ORDERED,
    );

    expect(got).toEqual(["M1", "M3", BRAINSTORM_WINDOW_ID]);
  });

  it("handles a stack that is only the brainstorm window", () => {
    expect(orderWindowsForTile([BRAINSTORM_WINDOW_ID], {}, [])).toEqual([
      BRAINSTORM_WINDOW_ID,
    ]);
  });

  it("keeps every window it was given", () => {
    const open = [BRAINSTORM_WINDOW_ID, "M1", "M2", "M3"];

    expect(orderWindowsForTile(open, chainNodes(), ORDERED).sort()).toEqual(
      [...open].sort(),
    );
  });

  it("is empty for an empty stack", () => {
    expect(orderWindowsForTile([], chainNodes(), ORDERED)).toEqual([]);
  });
});
