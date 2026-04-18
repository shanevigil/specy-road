import { describe, expect, it } from "vitest";
import { ROADMAP_NODE_STATUS_ORDERED } from "./roadmapNodeStatuses";

const SCHEMA_STATUSES = new Set([
  "Not Started",
  "In Progress",
  "Complete",
  "Blocked",
]);

describe("ROADMAP_NODE_STATUS_ORDERED", () => {
  it("matches roadmap.schema.json status enum", () => {
    expect(ROADMAP_NODE_STATUS_ORDERED).toHaveLength(4);
    for (const s of ROADMAP_NODE_STATUS_ORDERED) {
      expect(SCHEMA_STATUSES.has(s)).toBe(true);
    }
    expect(new Set(ROADMAP_NODE_STATUS_ORDERED)).toEqual(SCHEMA_STATUSES);
  });
});
