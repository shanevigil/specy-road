import { describe, expect, it } from "vitest";
import {
  effectiveDependencyKeysForNode,
  transitiveEffectivePrereqIds,
} from "./depChain";
import type { RoadmapNode } from "./types";

/** Minimal nodes: M3 under M2 under M1; M3 explicitly depends on M1's node_key. */
function chainNodes(): Record<string, RoadmapNode> {
  const nk1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const nk2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
  const nk3 = "cccccccc-cccc-cccc-cccc-cccccccccccc";
  return {
    M1: {
      id: "M1",
      node_key: nk1,
      type: "milestone",
      title: "m1",
      parent_id: null,
      dependencies: [],
    },
    M2: {
      id: "M2",
      node_key: nk2,
      type: "milestone",
      title: "m2",
      parent_id: "M1",
      dependencies: [],
    },
    M3: {
      id: "M3",
      node_key: nk3,
      type: "task",
      title: "m3",
      parent_id: "M2",
      dependencies: [nk1],
    },
  };
}

describe("effectiveDependencyKeysForNode", () => {
  it("collects explicit deps on the node and deps on each ancestor", () => {
    const byId = chainNodes();
    const nk1 = byId.M1!.node_key;
    const keys = effectiveDependencyKeysForNode(byId.M3!, byId);
    expect(keys.has(nk1)).toBe(true);
  });
});

describe("transitiveEffectivePrereqIds", () => {
  it("returns transitive display ids for effective deps (excludes selection)", () => {
    const byId = chainNodes();
    const keyToDisplayId: Record<string, string> = {
      [byId.M1!.node_key]: "M1",
      [byId.M2!.node_key]: "M2",
      [byId.M3!.node_key]: "M3",
    };
    const out = transitiveEffectivePrereqIds("M3", byId, keyToDisplayId);
    expect(out.has("M1")).toBe(true);
    expect(out.has("M3")).toBe(false);
  });
});
