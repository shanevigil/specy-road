import type { RoadmapResponse } from "./types";

const API = "/api";

export async function fetchRoadmap(): Promise<RoadmapResponse> {
  const r = await fetch(`${API}/roadmap`);
  if (!r.ok) throw new Error(`roadmap: ${r.status}`);
  return r.json() as Promise<RoadmapResponse>;
}

export async function fetchGovernanceCompletion(): Promise<{
  vision_needs_completion: boolean;
  constitution_needs_completion: boolean;
}> {
  const r = await fetch(`${API}/governance-completion`);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    vision_needs_completion: boolean;
    constitution_needs_completion: boolean;
  }>;
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

export async function deleteNode(nodeId: string): Promise<void> {
  const r = await fetch(`${API}/nodes/${encodeURIComponent(nodeId)}`, {
    method: "DELETE",
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
  return r.json() as Promise<{
    planning_dir: string | null;
    ancestor_planning_files?: { role?: string; path: string; exists: boolean }[];
    files: { role: string; path: string; exists: boolean }[];
  }>;
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

export type WorkspaceFileEntry = {
  path: string;
  name: string;
  bytes: number;
};

export async function fetchWorkspaceFiles(
  prefix: "shared" | "work",
): Promise<{ prefix: string; files: WorkspaceFileEntry[] }> {
  const r = await fetch(
    `${API}/workspace/files?${new URLSearchParams({ prefix })}`,
  );
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    prefix: string;
    files: WorkspaceFileEntry[];
  }>;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const data = r.result as string;
      const i = data.indexOf(",");
      resolve(i >= 0 ? data.slice(i + 1) : data);
    };
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

/** Upload a file into ``shared/`` (optional subfolder under ``shared``, e.g. ``contracts``). */
export async function uploadSharedFile(
  file: File,
  subpath?: string,
): Promise<{ ok: string; path: string }> {
  const safeName = file.name.replace(/^.*[/\\]/, "");
  const sub = subpath?.trim().replace(/^[/\\]+|[/\\]+$/g, "").replace(/\\/g, "/");
  const path = sub
    ? `shared/${sub}/${safeName}`.replace(/\/+/g, "/")
    : `shared/${safeName}`;
  const content_base64 = await fileToBase64(file);
  const r = await fetch(`${API}/workspace/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content_base64 }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok: string; path: string }>;
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

export async function putSettings(payload: {
  inherit_llm: boolean;
  inherit_git_remote: boolean;
  llm: Record<string, string>;
  git_remote: Record<string, string>;
}) {
  const r = await fetch(`${API}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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

export async function fetchRoadmapFingerprint(): Promise<number> {
  const r = await fetch(`${API}/roadmap/fingerprint`);
  const raw = (await r.json()) as { fingerprint?: number; detail?: unknown };
  if (!r.ok) {
    const d = raw.detail;
    throw new Error(
      typeof d === "string" ? d : JSON.stringify(raw),
    );
  }
  if (typeof raw.fingerprint !== "number") {
    throw new Error("invalid fingerprint response");
  }
  return raw.fingerprint;
}

/** LLM settings object as stored in gui-settings / API (values may be strings). */
export async function postLlmReview(
  nodeId: string,
  llm: Record<string, unknown>,
  /** Live planning sheet from the editor (sent as planning_body). */
  planningBody: string,
): Promise<string> {
  const r = await fetch(`${API}/llm/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      node_id: nodeId,
      llm,
      planning_body: planningBody,
    }),
  });
  const raw = (await r.json()) as { report?: string; detail?: unknown };
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
  if (typeof raw.report !== "string") {
    throw new Error("invalid review response");
  }
  return raw.report;
}

export async function postGitTest(
  gitRemote: Record<string, string>,
): Promise<{ ok: boolean; message: string }> {
  const r = await fetch(`${API}/git/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ git_remote: gitRemote }),
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
