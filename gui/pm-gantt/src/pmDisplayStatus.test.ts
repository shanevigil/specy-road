import { describe, expect, it } from "vitest";
import {
  pmDisplayStatus,
  pmOutlineDisplayStatus,
  pmPlanningTitleReadOnlyFromRow,
} from "./pmDisplayStatus";
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

describe("pmOutlineDisplayStatus", () => {
  it("shows MR Pending for open github_pr enrichment", () => {
    expect(
      pmOutlineDisplayStatus(
        node("In Progress"),
        { branch: "feature/x", node_id: "M1.2", codename: "x", touch_zones: [] },
        { kind: "github_pr", pr_state: "open", merged: false },
      ),
    ).toBe("MR Pending");
  });

  it("shows MR Merged when API reports merged", () => {
    expect(
      pmOutlineDisplayStatus(node("In Progress"), undefined, {
        kind: "github_pr",
        pr_state: "merged",
        merged: true,
      }),
    ).toBe("MR Merged");
  });

  it("shows MR Rejected for pr_state rejected", () => {
    expect(
      pmOutlineDisplayStatus(node("In Progress"), undefined, {
        kind: "github_pr",
        pr_state: "rejected",
        merged: false,
      }),
    ).toBe("MR Rejected");
  });

  it("shows MR Rejected for closed unmerged GitLab-style payload", () => {
    expect(
      pmOutlineDisplayStatus(node("Not Started"), undefined, {
        kind: "gitlab_mr",
        pr_state: "closed",
        merged: false,
      }),
    ).toBe("MR Rejected");
  });

  it("shows MR Merged for gitlab_mr when merged", () => {
    expect(
      pmOutlineDisplayStatus(node("In Progress"), undefined, {
        kind: "gitlab_mr",
        pr_state: "merged",
        merged: true,
      }),
    ).toBe("MR Merged");
  });

  it("uses displayBaseOverride when provided (phase rollup)", () => {
    expect(
      pmOutlineDisplayStatus(
        node("In Progress"),
        { branch: "feature/x", node_id: "M1.2", codename: "x", touch_zones: [] },
        undefined,
        "Complete",
      ),
    ).toBe("Complete");
  });
});

describe("pmPlanningTitleReadOnlyFromRow", () => {
  it("locks for in-progress display without checkout", () => {
    expect(pmPlanningTitleReadOnlyFromRow(false, "In Progress", "In Progress")).toBe(
      true,
    );
  });

  it("locks for MR Pending outline label", () => {
    expect(
      pmPlanningTitleReadOnlyFromRow(false, "In Progress", "MR Pending"),
    ).toBe(true);
  });

  it("allows editing when MR Rejected and roadmap status is not In Progress", () => {
    expect(
      pmPlanningTitleReadOnlyFromRow(false, "Not Started", "MR Rejected"),
    ).toBe(false);
  });

  it("locks when outline shows MR Merged", () => {
    expect(
      pmPlanningTitleReadOnlyFromRow(false, "In Progress", "MR Merged"),
    ).toBe(true);
  });
});
