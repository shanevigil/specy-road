import { describe, expect, it } from "vitest";
import { buildDisplayStatusWithPhaseRollup } from "./parentStatusRollup";
import type { RoadmapNode } from "./types";

/** Same pipeline as ``App`` ``displayStatusById`` useMemo (wiring parity). */
function buildDisplayStatusById(
  orderedIds: string[],
  byId: Record<string, RoadmapNode>,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
): Record<string, string> {
  return buildDisplayStatusWithPhaseRollup(orderedIds, byId, registryByNode);
}

describe("buildDisplayStatusById (App parity)", () => {
  it("maps every ordered id through pmDisplayStatus with registry row", () => {
    const byId: Record<string, RoadmapNode> = {
      M1: {
        id: "M1",
        node_key: "11111111-1111-1111-1111-111111111111",
        type: "task",
        title: "a",
        status: "Not Started",
      },
      M2: {
        id: "M2",
        node_key: "22222222-2222-2222-2222-222222222222",
        type: "task",
        title: "b",
        status: "Complete",
      },
    };
    const registryByNode = {
      M1: {
        codename: "x",
        node_id: "M1",
        branch: "feature/rm-x",
        touch_zones: ["z"],
      },
    };
    const map = buildDisplayStatusById(["M1", "M2"], byId, registryByNode);
    expect(map.M1).toBe("In Progress");
    expect(map.M2).toBe("Complete");
  });
});
