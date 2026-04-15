import type { RoadmapNode } from "./types";
import {
  isDisplayStatusInProgress,
  showActiveFeatureBranchBar,
} from "./rowMatchesRegisteredBranch";

/** Payload from `git_enrichment[node_id]` for registry rows with a `branch`. */
export type GitEnrichmentEntry = Record<string, unknown> & {
  kind?: string;
  /** Server: `open` | `merged` | `rejected` (GitHub may also send `closed` unmerged). */
  pr_state?: string;
  merged?: boolean;
};

const MR_OPEN_KINDS = new Set(["github_pr", "gitlab_mr"]);

/** Maps enrichment to MR lifecycle flags; legacy rows may omit `pr_state` when the PR is still open. */
function enrichmentPrLifecycle(g: GitEnrichmentEntry | undefined): {
  open: boolean;
  merged: boolean;
  rejected: boolean;
} {
  if (!g) return { open: false, merged: false, rejected: false };
  const kind = (g.kind as string) || "";
  const prState = ((g.pr_state as string) || "").toLowerCase();
  const mergedFlag = Boolean(g.merged);
  if (prState === "merged" || mergedFlag) {
    return { open: false, merged: true, rejected: false };
  }
  if (prState === "rejected" || prState === "closed") {
    return { open: false, merged: false, rejected: true };
  }
  if (prState === "open") {
    return { open: true, merged: false, rejected: false };
  }
  if (MR_OPEN_KINDS.has(kind)) {
    return { open: true, merged: false, rejected: false };
  }
  return { open: false, merged: false, rejected: false };
}

/**
 * Semantic bar fill only (selection and dependency-highlight overrides happen in {@link resolveGanttBarStyle}).
 * Order: merged MR → rejected MR → roadmap Blocked → open MR → active feature-branch green → other status.
 * Rejected MR is evaluated before Blocked so closed-unmerged PRs drive the bar when both apply.
 */
export function ganttBarSemanticFill(
  nodeId: string,
  displayStatus: string | undefined,
  persistedStatus: string | undefined,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitCheckoutById: Record<string, boolean> | undefined,
  gitEnrichment: Record<string, GitEnrichmentEntry> | undefined,
): string {
  const disp = (displayStatus || "").trim().toLowerCase();
  const persisted = (persistedStatus || "").trim().toLowerCase();
  const g = gitEnrichment?.[nodeId];
  const pr = enrichmentPrLifecycle(g);

  if (pr.merged) {
    return "var(--bar-complete)";
  }
  if (pr.rejected) {
    return "var(--bar-mr-rejected)";
  }
  if (persisted === "blocked" || disp === "blocked") {
    return "var(--bar-blocked)";
  }
  if (pr.open) {
    return "var(--bar-mr-pending)";
  }
  if (
    showActiveFeatureBranchBar(
      nodeId,
      displayStatus,
      registryByNode,
      gitCheckoutById,
    )
  ) {
    return "var(--bar-in-progress)";
  }
  if (disp === "complete" || persisted === "complete") {
    return "var(--bar-complete)";
  }
  if (disp === "not started" || !displayStatus) {
    return "var(--bar-not-started)";
  }
  if (isDisplayStatusInProgress(displayStatus)) {
    return "var(--bar-in-progress)";
  }
  return "var(--bar-not-started)";
}

export type GanttBarResolveContext = {
  nodeId: string;
  selected: boolean;
  depHighlight: boolean;
  displayStatus: string | undefined;
  node: RoadmapNode | undefined;
  registryByNode?: Record<string, Record<string, unknown>>;
  gitCheckoutById?: Record<string, boolean>;
  gitEnrichment?: Record<string, GitEnrichmentEntry>;
};

/**
 * Final bar paint: selection → blue; dependency row → yellow; else semantic fill.
 * Thicker accent stroke applies only when the semantic fill is feature-branch green (not plain “In Progress” green).
 */
export function resolveGanttBarStyle(ctx: GanttBarResolveContext): {
  fill: string;
  stroke: string;
  strokeWidth: number;
} {
  const persisted = ctx.node?.status as string | undefined;
  const semantic = ganttBarSemanticFill(
    ctx.nodeId,
    ctx.displayStatus,
    persisted,
    ctx.registryByNode,
    ctx.gitCheckoutById,
    ctx.gitEnrichment,
  );

  if (ctx.selected) {
    return {
      fill: "var(--gantt-bar-selected)",
      stroke: "rgba(0,0,0,0.15)",
      strokeWidth: 1,
    };
  }
  if (ctx.depHighlight) {
    return {
      fill: "var(--gantt-dep-chain)",
      stroke: "rgba(0,0,0,0.15)",
      strokeWidth: 1,
    };
  }
  const thickGreen =
    semantic === "var(--bar-in-progress)" &&
    showActiveFeatureBranchBar(
      ctx.nodeId,
      ctx.displayStatus,
      ctx.registryByNode,
      ctx.gitCheckoutById,
    );
  const selStroke = thickGreen ? "var(--accent)" : "rgba(0,0,0,0.15)";
  const sw = thickGreen ? 2 : 1;
  return {
    fill: semantic,
    stroke: selStroke,
    strokeWidth: sw,
  };
}
