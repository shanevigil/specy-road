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

export async function moveOutline(
  nodeKey: string,
  newParentId: string | null,
  newIndex: number,
): Promise<void> {
  const r = await fetch(`${API}/outline/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      node_key: nodeKey,
      new_parent_id: newParentId,
      new_index: newIndex,
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

export async function scaffoldPlanning(
  nodeId: string,
  opts?: { planning_dir?: string | null; force?: boolean },
) {
  const r = await fetch(
    `${API}/planning/${encodeURIComponent(nodeId)}/scaffold`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        planning_dir: opts?.planning_dir ?? null,
        force: opts?.force ?? false,
      }),
    },
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    planning_dir: string;
    written: string[];
  }>;
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

export async function scaffoldConstitution(force = false): Promise<{
  written: string[];
  skipped_existing: string[];
}> {
  const r = await fetch(`${API}/constitution/scaffold`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  const raw = (await r.json().catch(() => ({}))) as {
    detail?: unknown;
    written?: string[];
    skipped_existing?: string[];
  };
  if (!r.ok) {
    const d = raw.detail;
    let msg: string;
    if (typeof d === "string") msg = d;
    else if (d != null && typeof d === "object" && "message" in d)
      msg = String((d as { message?: string }).message);
    else msg = JSON.stringify(raw);
    throw new Error(msg);
  }
  return {
    written: raw.written ?? [],
    skipped_existing: raw.skipped_existing ?? [],
  };
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

export async function testLlmSettings(
  llm: Record<string, string>,
): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${API}/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ llm }),
  });
  const raw = (await r.json()) as {
    ok?: boolean;
    message?: string;
    detail?: unknown;
  };
  if (!r.ok) {
    const d = raw.detail;
    const msg =
      typeof d === "string"
        ? d
        : d != null
          ? JSON.stringify(d)
          : JSON.stringify(raw);
    throw new Error(msg);
  }
  return {
    ok: Boolean(raw.ok),
    message: typeof raw.message === "string" ? raw.message : "",
  };
}
