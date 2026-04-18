import { describe, expect, it } from "vitest";

import {
  applyOptimistic,
  buildAddPlaceholder,
  isPendingPlaceholderId,
  type OptimisticOp,
} from "./optimisticOutline";
import type { RoadmapNode, RoadmapResponse } from "./types";

function node(
  id: string,
  parent_id: string | null,
  sibling_order: number,
  extras: Partial<RoadmapNode> = {},
): RoadmapNode {
  return {
    id,
    node_key: `key-${id}`,
    type: "task",
    title: id,
    status: "Not Started",
    parent_id,
    dependencies: [],
    sibling_order,
    ...extras,
  };
}

function fixture(): RoadmapResponse {
  // M0 -> M0.1, M0.2, M0.3 ; M1 -> M1.1
  const nodes: RoadmapNode[] = [
    node("M0", null, 0, { type: "phase" }),
    node("M0.1", "M0", 0),
    node("M0.2", "M0", 1),
    node("M0.3", "M0", 2),
    node("M1", null, 1, { type: "phase" }),
    node("M1.1", "M1", 0),
  ];
  return {
    version: 1,
    fingerprint: "1",
    nodes,
    registry: {},
    tree: [],
    dependency_depths: {},
    dependency_spans: {},
    edges: [],
    ordered_ids: [],
    row_depths: [],
    pr_hints: {},
    git_enrichment: {},
  };
}

function siblingsOf(r: RoadmapResponse, parent: string | null): string[] {
  const sibs = r.nodes
    .filter((n) => (n.parent_id ?? null) === parent)
    .sort((a, b) => Number(a.sibling_order ?? 0) - Number(b.sibling_order ?? 0));
  return sibs.map((s) => s.id);
}

describe("applyOptimistic — reorder", () => {
  it("rotates last child to first", () => {
    const op: OptimisticOp = {
      kind: "reorder",
      parentId: "M0",
      orderedChildIds: ["M0.3", "M0.1", "M0.2"],
    };
    const out = applyOptimistic(fixture(), [op]);
    expect(siblingsOf(out, "M0")).toEqual(["M0.3", "M0.1", "M0.2"]);
    // ordered_ids reflects the new tree.
    expect(out.ordered_ids).toEqual(["M0", "M0.3", "M0.1", "M0.2", "M1", "M1.1"]);
    // row_depths still match shape: phase=0, child=1.
    expect(out.row_depths).toEqual([0, 1, 1, 1, 0, 1]);
  });
});

describe("applyOptimistic — move (cross-parent)", () => {
  it("moves M0.3 under M1 at index 0", () => {
    const op: OptimisticOp = {
      kind: "move",
      nodeKey: "key-M0.3",
      newParentId: "M1",
      newIndex: 0,
    };
    const out = applyOptimistic(fixture(), [op]);
    const moved = out.nodes.find((n) => n.id === "M0.3")!;
    expect(moved.parent_id).toBe("M1");
    expect(siblingsOf(out, "M1")).toEqual(["M0.3", "M1.1"]);
    expect(siblingsOf(out, "M0")).toEqual(["M0.1", "M0.2"]);
  });

  it("moves to root (newParentId=null)", () => {
    const op: OptimisticOp = {
      kind: "move",
      nodeKey: "key-M0.3",
      newParentId: null,
      newIndex: 1,
    };
    const out = applyOptimistic(fixture(), [op]);
    expect(siblingsOf(out, null)).toEqual(["M0", "M0.3", "M1"]);
  });
});

describe("applyOptimistic — indent", () => {
  it("makes M0.2 a child of M0.1", () => {
    const op: OptimisticOp = { kind: "indent", nodeId: "M0.2" };
    const out = applyOptimistic(fixture(), [op]);
    const moved = out.nodes.find((n) => n.id === "M0.2")!;
    expect(moved.parent_id).toBe("M0.1");
    expect(siblingsOf(out, "M0")).toEqual(["M0.1", "M0.3"]);
    expect(siblingsOf(out, "M0.1")).toEqual(["M0.2"]);
  });

  it("first sibling cannot indent (no previous)", () => {
    const op: OptimisticOp = { kind: "indent", nodeId: "M0.1" };
    const out = applyOptimistic(fixture(), [op]);
    const moved = out.nodes.find((n) => n.id === "M0.1")!;
    expect(moved.parent_id).toBe("M0");
  });
});

describe("applyOptimistic — outdent", () => {
  it("M0.2 promoted to root, just after its old parent M0", () => {
    const op: OptimisticOp = { kind: "outdent", nodeId: "M0.2" };
    const out = applyOptimistic(fixture(), [op]);
    const moved = out.nodes.find((n) => n.id === "M0.2")!;
    expect(moved.parent_id).toBe(null);
    expect(siblingsOf(out, null)).toEqual(["M0", "M0.2", "M1"]);
  });

  it("root node cannot outdent further", () => {
    const op: OptimisticOp = { kind: "outdent", nodeId: "M0" };
    const out = applyOptimistic(fixture(), [op]);
    const moved = out.nodes.find((n) => n.id === "M0")!;
    expect(moved.parent_id ?? null).toBe(null);
  });
});

describe("applyOptimistic — dep", () => {
  it("replaces explicit dependencies for the named node", () => {
    const op: OptimisticOp = {
      kind: "dep",
      nodeId: "M0.2",
      explicitNodeKeys: ["key-M0.1", "key-M1.1"],
    };
    const out = applyOptimistic(fixture(), [op]);
    const target = out.nodes.find((n) => n.id === "M0.2")!;
    expect(target.dependencies).toEqual(["key-M0.1", "key-M1.1"]);
    // Other nodes untouched.
    const sibling = out.nodes.find((n) => n.id === "M0.1")!;
    expect(sibling.dependencies).toEqual([]);
  });
});

describe("applyOptimistic — add", () => {
  it("inserts placeholder above reference", () => {
    const placeholder = buildAddPlaceholder({
      token: "abc",
      title: "new task",
      type: "task",
      parentId: "M0",
    });
    expect(isPendingPlaceholderId(placeholder.id)).toBe(true);
    const op: OptimisticOp = {
      kind: "add",
      placeholder,
      referenceNodeId: "M0.2",
      position: "above",
    };
    const out = applyOptimistic(fixture(), [op]);
    expect(siblingsOf(out, "M0")).toEqual([
      "M0.1",
      placeholder.id,
      "M0.2",
      "M0.3",
    ]);
    const inserted = out.nodes.find((n) => n.id === placeholder.id)!;
    expect(inserted.title).toBe("new task");
    expect(inserted.parent_id).toBe("M0");
  });

  it("inserts placeholder below reference", () => {
    const placeholder = buildAddPlaceholder({
      token: "x",
      title: "below",
      type: "task",
      parentId: "M0",
    });
    const op: OptimisticOp = {
      kind: "add",
      placeholder,
      referenceNodeId: "M0.2",
      position: "below",
    };
    const out = applyOptimistic(fixture(), [op]);
    expect(siblingsOf(out, "M0")).toEqual([
      "M0.1",
      "M0.2",
      placeholder.id,
      "M0.3",
    ]);
  });
});

describe("applyOptimistic — delete", () => {
  it("removes the node and any descendants", () => {
    const out = applyOptimistic(fixture(), [
      { kind: "delete", nodeId: "M0" },
    ]);
    expect(out.nodes.find((n) => n.id === "M0")).toBeUndefined();
    expect(out.nodes.find((n) => n.id === "M0.1")).toBeUndefined();
    expect(out.nodes.find((n) => n.id === "M0.3")).toBeUndefined();
    // M1 subtree intact.
    expect(siblingsOf(out, null)).toEqual(["M1"]);
    expect(siblingsOf(out, "M1")).toEqual(["M1.1"]);
  });
});

describe("applyOptimistic — composition", () => {
  it("multiple ops apply in order", () => {
    const placeholder = buildAddPlaceholder({
      token: "z",
      title: "composed",
      type: "task",
      parentId: "M0",
    });
    const out = applyOptimistic(fixture(), [
      { kind: "reorder", parentId: "M0", orderedChildIds: ["M0.3", "M0.1", "M0.2"] },
      {
        kind: "add",
        placeholder,
        referenceNodeId: "M0.1",
        position: "below",
      },
      { kind: "dep", nodeId: "M0.2", explicitNodeKeys: ["key-M1.1"] },
    ]);
    expect(siblingsOf(out, "M0")).toEqual([
      "M0.3",
      "M0.1",
      placeholder.id,
      "M0.2",
    ]);
    expect(
      out.nodes.find((n) => n.id === "M0.2")!.dependencies,
    ).toEqual(["key-M1.1"]);
  });

  it("empty op list returns the base unchanged (same reference)", () => {
    const base = fixture();
    expect(applyOptimistic(base, [])).toBe(base);
  });
});
