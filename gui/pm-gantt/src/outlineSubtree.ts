import type { RoadmapNode } from "./types";

function parentKey(n: RoadmapNode | undefined): string | null {
  const p = n?.parent_id;
  if (p === undefined || p === null || p === "") return null;
  return p;
}

/**
 * True if `id` is `rootId` or a descendant of `rootId` in the roadmap tree
 * (walks `parent_id` upward). Works when the outline list is filtered (e.g. hide
 * complete): unlike depth-based slices, gaps from hidden ancestors do not break
 * inclusion of deeper visible rows.
 */
export function isVisibleIdUnderRoot(
  nodesById: Record<string, RoadmapNode>,
  id: string,
  rootId: string,
): boolean {
  if (id === rootId) return true;
  const seen = new Set<string>();
  let cur: string | null = parentKey(nodesById[id]);
  while (cur) {
    if (cur === rootId) return true;
    if (seen.has(cur)) return false;
    seen.add(cur);
    cur = parentKey(nodesById[cur]);
  }
  return false;
}

/**
 * Visible rows that belong to the subtree rooted at `rootId`, in outline order.
 * Use for drag preview / hiding source rows when the list may omit complete tasks.
 */
export function visibleDragSubtreeIds(
  visibleOrderedIds: string[],
  nodesById: Record<string, RoadmapNode>,
  rootId: string,
): string[] {
  if (!visibleOrderedIds.includes(rootId)) return [];
  return visibleOrderedIds.filter((id) =>
    isVisibleIdUnderRoot(nodesById, id, rootId),
  );
}

/**
 * Contiguous preorder subtree in a flat outline: ids from `rootId` through the
 * last descendant before the next sibling (or uncle) at the same depth.
 * Correct only when `orderedIds` / `rowDepths` are an unfiltered preorder (no
 * rows omitted). Prefer {@link visibleDragSubtreeIds} when the list can skip nodes.
 */
export function contiguousSubtreeIds(
  orderedIds: string[],
  rowDepths: number[],
  rootId: string,
): string[] {
  const start = orderedIds.indexOf(rootId);
  if (start < 0) return [];
  const baseDepth = rowDepths[start] ?? 0;
  const out: string[] = [orderedIds[start]!];
  for (let j = start + 1; j < orderedIds.length; j++) {
    const d = rowDepths[j] ?? 0;
    if (d <= baseDepth) break;
    out.push(orderedIds[j]!);
  }
  return out;
}
