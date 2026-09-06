import {
  clampRectToViewport,
  getDefaultEditModalRect,
  type ModalRect,
} from "./modalRect";
import type { RoadmapNode } from "./types";

const SPAWN_DX = 28;
const SPAWN_DY = 28;

/**
 * The Brainstorm window's id in the open-window stack.
 *
 * Every other window in that stack is a roadmap node id, so this needs a shape
 * a node id can never take. Sharing the stack is what gives Brainstorm the same
 * focus order, z-order, minimize dock and Escape handling as a task window.
 */
export const BRAINSTORM_WINDOW_ID = "@brainstorm";

/** True for a window that is not a roadmap node, so has no place in the graph. */
export function isGraphWindow(id: string): boolean {
  return !id.startsWith("@");
}

/** Offset a new dialog from the anchor rect so it is visibly stacked. */
export function computeSpawnRect(
  anchor: ModalRect | undefined,
  minTop: number,
): ModalRect {
  if (!anchor) {
    return getDefaultEditModalRect({ minTop });
  }
  return clampRectToViewport(
    {
      left: anchor.left + SPAWN_DX,
      top: anchor.top + SPAWN_DY,
      width: anchor.width,
      height: anchor.height,
    },
    { minTop },
  );
}

/**
 * Topological order among open ids: prerequisites to the left of dependents.
 * Tie-break by outline index. Unresolved cycles: remaining ids in outline order.
 */
export function sortOpenIdsByDependencyOrder(
  openIds: string[],
  nodesById: Record<string, RoadmapNode>,
  orderedIds: string[],
): string[] {
  const open = new Set(openIds);
  const indexOf = new Map<string, number>();
  orderedIds.forEach((id, i) => indexOf.set(id, i));
  const keyToId = new Map<string, string>();
  for (const id of openIds) {
    const nk = nodesById[id]?.node_key;
    if (nk) keyToId.set(nk, id);
  }

  const indegree = new Map<string, number>();
  const adj = new Map<string, string[]>();
  for (const id of openIds) {
    indegree.set(id, 0);
    adj.set(id, []);
  }

  for (const id of openIds) {
    const deps = nodesById[id]?.dependencies ?? [];
    for (const k of deps) {
      const pred = keyToId.get(k);
      if (!pred || !open.has(pred) || pred === id) continue;
      adj.get(pred)!.push(id);
      indegree.set(id, (indegree.get(id) ?? 0) + 1);
    }
  }

  const byOutline = (a: string, b: string) =>
    (indexOf.get(a) ?? 0) - (indexOf.get(b) ?? 0);

  const queue = openIds
    .filter((id) => indegree.get(id) === 0)
    .sort(byOutline);
  const out: string[] = [];

  while (queue.length) {
    const u = queue.shift()!;
    out.push(u);
    for (const v of adj.get(u) ?? []) {
      indegree.set(v, (indegree.get(v) ?? 0) - 1);
      if (indegree.get(v) === 0) {
        queue.push(v);
        queue.sort(byOutline);
      }
    }
  }

  if (out.length < openIds.length) {
    const rest = openIds.filter((id) => !out.includes(id)).sort(byOutline);
    return [...out, ...rest];
  }
  return out;
}

/**
 * Tile order for a stack that may hold windows outside the graph.
 *
 * Dependency order only means something for nodes, so the non-graph windows
 * are not sorted into it — they keep their stack order and sit to the right,
 * where a reader is not invited to read them as a step in the chain.
 */
export function orderWindowsForTile(
  openIds: string[],
  nodesById: Record<string, RoadmapNode>,
  orderedIds: string[],
): string[] {
  const graph = openIds.filter(isGraphWindow);
  const others = openIds.filter((id) => !isGraphWindow(id));
  return [
    ...sortOpenIdsByDependencyOrder(graph, nodesById, orderedIds),
    ...others,
  ];
}

/** Horizontal tiles across the viewport, left to right (may use space above the app header). */
export function computeTileRects(orderedNodeIds: string[]): Record<string, ModalRect> {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const margin = 8;
  const gap = 6;
  const top = margin;
  const n = orderedNodeIds.length;
  if (n === 0) return {};
  const availW = vw - 2 * margin;
  const availH = vh - top - margin;
  const colW = (availW - gap * (n - 1)) / n;
  const out: Record<string, ModalRect> = {};
  orderedNodeIds.forEach((id, i) => {
    out[id] = clampRectToViewport(
      {
        left: margin + i * (colW + gap),
        top,
        width: colW,
        height: availH,
      },
      { minTop: 0 },
    );
  });
  return out;
}
