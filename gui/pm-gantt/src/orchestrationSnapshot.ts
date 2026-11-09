/**
 * Orchestration snapshot contract and its pure view model (M17.2).
 *
 * The snapshot is `specy_road.orchestration`'s `state.snapshot(repo_root)`,
 * served unchanged by `GET /api/orchestration` (M17.7). Required fields are
 * M16.3.1's schema 1 list; schema 2 (M17.6) only adds optional fields, so a
 * schema 1 server still type-checks. Any readable-source field may be the
 * literal `"unknown"` when its source could not be read.
 *
 * `buildOrchestrationView` takes the clock as a parameter (no `Date.now()`),
 * joins leaf keys to the outline the GUI already loads, and returns display
 * text only: no React, no fetch. The drawer's loader, poll and copy commands
 * (M17.3) sit below it, with the fetch and the timer injected or owned here
 * so vitest drives them without a DOM.
 */
import { formatRelativeAge } from "./lastWorked";
import type { RoadmapNode } from "./types";

export type Unknown = "unknown";

export type WorkerStatus =
  | "claimed"
  | "running"
  | "exited_ok"
  | "exited_failed"
  | "abandoned"
  | "unknown";

export type SnapshotClaim = {
  codename: string | Unknown;
  branch: string | Unknown;
  registered_at: string | Unknown;
};

export type SnapshotWorker = {
  id: string;
  harness: string | Unknown;
  model: string | Unknown;
  status: WorkerStatus;
  pid_alive: boolean | Unknown;
  started_at: string | null | Unknown;
  ended_at: string | null | Unknown;
  /** Schema 2: Claude profile name, or null when not known (M17.1 question 3). */
  account?: string | null;
  last_activity?: string | null | Unknown;
  /** Schema 2: rendered verbatim (stalled, steering_changed, paused_by_limit, …). */
  flags?: string[];
};

export type SnapshotWorktree = {
  path: string;
  branch: string | Unknown;
  dirty: boolean | Unknown;
  ahead?: number | Unknown;
  behind?: number | Unknown;
};

export type SnapshotReview = {
  model: string | Unknown;
  verdict: string | Unknown;
  commit: string | Unknown;
  fresh_for_head: boolean | Unknown;
};

export type SnapshotBlockedOn = { acceptance: string; reason: string };

export type SnapshotReady = {
  commit: string | Unknown;
  model: string | Unknown;
  at: string | Unknown;
  blocked_on?: SnapshotBlockedOn[];
};

export type SnapshotGate = {
  /** A `specy-road handoff status` label (approved, blocked, executor_blocked, …). */
  state: string | Unknown;
  approvals: number | Unknown;
  blocks: number | Unknown;
  fresh_for_head: boolean | Unknown;
};

export type SnapshotHold = {
  source: "hold_list" | "gate";
  id: string;
  reason: string | null;
};

export type SnapshotLeaf = {
  claim: SnapshotClaim | null;
  workers: SnapshotWorker[];
  worktrees: SnapshotWorktree[];
  reviews: SnapshotReview[];
  ready?: SnapshotReady | null;
  gate?: SnapshotGate | null;
  holds?: SnapshotHold[];
};

export type OrchestrationSnapshot = {
  schema: number;
  /** Keyed by the outline's `node_key`. */
  leaves: Record<string, SnapshotLeaf>;
  leafless_workers: SnapshotWorker[];
};

/*
 * Key paths: `.` between object keys, `*` for a leaf key in `leaves`, `[]`
 * for any list item. M17.6's Python fixture compares against these lists.
 */
const WORKER_REQUIRED = ["id", "harness", "model", "status", "pid_alive", "started_at", "ended_at"];
const WORKER_OPTIONAL = ["account", "last_activity", "flags"];
const under = (prefix: string, keys: string[]) => keys.map((k) => `${prefix}.${k}`);

export const requiredKeys: readonly string[] = [
  "schema",
  "leaves",
  "leaves.*",
  "leaves.*.claim",
  ...under("leaves.*.claim", ["codename", "branch", "registered_at"]),
  "leaves.*.workers",
  ...under("leaves.*.workers[]", WORKER_REQUIRED),
  "leaves.*.worktrees",
  ...under("leaves.*.worktrees[]", ["path", "branch", "dirty"]),
  "leaves.*.reviews",
  ...under("leaves.*.reviews[]", ["model", "verdict", "commit", "fresh_for_head"]),
  "leafless_workers",
  ...under("leafless_workers[]", WORKER_REQUIRED),
];

export const optionalKeys: readonly string[] = [
  ...under("leaves.*.workers[]", WORKER_OPTIONAL),
  ...under("leafless_workers[]", WORKER_OPTIONAL),
  ...under("leaves.*.worktrees[]", ["ahead", "behind"]),
  "leaves.*.ready",
  ...under("leaves.*.ready", ["commit", "model", "at", "blocked_on"]),
  ...under("leaves.*.ready.blocked_on[]", ["acceptance", "reason"]),
  "leaves.*.gate",
  ...under("leaves.*.gate", ["state", "approvals", "blocks", "fresh_for_head"]),
  "leaves.*.holds",
  ...under("leaves.*.holds[]", ["source", "id", "reason"]),
];

/* ---------- view model ---------- */

/** M17.1 precedence, highest first. */
export type LeafBadgeKind =
  | "blocked"
  | "held"
  | "exited_failed"
  | "stalled"
  | "running"
  | "ready"
  | "approved"
  | "claimed"
  | "abandoned"
  | "unknown";

export type LeafBadge = { kind: LeafBadgeKind; text: string };

export type WorkerRowView = {
  id: string;
  harnessModel: string;
  account: string;
  status: string;
  lastActivity: string;
  started: string;
  ended: string;
  flags: string[];
};

export type WorktreeRowView = {
  path: string;
  branch: string;
  dirty: string;
  ahead: string;
  behind: string;
};

export type ReviewRowView = { model: string; verdict: string; commit: string; fresh: string };

export type OrchestrationGroupView = {
  /** Leaf `node_key`; null for the "No leaf" group. */
  key: string | null;
  displayId: string;
  title: string;
  badge: LeafBadge | null;
  claim: { codename: string; branch: string; registered: string } | null;
  workers: WorkerRowView[];
  worktrees: WorktreeRowView[];
  reviews: ReviewRowView[];
  ready: { commit: string; model: string; age: string; blockedOn: string[] } | null;
  gate: { state: string; approvals: string; blocks: string; fresh: string } | null;
  holds: { source: string; id: string; reason: string }[];
};

export type OutlineNodeRef = Pick<RoadmapNode, "id" | "node_key" | "title">;

const MISSING = "—";

/** READY's displayed commit. Freshness is never derived from this or from a review's commit. */
const SHORT_COMMIT_LEN = 12;

/** `"unknown"` stays "unknown"; absent or null is "—", never false, 0 or clean. */
function text(v: string | number | null | undefined): string {
  if (v === undefined || v === null) return MISSING;
  return String(v);
}

function yesNo(v: boolean | Unknown | undefined, yes: string, no: string): string {
  if (v === undefined || v === null) return MISSING;
  if (v === "unknown") return v;
  return v ? yes : no;
}

function age(iso: string | null | undefined, now: Date): string {
  if (iso === undefined || iso === null) return MISSING;
  if (iso === "unknown") return iso;
  return formatRelativeAge(iso, now) || MISSING;
}

function shortCommit(commit: string): string {
  if (commit === "unknown" || commit.length <= SHORT_COMMIT_LEN) return commit;
  return commit.slice(0, SHORT_COMMIT_LEN);
}

/** `block` first; every other verdict keeps its snapshot order. */
function reviewsBlockingFirst(reviews: SnapshotReview[]): SnapshotReview[] {
  return reviews
    .map((r, i) => ({ r, i }))
    .sort(
      (a, b) =>
        Number(a.r.verdict !== "block") - Number(b.r.verdict !== "block") || a.i - b.i,
    )
    .map(({ r }) => r);
}

function workerRow(w: SnapshotWorker, now: Date): WorkerRowView {
  return {
    id: w.id,
    harnessModel: `${w.harness} / ${w.model}`,
    // M17.1 question 3: an unknown account is an empty cell, not "—".
    account: w.account ?? "",
    status: w.status,
    lastActivity: age(w.last_activity, now),
    started: age(w.started_at, now),
    ended: age(w.ended_at, now),
    flags: w.flags ?? [],
  };
}

function blockedCount(leaf: SnapshotLeaf): number | null {
  const gate = leaf.gate;
  if (!gate || (gate.state !== "blocked" && gate.state !== "executor_blocked")) return null;
  if (typeof gate.blocks === "number" && gate.blocks > 0) return gate.blocks;
  return leaf.ready?.blocked_on?.length ?? 0;
}

/** One badge per leaf, the highest of M17.1's precedence that applies. */
export function leafBadge(leaf: SnapshotLeaf): LeafBadge | null {
  const blocks = blockedCount(leaf);
  if (blocks !== null) return { kind: "blocked", text: blocks > 0 ? `blocked (${blocks})` : "blocked" };
  const holds = leaf.holds ?? [];
  if (holds.length > 0) return { kind: "held", text: holds.length > 1 ? `held (${holds.length})` : "held" };
  const ws = leaf.workers;
  if (ws.some((w) => w.status === "exited_failed")) return { kind: "exited_failed", text: "exited_failed" };
  if (ws.some((w) => w.flags?.includes("stalled"))) return { kind: "stalled", text: "stalled" };
  if (ws.some((w) => w.status === "running")) return { kind: "running", text: "running" };
  const approved = leaf.gate?.state === "approved";
  if (leaf.ready && !approved) return { kind: "ready", text: "READY awaiting review" };
  if (approved) return { kind: "approved", text: "approved" };
  if (leaf.claim || ws.some((w) => w.status === "claimed")) return { kind: "claimed", text: "claimed" };
  if (ws.some((w) => w.status === "abandoned")) return { kind: "abandoned", text: "abandoned" };
  if (ws.some((w) => w.status === "unknown")) return { kind: "unknown", text: "unknown" };
  return null;
}

export type OutlineBadgeView = {
  /** Badge label. One per leaf; the same text `leafBadge` chooses. */
  text: string;
  /** Claim, workers, worktree count, READY, reviews, and each hold. */
  hover: string;
  /** Leaf `node_key` a click passes to the drawer's `filterLeafId`. */
  leafKey: string;
};

/** Hold-list holds name the reason; a gate hold names the open gate id. */
function holdPhrase(hold: SnapshotHold): string {
  if (hold.source === "hold_list") {
    return hold.reason == null ? "hold list" : `hold list: ${text(hold.reason)}`;
  }
  return text(hold.id);
}

function badgeHover(leaf: SnapshotLeaf, now: Date): string {
  const claim = leaf.claim
    ? `${text(leaf.claim.codename)} · ${text(leaf.claim.branch)} · ${age(leaf.claim.registered_at, now)}`
    : "—";
  const workers =
    leaf.workers.length > 0 ? leaf.workers.map((w) => `${w.id} ${w.status}`).join(", ") : "—";
  const reviews =
    leaf.reviews.length > 0
      ? leaf.reviews.map((r) => `${text(r.model)} ${text(r.verdict)}`).join("; ")
      : "—";
  const ready = leaf.ready ? shortCommit(text(leaf.ready.commit)) : "—";
  const holds = leaf.holds?.length ? leaf.holds.map(holdPhrase).join("; ") : "—";
  return [
    `claim: ${claim}`,
    `workers: ${workers}`,
    `worktrees: ${leaf.worktrees.length}`,
    `READY: ${ready}`,
    `reviews: ${reviews}`,
    `holds: ${holds}`,
  ].join("\n");
}

/**
 * One outline badge for `leafKey`, or null when this load is not a snapshot
 * (404 and any other failure) or the leaf has no orchestration state.
 */
export function outlineBadge(
  load: OrchestrationLoad,
  leafKey: string,
  now: Date,
): OutlineBadgeView | null {
  if (load.kind !== "ok") return null;
  const leaf = load.snapshot.leaves[leafKey];
  if (!leaf) return null;
  const badge = leafBadge(leaf);
  if (!badge) return null;
  return { text: badge.text, hover: badgeHover(leaf, now), leafKey };
}

function leafGroup(
  key: string,
  leaf: SnapshotLeaf,
  node: OutlineNodeRef | undefined,
  now: Date,
): OrchestrationGroupView {
  const { claim, ready, gate } = leaf;
  return {
    key,
    displayId: node?.id ?? key,
    title: node?.title ?? MISSING,
    badge: leafBadge(leaf),
    claim: claim
      ? {
          codename: text(claim.codename),
          branch: text(claim.branch),
          registered: age(claim.registered_at, now),
        }
      : null,
    workers: leaf.workers.map((w) => workerRow(w, now)),
    worktrees: leaf.worktrees.map((t) => ({
      path: text(t.path),
      branch: text(t.branch),
      dirty: yesNo(t.dirty, "yes", "no"),
      ahead: text(t.ahead),
      behind: text(t.behind),
    })),
    reviews: reviewsBlockingFirst(leaf.reviews).map((r) => ({
      model: text(r.model),
      verdict: text(r.verdict),
      commit: text(r.commit),
      // fresh_for_head only: a commit that differs from READY.commit stays fresh when the snapshot says so.
      fresh: yesNo(r.fresh_for_head, "fresh", "stale"),
    })),
    ready: ready
      ? {
          commit: shortCommit(text(ready.commit)),
          model: text(ready.model),
          age: age(ready.at, now),
          blockedOn: (ready.blocked_on ?? []).map((b) => `${text(b.acceptance)}: ${text(b.reason)}`),
        }
      : null,
    gate: gate
      ? {
          state: text(gate.state),
          approvals: text(gate.approvals),
          blocks: text(gate.blocks),
          fresh: yesNo(gate.fresh_for_head, "fresh", "stale"),
        }
      : null,
    holds: (leaf.holds ?? []).map((h) => ({
      source: text(h.source),
      id: text(h.id),
      reason: text(h.reason),
    })),
  };
}

/**
 * Groups in outline order, then leaf keys absent from the outline (by key),
 * then one "No leaf" group for leafless workers.
 */
export function buildOrchestrationView(
  snapshot: OrchestrationSnapshot,
  outline: readonly OutlineNodeRef[],
  now: Date,
): OrchestrationGroupView[] {
  const leaves = snapshot.leaves ?? {};
  const byKey = new Map(outline.map((n) => [n.node_key, n]));
  const inOutline = outline.map((n) => n.node_key).filter((k) => Object.hasOwn(leaves, k));
  const orphans = Object.keys(leaves)
    .filter((k) => !byKey.has(k))
    .sort();
  const groups = [...inOutline, ...orphans].map((k) => leafGroup(k, leaves[k], byKey.get(k), now));
  const leafless = snapshot.leafless_workers ?? [];
  if (leafless.length > 0) {
    groups.push({
      key: null,
      displayId: "",
      title: "No leaf",
      badge: null,
      claim: null,
      workers: leafless.map((w) => workerRow(w, now)),
      worktrees: [],
      reviews: [],
      ready: null,
      gate: null,
      holds: [],
    });
  }
  return groups;
}

/* ---------- drawer: load, poll, copy commands (M17.3) ---------- */

export type OrchestrationLoad =
  | { kind: "ok"; snapshot: OrchestrationSnapshot }
  /** 404: a server without the route (any build before M17.7). */
  | { kind: "unavailable" }
  | { kind: "error"; message: string };

export type OrchestrationNotice = { load: OrchestrationLoad; at: Date };

/**
 * Listeners for each `loadOrchestration` result. The outline badge subscribes
 * so a roadmap refresh and every drawer load (its poll included) update it.
 * The badge has no timer of its own.
 */
const orchestrationListeners = new Set<(notice: OrchestrationNotice) => void>();

/** Subscribe to later loads. The returned function removes the listener. */
export function subscribeOrchestration(
  listener: (notice: OrchestrationNotice) => void,
): () => void {
  orchestrationListeners.add(listener);
  return () => {
    orchestrationListeners.delete(listener);
  };
}

/** One GET of `/api/orchestration`; never throws. Notifies subscribers. */
export async function loadOrchestration(fetchImpl: typeof fetch): Promise<OrchestrationLoad> {
  let load: OrchestrationLoad;
  try {
    const r = await fetchImpl("/api/orchestration");
    if (r.status === 404) load = { kind: "unavailable" };
    else if (!r.ok) load = { kind: "error", message: `orchestration: HTTP ${r.status}` };
    else load = { kind: "ok", snapshot: (await r.json()) as OrchestrationSnapshot };
  } catch (e: unknown) {
    load = { kind: "error", message: String(e) };
  }
  const notice = { load, at: new Date() };
  for (const listener of orchestrationListeners) listener(notice);
  return load;
}

/** M17.1 question 5: refresh every 15 s, only while the drawer is open. */
const POLL_MS = 15_000;

/** Calls `load` now and every 15 s; the returned function stops it. */
export function pollOrchestration(load: () => void): () => void {
  load();
  const timer = setInterval(load, POLL_MS);
  return () => clearInterval(timer);
}

export type CopyKind = "worker status" | "worker open" | "handoff status";

/** `specy-road <kind> <id>`, the id single-quoted for a POSIX shell unless it is [A-Za-z0-9._-]+. */
export function copyCommand(kind: CopyKind, id: string): string {
  const arg = /^[A-Za-z0-9._-]+$/.test(id) ? id : `'${id.replaceAll("'", `'\\''`)}'`;
  return `specy-road ${kind} ${arg}`;
}
