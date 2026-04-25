import { describe, expect, it } from "vitest";
import {
  ganttBarSemanticFill,
  resolveGanttBarStyle,
  type GitEnrichmentEntry,
} from "./ganttBarSemantic";
import type { RoadmapNode } from "./types";

function stubNode(id: string, status: string): RoadmapNode {
  return {
    id,
    node_key: "00000000-0000-4000-8000-000000000001",
    type: "task",
    title: "t",
    status,
  };
}

const reg = (branch: string) => ({
  N1: { branch, node_id: "N1" },
});

describe("ganttBarSemanticFill", () => {
  it("uses orange for open PR enrichment", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: { kind: "github_pr", title: "x", pr_state: "open", merged: false },
    };
    expect(
      ganttBarSemanticFill(
        "N1",
        "In Progress",
        "In Progress",
        reg("feature/rm-a"),
        {},
        ge,
      ),
    ).toBe("var(--bar-mr-pending)");
  });

  it("uses dark gray for merged PR", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: {
        kind: "github_pr",
        pr_state: "merged",
        merged: true,
      },
    };
    expect(
      ganttBarSemanticFill("N1", "In Progress", "In Progress", {}, {}, ge),
    ).toBe("var(--bar-complete)");
  });

  it("uses red for rejected closed PR", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: {
        kind: "github_pr",
        pr_state: "rejected",
        merged: false,
      },
    };
    expect(
      ganttBarSemanticFill("N1", "In Progress", "In Progress", {}, {}, ge),
    ).toBe("var(--bar-mr-rejected)");
  });

  it("prefers roadmap Blocked over open MR enrichment", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: {
        kind: "github_pr",
        pr_state: "open",
        merged: false,
      },
    };
    expect(
      ganttBarSemanticFill(
        "N1",
        "Blocked",
        "Blocked",
        reg("feature/rm-a"),
        {},
        ge,
      ),
    ).toBe("var(--bar-blocked)");
  });

  it("prefers MR rejected over roadmap Blocked when both apply", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: {
        kind: "github_pr",
        pr_state: "rejected",
        merged: false,
      },
    };
    expect(
      ganttBarSemanticFill(
        "N1",
        "Blocked",
        "Blocked",
        reg("feature/rm-a"),
        {},
        ge,
      ),
    ).toBe("var(--bar-mr-rejected)");
  });

  it("uses green for in progress without MR metadata", () => {
    expect(
      ganttBarSemanticFill("N1", "In Progress", "In Progress", {}, {}, {}),
    ).toBe("var(--bar-in-progress)");
  });

  it("treats legacy github_pr without pr_state as open MR (orange)", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: { kind: "github_pr", title: "legacy", merged: false },
    };
    expect(
      ganttBarSemanticFill("N1", "In Progress", "In Progress", {}, {}, ge),
    ).toBe("var(--bar-mr-pending)");
  });

  it("treats pr_state closed as rejected when unmerged", () => {
    const ge: Record<string, GitEnrichmentEntry> = {
      N1: {
        kind: "github_pr",
        pr_state: "closed",
        merged: false,
      },
    };
    expect(
      ganttBarSemanticFill("N1", "In Progress", "In Progress", {}, {}, ge),
    ).toBe("var(--bar-mr-rejected)");
  });
});

describe("resolveGanttBarStyle", () => {
  it("selected wins over dependency highlight and semantic green", () => {
    const s = resolveGanttBarStyle({
      nodeId: "N1",
      selected: true,
      depHighlight: true,
      displayStatus: "In Progress",
      node: stubNode("N1", "In Progress"),
      registryByNode: reg("feature/rm-a"),
      gitCheckoutById: { N1: true },
      gitEnrichment: {},
    });
    expect(s.fill).toBe("var(--gantt-bar-selected)");
  });

  it("dependency highlight is yellow when not selected", () => {
    const s = resolveGanttBarStyle({
      nodeId: "N1",
      selected: false,
      depHighlight: true,
      displayStatus: "Not Started",
      node: stubNode("N1", "Not Started"),
    });
    expect(s.fill).toBe("var(--gantt-dep-chain)");
  });

  it("gate rows use purple bar when not selected", () => {
    const s = resolveGanttBarStyle({
      nodeId: "N1",
      selected: false,
      depHighlight: false,
      displayStatus: "Not Started",
      node: { ...stubNode("N1", "Not Started"), type: "gate" },
    });
    expect(s.fill).toBe("var(--bar-gate)");
  });

  it("selection wins over gate purple on bar", () => {
    const s = resolveGanttBarStyle({
      nodeId: "N1",
      selected: true,
      depHighlight: false,
      displayStatus: "Not Started",
      node: { ...stubNode("N1", "Not Started"), type: "gate" },
    });
    expect(s.fill).toBe("var(--gantt-bar-selected)");
  });

  it("parent container rows use neutral parent bar when not selected", () => {
    const s = resolveGanttBarStyle({
      nodeId: "P1",
      selected: false,
      depHighlight: false,
      displayStatus: "In Progress",
      isParentNode: true,
      node: stubNode("P1", "In Progress"),
    });
    expect(s.fill).toBe("var(--bar-parent)");
    expect(s.stroke).toBe("var(--bar-parent-stroke)");
  });

  it("selection wins over parent grey on bar", () => {
    const s = resolveGanttBarStyle({
      nodeId: "P1",
      selected: true,
      depHighlight: false,
      displayStatus: "In Progress",
      isParentNode: true,
      node: stubNode("P1", "In Progress"),
    });
    expect(s.fill).toBe("var(--gantt-bar-selected)");
  });

  it("uses thick accent stroke for feature-branch in-progress bar only", () => {
    const thick = resolveGanttBarStyle({
      nodeId: "N1",
      selected: false,
      depHighlight: false,
      displayStatus: "In Progress",
      node: stubNode("N1", "In Progress"),
      registryByNode: reg("feature/rm-a"),
      gitCheckoutById: { N1: true },
      gitEnrichment: {},
    });
    expect(thick.strokeWidth).toBe(2);
    expect(thick.stroke).toBe("var(--accent)");

    const thin = resolveGanttBarStyle({
      nodeId: "N1",
      selected: false,
      depHighlight: false,
      displayStatus: "In Progress",
      node: stubNode("N1", "In Progress"),
      registryByNode: {},
      gitCheckoutById: {},
      gitEnrichment: {},
    });
    expect(thin.strokeWidth).toBe(1);
  });
});
