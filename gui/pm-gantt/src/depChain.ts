import type { RoadmapNode } from "./types";

/**
 * Union of ``dependencies`` on this node and on every ancestor along ``parent_id``
 * (same rule as Python ``effective_dependency_keys`` / inherited deps on the server).
 */
export function effectiveDependencyKeysForNode(
  n: RoadmapNode,
  byId: Record<string, RoadmapNode>,
): Set<string> {
  const keys = new Set<string>();
  let cur: RoadmapNode | undefined = n;
  while (cur) {
    for (const k of (cur.dependencies ?? []) as string[]) {
      keys.add(k);
    }
    const pid: string | null | undefined = cur.parent_id;
    if (!pid) break;
    const next: RoadmapNode | undefined = byId[pid];
    cur = next;
  }
  return keys;
}

/**
 * Every **preceding** dependency of the selection: transitive closure using
 * **effective** deps (explicit + inherited from ancestors) at each step.
 * Independent of whether dashed “inherited” edges are drawn on the chart.
 */
export function transitiveEffectivePrereqIds(
  selectedId: string,
  byId: Record<string, RoadmapNode>,
  keyToDisplayId: Record<string, string>,
): Set<string> {
  const out = new Set<string>();
  const expanded = new Set<string>();
  const queue: string[] = [selectedId];

  while (queue.length) {
    const id = queue.shift()!;
    if (expanded.has(id)) continue;
    expanded.add(id);
    const n = byId[id];
    if (!n) continue;
    for (const k of effectiveDependencyKeysForNode(n, byId)) {
      const did = keyToDisplayId[k] ?? k;
      if (!did || !byId[did]) continue;
      out.add(did);
      queue.push(did);
    }
  }
  out.delete(selectedId);
  return out;
}
