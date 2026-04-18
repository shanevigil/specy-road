import { describe, expect, it } from "vitest";
import type { RoadmapNode } from "./types";
import {
  contiguousSubtreeIds,
  visibleDragSubtreeIds,
} from "./outlineSubtree";

describe("contiguousSubtreeIds", () => {
  it("returns single id for a leaf", () => {
    expect(
      contiguousSubtreeIds(["a", "b"], [0, 0], "b"),
    ).toEqual(["b"]);
  });

  it("includes direct children and stops at next sibling depth", () => {
    const ids = ["root", "c1", "c2", "sib"];
    const depths = [0, 1, 1, 0];
    expect(contiguousSubtreeIds(ids, depths, "root")).toEqual([
      "root",
      "c1",
      "c2",
    ]);
  });

  it("includes nested descendants", () => {
    const ids = ["a", "b", "c", "d"];
    const depths = [0, 1, 2, 0];
    expect(contiguousSubtreeIds(ids, depths, "a")).toEqual(["a", "b", "c"]);
  });

  it("returns empty when root id is missing", () => {
    expect(contiguousSubtreeIds(["x"], [0], "missing")).toEqual([]);
  });
});

function node(
  id: string,
  parent_id: string | null,
): RoadmapNode {
  return {
    id,
    node_key: `k_${id}`,
    type: "feature",
    title: id,
    parent_id,
  };
}

describe("visibleDragSubtreeIds", () => {
  it("matches contiguous slice when the full preorder is visible", () => {
    const ids = ["root", "c1", "c2", "sib"];
    const depths = [0, 1, 1, 0];
    const byId: Record<string, RoadmapNode> = {
      root: node("root", null),
      c1: node("c1", "root"),
      c2: node("c2", "root"),
      sib: node("sib", null),
    };
    expect(visibleDragSubtreeIds(ids, byId, "root")).toEqual(
      contiguousSubtreeIds(ids, depths, "root"),
    );
  });

  it("includes visible descendants when intermediate ancestors are omitted from the list", () => {
    /** A → B → C and A → D; B is hidden (e.g. complete); visible preorder A, C, D. */
    const visible = ["A", "C", "D"];
    const byId: Record<string, RoadmapNode> = {
      A: node("A", null),
      B: node("B", "A"),
      C: node("C", "B"),
      D: node("D", "A"),
    };
    /** Depth-only contiguous slice can miss later rows when filtered depths dip (see doc on contiguousSubtreeIds). */
    expect(visibleDragSubtreeIds(visible, byId, "A")).toEqual(["A", "C", "D"]);
  });

  it("returns empty when root is not in the visible list", () => {
    const byId: Record<string, RoadmapNode> = {
      x: node("x", null),
    };
    expect(visibleDragSubtreeIds([], byId, "x")).toEqual([]);
  });

  it("uses parent_id when depth no longer reflects nesting after filtering", () => {
    /** After hiding rows, two visible siblings in preorder can share the same depth value; depth-only slice would stop too early. */
    const visible = ["R", "C"];
    const depths = [0, 0];
    const byId: Record<string, RoadmapNode> = {
      R: node("R", null),
      C: node("C", "R"),
    };
    expect(contiguousSubtreeIds(visible, depths, "R")).toEqual(["R"]);
    expect(visibleDragSubtreeIds(visible, byId, "R")).toEqual(["R", "C"]);
  });
});
