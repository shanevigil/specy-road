import { compareRoadmapIds } from "./roadmapIdSort";
import type { RoadmapNode, RoadmapResponse } from "./types";

/**
 * Apply optimistic outline mutations to a server-truth ``RoadmapResponse``
 * so the UI can render the post-mutation state immediately, before the
 * server's ack arrives.
 *
 * Each op is applied in registration order to a freshly cloned snapshot.
 * The result has the same shape as ``RoadmapResponse`` so OutlineTable
 * and GanttPane can render it interchangeably with server-truth data.
 *
 * Scope: outline-affecting ops only. Status / title / planning_dir
 * edits don't change tree structure and don't need optimistic transform.
 */

export type OptimisticOp =
  | {
      kind: "reorder";
      parentId: string | null;
      orderedChildIds: string[];
    }
  | {
      kind: "move";
      nodeKey: string;
      newParentId: string | null;
      newIndex: number;
    }
  | { kind: "indent"; nodeId: string }
  | { kind: "outdent"; nodeId: string }
  | { kind: "dep"; nodeId: string; explicitNodeKeys: string[] }
  | {
      kind: "add";
      placeholder: RoadmapNode;
      referenceNodeId: string;
      position: "above" | "below";
    }
  | { kind: "delete"; nodeId: string };

/** Display ids touched by ``op``; OutlineTable applies the pending pulse class to these. */
export function affectedIds(op: OptimisticOp): string[] {
  switch (op.kind) {
    case "reorder":
      return [...op.orderedChildIds];
    case "move":
      return []; // we may not yet know the new display id; handled via node_key resolution
    case "indent":
    case "outdent":
    case "dep":
    case "delete":
      return [op.nodeId];
    case "add":
      return [op.placeholder.id];
  }
}

function parentKey(node: RoadmapNode | undefined): string | null {
  const p = node?.parent_id;
  return p == null || p === "" ? null : p;
}

function cloneNodes(nodes: RoadmapNode[]): RoadmapNode[] {
  return nodes.map((n) => ({ ...n, dependencies: [...(n.dependencies ?? [])] }));
}

function indexById(nodes: RoadmapNode[]): Map<string, number> {
  const m = new Map<string, number>();
  for (let i = 0; i < nodes.length; i++) m.set(nodes[i].id, i);
  return m;
}

function siblingsOf(
  nodes: RoadmapNode[],
  parentId: string | null,
): { id: string; sibling_order: number; idx: number }[] {
  const out: { id: string; sibling_order: number; idx: number }[] = [];
  for (let i = 0; i < nodes.length; i++) {
    if (parentKey(nodes[i]) === parentId) {
      out.push({
        id: nodes[i].id,
        sibling_order: Number(nodes[i].sibling_order ?? 0),
        idx: i,
      });
    }
  }
  out.sort((a, b) => {
    if (a.sibling_order !== b.sibling_order) {
      return a.sibling_order - b.sibling_order;
    }
    return compareRoadmapIds(a.id, b.id);
  });
  return out;
}

/** Renumber a parent's children to ``0..n-1`` in the given id order. */
function setSiblingOrder(
  nodes: RoadmapNode[],
  parentId: string | null,
  orderedIds: string[],
): void {
  const idx = indexById(nodes);
  let n = 0;
  for (const id of orderedIds) {
    const i = idx.get(id);
    if (i == null) continue;
    nodes[i] = { ...nodes[i], sibling_order: n++ };
  }
  // Anything else under the same parent (defensive) keeps its order
  // appended after the explicitly-specified ids.
  for (const sib of siblingsOf(nodes, parentId)) {
    if (!orderedIds.includes(sib.id)) {
      nodes[sib.idx] = { ...nodes[sib.idx], sibling_order: n++ };
    }
  }
}

function applyReorder(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "reorder" }>,
): RoadmapNode[] {
  setSiblingOrder(nodes, op.parentId, op.orderedChildIds);
  return nodes;
}

function applyMove(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "move" }>,
): RoadmapNode[] {
  const movedIdx = nodes.findIndex((n) => n.node_key === op.nodeKey);
  if (movedIdx < 0) return nodes;
  const moved = nodes[movedIdx];
  // Update parent_id.
  nodes[movedIdx] = { ...moved, parent_id: op.newParentId };
  // Recompute the new parent's children order, splicing the moved node in.
  const newSibsBefore = siblingsOf(nodes, op.newParentId)
    .filter((s) => s.id !== moved.id)
    .map((s) => s.id);
  const insertAt = Math.max(0, Math.min(op.newIndex, newSibsBefore.length));
  const newOrder = [
    ...newSibsBefore.slice(0, insertAt),
    moved.id,
    ...newSibsBefore.slice(insertAt),
  ];
  setSiblingOrder(nodes, op.newParentId, newOrder);
  return nodes;
}

function applyIndent(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "indent" }>,
): RoadmapNode[] {
  // Approximate the server's ``apply_indent``: move the node under its
  // immediately-previous sibling, appended as the last child. Server is
  // the source of truth — if the indent is illegal it'll reject and
  // the optimistic op rolls back.
  const idx = nodes.findIndex((n) => n.id === op.nodeId);
  if (idx < 0) return nodes;
  const node = nodes[idx];
  const sibs = siblingsOf(nodes, parentKey(node)).map((s) => s.id);
  const pos = sibs.indexOf(op.nodeId);
  if (pos <= 0) return nodes;
  const newParentId = sibs[pos - 1];
  return applyMove(nodes, {
    kind: "move",
    nodeKey: node.node_key,
    newParentId,
    newIndex: siblingsOf(nodes, newParentId).length,
  });
}

function applyOutdent(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "outdent" }>,
): RoadmapNode[] {
  // Approximate ``apply_outdent``: move the node up to its
  // grandparent, immediately after the current parent.
  const idx = nodes.findIndex((n) => n.id === op.nodeId);
  if (idx < 0) return nodes;
  const node = nodes[idx];
  const parentId = parentKey(node);
  if (parentId == null) return nodes; // root nodes can't outdent
  const parentIdx = nodes.findIndex((n) => n.id === parentId);
  if (parentIdx < 0) return nodes;
  const grandParent = parentKey(nodes[parentIdx]);
  const grandSibs = siblingsOf(nodes, grandParent).map((s) => s.id);
  const insertAfter = grandSibs.indexOf(parentId);
  return applyMove(nodes, {
    kind: "move",
    nodeKey: node.node_key,
    newParentId: grandParent,
    newIndex: insertAfter < 0 ? grandSibs.length : insertAfter + 1,
  });
}

function applyDep(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "dep" }>,
): RoadmapNode[] {
  const idx = nodes.findIndex((n) => n.id === op.nodeId);
  if (idx < 0) return nodes;
  nodes[idx] = { ...nodes[idx], dependencies: [...op.explicitNodeKeys] };
  return nodes;
}

function applyAdd(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "add" }>,
): RoadmapNode[] {
  const refIdx = nodes.findIndex((n) => n.id === op.referenceNodeId);
  if (refIdx < 0) return nodes;
  const ref = nodes[refIdx];
  const placeholder: RoadmapNode = {
    ...op.placeholder,
    parent_id: parentKey(ref),
  };
  // Insert placeholder, then renumber the parent's children so the new
  // row sits at the correct slot relative to ref.
  const result = [...nodes, placeholder];
  const sibs = siblingsOf(result, parentKey(ref)).map((s) => s.id);
  // Remove placeholder from its initial trailing position.
  const without = sibs.filter((id) => id !== placeholder.id);
  const refPos = without.indexOf(op.referenceNodeId);
  const insertAt = op.position === "above" ? refPos : refPos + 1;
  const newOrder = [
    ...without.slice(0, insertAt),
    placeholder.id,
    ...without.slice(insertAt),
  ];
  setSiblingOrder(result, parentKey(ref), newOrder);
  return result;
}

function applyDelete(
  nodes: RoadmapNode[],
  op: Extract<OptimisticOp, { kind: "delete" }>,
): RoadmapNode[] {
  const subtree = new Set<string>();
  const collect = (id: string) => {
    subtree.add(id);
    for (const n of nodes) {
      if (n.parent_id === id) collect(n.id);
    }
  };
  collect(op.nodeId);
  return nodes.filter((n) => !subtree.has(n.id));
}

/** Top-down DFS traversal honoring sibling_order; returns ``[node, depth]`` rows. */
function orderedTreeRows(
  nodes: RoadmapNode[],
): { node: RoadmapNode; depth: number }[] {
  const childrenByParent = new Map<string | null, RoadmapNode[]>();
  for (const n of nodes) {
    const p = parentKey(n);
    const arr = childrenByParent.get(p) ?? [];
    arr.push(n);
    childrenByParent.set(p, arr);
  }
  for (const arr of childrenByParent.values()) {
    arr.sort((a, b) => {
      const sa = Number(a.sibling_order ?? 0);
      const sb = Number(b.sibling_order ?? 0);
      if (sa !== sb) return sa - sb;
      return compareRoadmapIds(a.id, b.id);
    });
  }
  const out: { node: RoadmapNode; depth: number }[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const n of childrenByParent.get(parent) ?? []) {
      out.push({ node: n, depth });
      walk(n.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

/**
 * Recompute ``ordered_ids``, ``tree``, and ``row_depths`` from a node
 * list after one or more optimistic ops have been applied.
 *
 * The other ``RoadmapResponse`` fields (``edges``, ``dependency_depths``,
 * ``pr_hints``, ``registry``, etc.) are left untouched — they're either
 * derived from the registry (server-truth, unrelated to the local
 * tree shape) or re-fetched by ``loadSnapshot`` after the mutation
 * resolves.
 */
function rebuildOrdering(base: RoadmapResponse, nodes: RoadmapNode[]) {
  const rows = orderedTreeRows(nodes);
  return {
    ...base,
    nodes,
    tree: rows.map((r, i) => ({
      id: r.node.id,
      outline_depth: r.depth,
      row_index: i,
    })),
    ordered_ids: rows.map((r) => r.node.id),
    row_depths: rows.map((r) => r.depth),
  };
}

/** Apply ``ops`` (in order) to ``base`` and return the optimistic response. */
export function applyOptimistic(
  base: RoadmapResponse,
  ops: readonly OptimisticOp[],
): RoadmapResponse {
  if (ops.length === 0) return base;
  let nodes = cloneNodes(base.nodes);
  for (const op of ops) {
    switch (op.kind) {
      case "reorder":
        nodes = applyReorder(nodes, op);
        break;
      case "move":
        nodes = applyMove(nodes, op);
        break;
      case "indent":
        nodes = applyIndent(nodes, op);
        break;
      case "outdent":
        nodes = applyOutdent(nodes, op);
        break;
      case "dep":
        nodes = applyDep(nodes, op);
        break;
      case "add":
        nodes = applyAdd(nodes, op);
        break;
      case "delete":
        nodes = applyDelete(nodes, op);
        break;
    }
  }
  return rebuildOrdering(base, nodes);
}

/** Build a placeholder ``RoadmapNode`` for the optimistic add-task op. */
export function buildAddPlaceholder(opts: {
  token: string;
  title: string;
  type: string;
  parentId: string | null;
}): RoadmapNode {
  return {
    id: `__pending__:${opts.token}`,
    node_key: `pending-${opts.token}`,
    type: opts.type,
    title: opts.title,
    status: "Not Started",
    parent_id: opts.parentId,
    dependencies: [],
    sibling_order: 0,
  };
}

/** Display id pattern for an add-task placeholder; OutlineTable uses this for special-casing. */
export function isPendingPlaceholderId(id: string): boolean {
  return id.startsWith("__pending__:");
}
