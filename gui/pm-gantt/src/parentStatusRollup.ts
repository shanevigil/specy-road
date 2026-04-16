import type { RoadmapNode } from "./types";
import { pmDisplayStatus } from "./pmDisplayStatus";

/** Canonical Complete label (matches roadmap schema enum casing). */
export const DISPLAY_STATUS_COMPLETE = "Complete";

/**
 * When unset or truthy, phase rows may show Complete when every descendant is effectively
 * complete (display-only). Set `VITE_SPECY_ROAD_PM_PHASE_ROLLUP=0` at build time to disable.
 */
export function isPhaseStatusRollupEnabled(): boolean {
  try {
    const v = import.meta.env?.VITE_SPECY_ROAD_PM_PHASE_ROLLUP;
    if (v === undefined || v === "") return true;
    const s = String(v).trim().toLowerCase();
    return s !== "0" && s !== "false" && s !== "off" && s !== "no";
  } catch {
    return true;
  }
}

function normLower(s: string | undefined): string {
  return (s || "").trim().toLowerCase();
}

function isTerminalBlocked(base: string): boolean {
  return normLower(base) === "blocked";
}

function isTerminalComplete(base: string): boolean {
  return normLower(base) === "complete";
}

/** Direct children from `parent_id` (outline tree). */
export function childrenIdsByParentId(
  nodes: RoadmapNode[],
): Map<string | null, string[]> {
  const m = new Map<string | null, string[]>();
  for (const n of nodes) {
    const pid =
      n.parent_id === undefined || n.parent_id === null || n.parent_id === ""
        ? null
        : String(n.parent_id);
    const id = n.id;
    if (!m.has(pid)) m.set(pid, []);
    m.get(pid)!.push(id);
  }
  return m;
}

/**
 * Post-order ids: every child before its parent (forest over `parent_id`).
 * Disconnected subtrees (e.g. missing parent id) are still visited.
 */
export function postOrderIdsForForest(
  orderedIds: string[],
  byId: Record<string, RoadmapNode | undefined>,
  childrenByParent: Map<string | null, string[]>,
): string[] {
  const out: string[] = [];
  const visited = new Set<string>();

  function walk(nid: string): void {
    if (visited.has(nid)) return;
    visited.add(nid);
    for (const c of childrenByParent.get(nid) ?? []) {
      walk(c);
    }
    out.push(nid);
  }

  for (const id of orderedIds) {
    const p = byId[id]?.parent_id;
    const root =
      p === undefined ||
      p === null ||
      (typeof p === "string" && p.trim() === "");
    if (root) walk(id);
  }
  for (const id of orderedIds) {
    if (!visited.has(id)) walk(id);
  }
  return out;
}

/**
 * Bottom-up effective display: a node is effectively Complete iff its base is Complete, or
 * (base is not Blocked and every direct child is effectively Complete). Blocked is sticky.
 */
export function computeEffectiveDisplayById(
  orderedPostOrder: string[],
  baseById: Record<string, string>,
  childrenByParent: Map<string | null, string[]>,
): Record<string, string> {
  const eff: Record<string, string> = {};

  for (const nid of orderedPostOrder) {
    const base = baseById[nid] ?? "Not Started";
    if (isTerminalComplete(base)) {
      eff[nid] = DISPLAY_STATUS_COMPLETE;
      continue;
    }
    if (isTerminalBlocked(base)) {
      eff[nid] = base;
      continue;
    }
    const kids = childrenByParent.get(nid);
    if (!kids || kids.length === 0) {
      eff[nid] = base;
      continue;
    }
    const allChildrenComplete = kids.every(
      (c) => normLower(eff[c]) === "complete",
    );
    eff[nid] = allChildrenComplete ? DISPLAY_STATUS_COMPLETE : base;
  }

  return eff;
}

/**
 * Full bottom-up effective status for every node (same `baseById` + `computeEffectiveDisplayById`
 * pipeline as {@link buildDisplayStatusWithPhaseRollup}, but returns `eff` for all ids).
 * Used for "hide complete" filtering. When phase rollup is disabled at build time, returns
 * `baseById` only (no subtree rollup), matching display behavior.
 */
export function computeEffectiveDisplayForAllNodes(
  orderedIds: string[],
  byId: Record<string, RoadmapNode | undefined>,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  opts?: PhaseRollupOptions,
): Record<string, string> {
  const baseById: Record<string, string> = {};
  for (const id of orderedIds) {
    baseById[id] = pmDisplayStatus(byId[id], registryByNode?.[id]);
  }
  const enabled = opts?.enabled ?? isPhaseStatusRollupEnabled();
  if (!enabled) {
    return { ...baseById };
  }
  const nodes = orderedIds
    .map((id) => byId[id])
    .filter((n): n is RoadmapNode => Boolean(n));
  const childrenByParent = childrenIdsByParentId(nodes);
  const post = postOrderIdsForForest(orderedIds, byId, childrenByParent);
  return computeEffectiveDisplayById(post, baseById, childrenByParent);
}

export type PhaseRollupOptions = {
  /** When false, returns `baseById` unchanged for phase rows. */
  enabled?: boolean;
};

/**
 * Per-node display after `pmDisplayStatus`, then phase-only rollup: `type === "phase"` may
 * show Complete when all descendants are effectively Complete (and base is not Blocked).
 */
export function buildDisplayStatusWithPhaseRollup(
  orderedIds: string[],
  byId: Record<string, RoadmapNode | undefined>,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  opts?: PhaseRollupOptions,
): Record<string, string> {
  const enabled = opts?.enabled ?? isPhaseStatusRollupEnabled();
  const baseById: Record<string, string> = {};
  for (const id of orderedIds) {
    baseById[id] = pmDisplayStatus(byId[id], registryByNode?.[id]);
  }
  if (!enabled) return { ...baseById };

  const nodes = orderedIds
    .map((id) => byId[id])
    .filter((n): n is RoadmapNode => Boolean(n));
  const childrenByParent = childrenIdsByParentId(nodes);
  const post = postOrderIdsForForest(orderedIds, byId, childrenByParent);
  const eff = computeEffectiveDisplayById(post, baseById, childrenByParent);

  const out: Record<string, string> = { ...baseById };
  for (const id of orderedIds) {
    const n = byId[id];
    if (n?.type === "phase" && eff[id] === DISPLAY_STATUS_COMPLETE) {
      out[id] = DISPLAY_STATUS_COMPLETE;
    }
  }
  return out;
}

/**
 * True when a phase row shows Complete from subtree rollup while the chunk `status` is not Complete.
 */
export function phaseRollupDerivedComplete(
  node: RoadmapNode | undefined,
  displayAfterRollup: string | undefined,
): boolean {
  if (!node || node.type !== "phase") return false;
  const persisted = normLower((node.status as string) || "");
  if (persisted === "complete") return false;
  return normLower(displayAfterRollup) === "complete";
}
