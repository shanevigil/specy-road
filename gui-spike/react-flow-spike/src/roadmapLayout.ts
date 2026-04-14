import type { Edge, Node } from "@xyflow/react";
import { MarkerType } from "@xyflow/react";

export type RoadmapNode = {
  id: string;
  title?: string;
  status?: string;
  dependencies?: string[];
  type?: string;
};

export type MergedRoadmap = {
  version?: number;
  nodes: RoadmapNode[];
};

const STATUS_COLORS: Record<string, string> = {
  "not started": "#b0b0b0",
  "in progress": "#1976d2",
  blocked: "#d32f2f",
  complete: "#424242",
  cancelled: "#757575",
};

function normalizeStatus(s: string | undefined): string {
  return (s ?? "not started").trim().toLowerCase();
}

/** Same recursive depth idea as specy_road/bundled_scripts/roadmap_layout.py `compute_depths`. */
export function computeDepths(nodes: RoadmapNode[]): Map<string, number> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const memo = new Map<string, number>();

  function depth(nid: string): number {
    const hit = memo.get(nid);
    if (hit !== undefined) return hit;
    const n = byId.get(nid);
    const deps = n?.dependencies?.filter((d) => byId.has(d)) ?? [];
    if (deps.length === 0) {
      memo.set(nid, 0);
      return 0;
    }
    const d = 1 + Math.max(...deps.map(depth));
    memo.set(nid, d);
    return d;
  }

  for (const n of nodes) depth(n.id);
  return memo;
}

const COL_W = 280;
const ROW_H = 72;

export function roadmapToFlowElements(roadmap: MergedRoadmap): {
  nodes: Node[];
  edges: Edge[];
} {
  const { nodes: raw } = roadmap;
  const depths = computeDepths(raw);
  const byDepth = new Map<number, RoadmapNode[]>();
  for (const n of raw) {
    const d = depths.get(n.id) ?? 0;
    const list = byDepth.get(d) ?? [];
    list.push(n);
    byDepth.set(d, list);
  }
  for (const [, list] of byDepth) {
    list.sort((a, b) => a.id.localeCompare(b.id));
  }
  const depthKeys = [...byDepth.keys()].sort((a, b) => a - b);

  const flowNodes: Node[] = [];
  for (const d of depthKeys) {
    const column = byDepth.get(d) ?? [];
    column.forEach((n, row) => {
      const st = normalizeStatus(n.status);
      const border = STATUS_COLORS[st] ?? STATUS_COLORS["not started"];
      flowNodes.push({
        id: n.id,
        position: { x: d * COL_W, y: row * ROW_H },
        data: {
          label: `${n.id}\n${(n.title ?? "").slice(0, 48)}${(n.title?.length ?? 0) > 48 ? "…" : ""}`,
        },
        style: {
          width: COL_W - 24,
          padding: 8,
          fontSize: 12,
          textAlign: "left" as const,
          border: `2px solid ${border}`,
          borderRadius: 6,
          background: "#fafafa",
        },
      });
    });
  }

  const flowEdges: Edge[] = [];
  for (const n of raw) {
    for (const dep of n.dependencies ?? []) {
      if (!raw.some((x) => x.id === dep)) continue;
      flowEdges.push({
        id: `${dep}->${n.id}`,
        source: dep,
        target: n.id,
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
        style: { stroke: "#555", strokeWidth: 1.5 },
      });
    }
  }

  return { nodes: flowNodes, edges: flowEdges };
}
