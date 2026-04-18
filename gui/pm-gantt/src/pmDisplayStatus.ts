import type { RoadmapNode } from "./types";
import { isDisplayStatusInProgress } from "./rowMatchesRegisteredBranch";

const NO_PROMOTE_LOWER = new Set(["complete", "blocked", "in progress"]);

/**
 * Label for the outline Status column and Gantt bar colors (display-only; does not persist).
 *
 * Leaves Complete, Blocked, and In Progress unchanged. For other values (including
 * missing/empty, treated as Not Started), a non-empty `registryEntry.branch` yields In Progress
 * so the PM view matches active `roadmap/registry.yaml` rows when chunk files lag.
 */
export function pmDisplayStatus(
  node: RoadmapNode | undefined,
  registryEntry: Record<string, unknown> | undefined,
): string {
  const raw = (node?.status as string)?.trim() || "Not Started";
  const lower = raw.toLowerCase();
  if (NO_PROMOTE_LOWER.has(lower)) {
    return raw;
  }
  const br = registryEntry?.branch;
  if (typeof br === "string" && br.trim().length > 0) {
    return "In Progress";
  }
  return raw;
}

/**
 * Outline Status column only: MR labels on top of {@link pmDisplayStatus}. Not persisted.
 * Bar colors use `pmDisplayStatus` + `git_enrichment` in the Gantt layer, not this outline string.
 */
export function pmOutlineDisplayStatus(
  node: RoadmapNode | undefined,
  registryEntry: Record<string, unknown> | undefined,
  gitEnrichmentEntry: Record<string, unknown> | undefined,
  /** When set (e.g. phase subtree rollup), used instead of {@link pmDisplayStatus}. */
  displayBaseOverride?: string,
): string {
  const base =
    displayBaseOverride !== undefined
      ? displayBaseOverride
      : pmDisplayStatus(node, registryEntry);
  const g = gitEnrichmentEntry;
  if (!g) return base;
  const kind = String(g.kind || "");
  const isPrMr = kind === "github_pr" || kind === "gitlab_mr";
  if (!isPrMr) return base;
  const ps = String(g.pr_state || "").toLowerCase();
  const mergedFlag = Boolean(g.merged);
  if (ps === "merged" || mergedFlag) {
    return "MR Merged";
  }
  // closed + unmerged (e.g. some GitLab payloads) — merged is handled above
  if (ps === "rejected" || (ps === "closed" && !mergedFlag)) {
    return "MR Rejected";
  }
  if (ps === "open" || ps === "") {
    return "MR Pending";
  }
  return base;
}

/**
 * When the outline title and planning sheet should be read-only in the PM UI.
 * MR Rejected is intentionally editable so the PM can fix roadmap state after a bad merge attempt.
 */
export function pmPlanningTitleReadOnlyFromRow(
  gitCheckoutMatchesRow: boolean,
  displayStatusBase: string | undefined,
  outlineStatus: string | undefined,
): boolean {
  if (gitCheckoutMatchesRow) return true;
  const ol = (outlineStatus || "").trim().toLowerCase();
  if (ol === "mr pending" || ol === "mr merged") return true;
  return isDisplayStatusInProgress(displayStatusBase);
}
