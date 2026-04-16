import { describe, expect, it } from "vitest";
import {
  buildDisplayStatusWithPhaseRollup,
  childrenIdsByParentId,
  computeEffectiveDisplayById,
  computeEffectiveDisplayForAllNodes,
  DISPLAY_STATUS_COMPLETE,
  phaseRollupDerivedComplete,
  postOrderIdsForForest,
} from "./parentStatusRollup";
import { pmDisplayStatus } from "./pmDisplayStatus";
import type { RoadmapNode } from "./types";

const K = (n: number) =>
  `${n.toString().padStart(8, "0")}-0000-4000-8000-${n.toString().padStart(12, "0")}`;

function phase(
  id: string,
  status: string,
  parent: string | null = null,
): RoadmapNode {
  return {
    id,
    node_key: K(1),
    type: "phase",
    title: id,
    status,
    parent_id: parent,
  };
}

function milestone(
  id: string,
  status: string,
  parent: string,
  key = 2,
): RoadmapNode {
  return {
    id,
    node_key: K(key),
    type: "milestone",
    title: id,
    status,
    parent_id: parent,
  };
}

describe("computeEffectiveDisplayById", () => {
  it("marks parent Complete when all direct children are Complete", () => {
    const nodes = [phase("M1", "In Progress"), milestone("M1.1", "Complete", "M1")];
    const byId: Record<string, RoadmapNode | undefined> = {
      M1: nodes[0],
      "M1.1": nodes[1],
    };
    const ordered = ["M1.1", "M1"];
    const base = {
      M1: pmDisplayStatus(byId.M1, undefined),
      "M1.1": pmDisplayStatus(byId["M1.1"], undefined),
    };
    const ch = childrenIdsByParentId(nodes);
    const post = postOrderIdsForForest(ordered, byId, ch);
    const eff = computeEffectiveDisplayById(post, base, ch);
    expect(eff["M1.1"]).toBe(DISPLAY_STATUS_COMPLETE);
    expect(eff.M1).toBe(DISPLAY_STATUS_COMPLETE);
  });

  it("does not roll to Complete when a child is Blocked", () => {
    const nodes = [
      phase("M1", "In Progress"),
      milestone("M1.1", "Blocked", "M1"),
      milestone("M1.2", "Complete", "M1", 3),
    ];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1.1", "M1.2", "M1"];
    const base = {
      M1: pmDisplayStatus(byId.M1, undefined),
      "M1.1": pmDisplayStatus(byId["M1.1"], undefined),
      "M1.2": pmDisplayStatus(byId["M1.2"], undefined),
    };
    const ch = childrenIdsByParentId(nodes);
    const post = postOrderIdsForForest(ordered, byId, ch);
    const eff = computeEffectiveDisplayById(post, base, ch);
    expect(eff.M1).toBe("In Progress");
  });
});

describe("computeEffectiveDisplayForAllNodes", () => {
  it("marks all ids Complete when phase and milestones are fully complete", () => {
    const nodes = [
      phase("M1", "In Progress"),
      milestone("M1.1", "Complete", "M1"),
      milestone("M1.2", "Complete", "M1", 3),
    ];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1", "M1.1", "M1.2"];
    const eff = computeEffectiveDisplayForAllNodes(ordered, byId, undefined, {
      enabled: true,
    });
    expect(eff.M1).toBe(DISPLAY_STATUS_COMPLETE);
    expect(eff["M1.1"]).toBe(DISPLAY_STATUS_COMPLETE);
    expect(eff["M1.2"]).toBe(DISPLAY_STATUS_COMPLETE);
  });

  it("keeps phase incomplete when one sibling branch is still incomplete", () => {
    const nodes = [
      phase("M1", "In Progress"),
      milestone("M1.1", "Complete", "M1"),
      milestone("M1.2", "In Progress", "M1", 3),
    ];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1", "M1.1", "M1.2"];
    const eff = computeEffectiveDisplayForAllNodes(ordered, byId, undefined, {
      enabled: true,
    });
    expect(eff.M1).toBe("In Progress");
    expect(eff["M1.1"]).toBe(DISPLAY_STATUS_COMPLETE);
    expect(eff["M1.2"]).toBe("In Progress");
  });

  it("does not roll parent to Complete when a child is Blocked", () => {
    const nodes = [
      phase("M1", "In Progress"),
      milestone("M1.1", "Blocked", "M1"),
      milestone("M1.2", "Complete", "M1", 3),
    ];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1.1", "M1.2", "M1"];
    const eff = computeEffectiveDisplayForAllNodes(ordered, byId, undefined, {
      enabled: true,
    });
    expect(eff.M1).toBe("In Progress");
  });

  it("returns base statuses only when rollup disabled", () => {
    const nodes = [phase("M1", "In Progress"), milestone("M1.1", "Complete", "M1")];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1", "M1.1"];
    const eff = computeEffectiveDisplayForAllNodes(ordered, byId, undefined, {
      enabled: false,
    });
    expect(eff.M1).toBe("In Progress");
    expect(eff["M1.1"]).toBe(DISPLAY_STATUS_COMPLETE);
  });
});

describe("buildDisplayStatusWithPhaseRollup", () => {
  it("shows phase Complete when milestones Complete but phase chunk says In Progress", () => {
    const nodes = [
      phase("M1", "In Progress"),
      milestone("M1.1", "Complete", "M1"),
      milestone("M1.2", "Complete", "M1", 3),
    ];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1", "M1.1", "M1.2"];
    const map = buildDisplayStatusWithPhaseRollup(ordered, byId, undefined, {
      enabled: true,
    });
    expect(map.M1).toBe(DISPLAY_STATUS_COMPLETE);
    expect(map["M1.1"]).toBe(DISPLAY_STATUS_COMPLETE);
    expect(map["M1.2"]).toBe(DISPLAY_STATUS_COMPLETE);
  });

  it("does not change milestone display when children are done (phase-only rollup)", () => {
    const nodes = [
      phase("M1", "In Progress"),
      milestone("M1.1", "In Progress", "M1"),
      { ...milestone("M1.1.1", "Complete", "M1.1", 4), parent_id: "M1.1" },
    ];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1", "M1.1", "M1.1.1"];
    const map = buildDisplayStatusWithPhaseRollup(ordered, byId, undefined, {
      enabled: true,
    });
    expect(map["M1.1"]).toBe("In Progress");
    expect(map.M1).toBe(DISPLAY_STATUS_COMPLETE);
  });

  it("promotes phase from registry then rollup when subtree is Complete", () => {
    const nodes = [phase("M1", "Not Started"), milestone("M1.1", "Complete", "M1")];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const reg = {
      M1: {
        branch: "feature/rm-x",
        codename: "x",
        node_id: "M1",
        touch_zones: ["a"],
      },
    };
    const ordered = ["M1", "M1.1"];
    const map = buildDisplayStatusWithPhaseRollup(ordered, byId, reg, {
      enabled: true,
    });
    expect(map.M1).toBe(DISPLAY_STATUS_COMPLETE);
  });

  it("returns base map when rollup disabled", () => {
    const nodes = [phase("M1", "In Progress"), milestone("M1.1", "Complete", "M1")];
    const byId: Record<string, RoadmapNode | undefined> = Object.fromEntries(
      nodes.map((n) => [n.id, n]),
    );
    const ordered = ["M1", "M1.1"];
    const map = buildDisplayStatusWithPhaseRollup(ordered, byId, undefined, {
      enabled: false,
    });
    expect(map.M1).toBe("In Progress");
  });
});

describe("phaseRollupDerivedComplete", () => {
  it("is true only for phase with display Complete and persisted not Complete", () => {
    const p = phase("M1", "In Progress");
    expect(phaseRollupDerivedComplete(p, "Complete")).toBe(true);
    expect(phaseRollupDerivedComplete(p, "In Progress")).toBe(false);
    expect(phaseRollupDerivedComplete(milestone("M1.1", "In Progress", "M1"), "Complete")).toBe(
      false,
    );
  });
});
