import type { RoadmapResponse } from "./types";

const API = "/api";

export async function fetchRoadmap(): Promise<RoadmapResponse> {
  const r = await fetch(`${API}/roadmap`);
  if (!r.ok) throw new Error(`roadmap: ${r.status}`);
  return r.json() as Promise<RoadmapResponse>;
}

export async function patchNode(
  nodeId: string,
  pairs: { key: string; value: string }[],
): Promise<void> {
  const r = await fetch(`${API}/nodes/${encodeURIComponent(nodeId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pairs }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function reorderOutline(
  parentId: string | null,
  orderedChildIds: string[],
): Promise<void> {
  const r = await fetch(`${API}/outline/reorder`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parent_id: parentId,
      ordered_child_ids: orderedChildIds,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function indentNode(nodeId: string): Promise<void> {
  const r = await fetch(`${API}/nodes/${encodeURIComponent(nodeId)}/indent`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function outdentNode(nodeId: string): Promise<void> {
  const r = await fetch(`${API}/nodes/${encodeURIComponent(nodeId)}/outdent`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function addNode(
  referenceNodeId: string,
  position: "above" | "below",
  title: string,
  type: string,
): Promise<string> {
  const r = await fetch(`${API}/nodes/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reference_node_id: referenceNodeId,
      position,
      title,
      type,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  const j = (await r.json()) as { id: string };
  return j.id;
}

export async function fetchPlanningArtifacts(nodeId: string) {
  const r = await fetch(
    `${API}/planning/${encodeURIComponent(nodeId)}/artifacts`,
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ planning_dir: string | null; files: { role: string; path: string; exists: boolean }[] }>;
}

export async function fetchPlanningFile(path: string) {
  const r = await fetch(
    `${API}/planning/file?${new URLSearchParams({ path })}`,
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ path: string; content: string }>;
}

export async function savePlanningFile(path: string, content: string) {
  const r = await fetch(
    `${API}/planning/file?${new URLSearchParams({ path })}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
  if (!r.ok) throw new Error(await r.text());
}

export async function getSettings() {
  const r = await fetch(`${API}/settings`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Record<string, unknown>>;
}

export async function putSettings(settings: Record<string, unknown>) {
  const r = await fetch(`${API}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings }),
  });
  if (!r.ok) throw new Error(await r.text());
}
