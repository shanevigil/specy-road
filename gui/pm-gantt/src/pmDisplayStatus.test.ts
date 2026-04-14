import { describe, expect, it } from "vitest";
import { pmDisplayStatus } from "./pmDisplayStatus";
import type { RoadmapNode } from "./types";

function node(status: string | undefined): RoadmapNode {
  return {
    id: "M1.2",
    node_key: "00000000-0000-0000-0000-000000000001",
    type: "task",
    title: "T",
    status,
  };
}

describe("pmDisplayStatus", () => {
  it("promotes Not Started to In Progress when registry has a branch", () => {
    expect(
      pmDisplayStatus(node("Not Started"), {
        branch: "feature/rm-foo",
        codename: "foo",
        node_id: "M1.2",
        touch_zones: ["a"],
      }),
    ).toBe("In Progress");
  });

  it("keeps Complete even when registry still lists a branch", () => {
    expect(
      pmDisplayStatus(node("Complete"), {
        branch: "feature/rm-foo",
        codename: "foo",
        node_id: "M1.2",
        touch_zones: ["a"],
      }),
    ).toBe("Complete");
  });

  it("keeps In Progress without registry", () => {
    expect(pmDisplayStatus(node("In Progress"), undefined)).toBe("In Progress");
  });

  it("keeps Not Started when registry has no branch", () => {
    expect(
      pmDisplayStatus(node("Not Started"), {
        codename: "foo",
        node_id: "M1.2",
        touch_zones: ["a"],
      } as Record<string, unknown>),
    ).toBe("Not Started");
  });

  it("treats missing status like Not Started and promotes with branch", () => {
    expect(
      pmDisplayStatus({ ...node(undefined), status: undefined }, {
        branch: "feature/rm-x",
        codename: "x",
        node_id: "M1.2",
        touch_zones: ["z"],
      }),
    ).toBe("In Progress");
  });

  it("does not promote on whitespace-only branch", () => {
    expect(
      pmDisplayStatus(node("Not Started"), {
        branch: "   ",
        codename: "foo",
        node_id: "M1.2",
        touch_zones: ["a"],
      }),
    ).toBe("Not Started");
  });
});
