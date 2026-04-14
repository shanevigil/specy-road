import type { RoadmapNode } from "./types";

const NO_PROMOTE_LOWER = new Set([
  "complete",
  "blocked",
  "cancelled",
  "in progress",
]);

/**
 * Label for the outline Status column and Gantt bar colors (display-only; does not persist).
 *
 * Leaves Complete, Blocked, Cancelled, and In Progress unchanged. For other values (including
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
