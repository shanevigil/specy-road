import { act, createElement as createReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import drawerSource from "./components/OrchestrationDrawer.tsx?raw";
import mockJson from "./fixtures/orchestration_snapshot_mock.json";
import {
  buildOrchestrationView,
  copyCommand,
  leafBadge,
  loadOrchestration,
  optionalKeys,
  outlineBadge,
  outlineNodesInRowOrder,
  pollOrchestration,
  requiredKeys,
  subscribeOrchestration,
  type OrchestrationSnapshot,
  type OutlineNodeRef,
  type SnapshotLeaf,
  type SnapshotWorker,
} from "./orchestrationSnapshot";

const NOW = new Date("2026-11-08T12:00:00Z");
const mock = mockJson as unknown as OrchestrationSnapshot;

type ObjectVisit = { path: string; at: string; obj: Record<string, unknown> };

/**
 * Every object in a snapshot-shaped value: `path` in the module's key-path
 * notation, `at` the concrete location (`leaves.k1.workers[0]`) for messages.
 */
function objects(value: unknown, path = "", at = "", out: ObjectVisit[] = []): ObjectVisit[] {
  if (Array.isArray(value)) {
    value.forEach((item, i) => objects(item, `${path}[]`, `${at}[${i}]`, out));
  } else if (value !== null && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    out.push({ path, at, obj });
    for (const [k, v] of Object.entries(obj)) {
      const seg = path === "leaves" ? "*" : k;
      objects(v, path ? `${path}.${seg}` : seg, at ? `${at}.${k}` : k, out);
    }
  }
  return out;
}

const childPath = (parent: string, key: string, mapKeys: boolean) =>
  `${parent ? `${parent}.` : ""}${mapKeys ? "*" : key}`;

/** Every key path the value uses, in the module's notation. */
const keyPaths = (value: unknown) =>
  new Set(
    objects(value).flatMap(({ path, obj }) =>
      Object.keys(obj).map((k) => childPath(path, k, path === "leaves")),
    ),
  );

/**
 * Rule: a key path is unlisted when no list names it; a required key is
 * missing when any concrete object at its parent path lacks it (so one
 * complete entry cannot hide an incomplete sibling). Map entries (`leaves.*`)
 * and list items are checked only where they exist: an empty map or list,
 * or a null claim, has no children to check. The whole mock must still
 * contain every required path once, so a list that is always empty is caught;
 * that check skips paths under a container already reported missing.
 */
function contractProblems(snapshot: unknown): { unlisted: string[]; missing: string[] } {
  const known = new Set([...requiredKeys, ...optionalKeys]);
  const paths = keyPaths(snapshot);
  const missing: string[] = [];
  const missingPaths: string[] = [];
  for (const { path, at, obj } of objects(snapshot)) {
    if (path === "leaves") continue;
    for (const req of requiredKeys) {
      const key = req.slice(req.lastIndexOf(".") + 1);
      if (childPath(path, key, false) === req && !Object.hasOwn(obj, key)) {
        missing.push(at ? `${at}.${key}` : key);
        missingPaths.push(req);
      }
    }
  }
  return {
    unlisted: [...paths].filter((p) => !known.has(p)).sort(),
    missing: [
      ...missing,
      ...requiredKeys.filter(
        (p) => !paths.has(p) && !missingPaths.some((m) => p === m || p.startsWith(`${m}.`) || p.startsWith(`${m}[`)),
      ),
    ],
  };
}

describe("snapshot key paths", () => {
  it("the mock uses only listed paths, every required one and every optional one", () => {
    expect(contractProblems(mock)).toEqual({ unlisted: [], missing: [] });
    const paths = keyPaths(mock);
    expect(optionalKeys.filter((p) => !paths.has(p))).toEqual([]);
  });

  it("catches a misspelled field inside a leaf's worker and a dropped required field", () => {
    const scratch = structuredClone(mockJson) as unknown as {
      leaves: Record<string, { workers: Record<string, unknown>[] }>;
      leafless_workers?: unknown;
    };
    const w = scratch.leaves["M10"].workers[0];
    w.stauts = w.status;
    delete w.status;
    delete scratch.leafless_workers;
    const { unlisted, missing } = contractProblems(scratch);
    expect(unlisted).toEqual(["leaves.*.workers[].stauts"]);
    expect(missing).toEqual(["leafless_workers", "leaves.M10.workers[0].status"]);
  });

  // Each field is still present on a sibling entry, so only a per-object
  // check sees it missing.
  it.each([
    ["leaves", "M10", "workers", 0, "harness"],
    ["leaves", "M13", "workers", 1, "pid_alive"],
    ["leaves", "M10", "worktrees", 1, "dirty"],
    ["leaves", "M9.4", "reviews", 0, "fresh_for_head"],
    ["leaves", "M12", "claim", "branch"],
    ["leaves", "M9.3"],
    ["leafless_workers", 0, "started_at"],
  ] as (string | number)[][])("reports %s.%s… missing on that one entry", (...segs) => {
    const scratch = structuredClone(mockJson) as unknown as Record<string | number, unknown>;
    const parent = segs.slice(0, -1).reduce<Record<string | number, unknown>>(
      (o, s) => o[s] as Record<string | number, unknown>,
      scratch,
    );
    const last = segs[segs.length - 1];
    if (segs.length === 2) {
      // A leaf entry with every required field gone.
      parent[last] = {};
    } else {
      delete parent[last];
    }
    const at = segs.map((s) => (typeof s === "number" ? `[${s}]` : `.${s}`)).join("").slice(1);
    const expected =
      segs.length === 2
        ? ["claim", "workers", "worktrees", "reviews", "status"].map((k) => `${at}.${k}`)
        : [at];
    expect(contractProblems(scratch)).toEqual({ unlisted: [], missing: expected });
  });

  it("the mock covers every worker status", () => {
    const all = [...Object.values(mock.leaves).flatMap((l) => l.workers), ...mock.leafless_workers];
    expect(new Set(all.map((w) => w.status))).toEqual(
      new Set(["starting", "running", "idle", "paused_by_limit", "completed", "failed", "terminated", "unknown"]),
    );
  });
});

const worker = (over: Partial<SnapshotWorker> = {}): SnapshotWorker => ({
  id: "w-1",
  harness: "claude",
  model: "opus",
  status: "completed",
  pid_alive: false,
  started_at: "2026-11-08T10:00:00Z",
  ended_at: null,
  ...over,
});

const emptyLeaf = (): SnapshotLeaf => ({
  status: "claimed", claim: null, workers: [], worktrees: [], reviews: [],
});

/** Each badge candidate alone, in M17.1's precedence order. */
const CANDIDATES: [string, Partial<SnapshotLeaf>, string][] = [
  ["blocked", { gate: { state: "blocked", approvals: 0, blocks: 2, fresh_for_head: true } }, "blocked (2)"],
  ["held", { holds: [{ source: "hold_list", id: "M1", reason: "r" }] }, "held"],
  ["failed", { workers: [worker({ status: "failed" })] }, "failed"],
  ["stalled", { workers: [worker({ flags: ["stalled"] })] }, "stalled"],
  ["running", { workers: [worker({ status: "running" })] }, "running"],
  ["ready", { ready: { commit: "c", model: "m", at: "2026-11-08T11:00:00Z" } }, "READY awaiting review"],
  ["approved", { gate: { state: "approved", approvals: 2, blocks: 0, fresh_for_head: true } }, "approved"],
  ["claimed", { claim: { codename: "c", branch: "b", registered_at: "2026-11-08T09:00:00Z" } }, "claimed"],
  ["abandoned", { status: "abandoned" }, "abandoned"],
  ["unknown", { workers: [worker({ status: "unknown" })] }, "unknown"],
];

function merge(...parts: Partial<SnapshotLeaf>[]): SnapshotLeaf {
  const leaf = emptyLeaf();
  for (const p of parts) {
    Object.assign(leaf, { ...p, workers: [...leaf.workers, ...(p.workers ?? [])] });
  }
  return leaf;
}

describe("leafBadge", () => {
  it.each(CANDIDATES)("%s alone", (kind, part, text) => {
    expect(leafBadge(merge(part))).toEqual({ kind, text });
  });

  it("no orchestration state, no badge", () => {
    expect(leafBadge(emptyLeaf())).toBeNull();
    expect(leafBadge(merge({ workers: [worker()] }))).toBeNull();
  });

  // ready + approved: an approved gate has reviewed the READY, so it is no
  // longer "awaiting review" and approved shows; every other pair keeps the
  // higher of the two.
  it.each(CANDIDATES.slice(0, -1).map((hi, i) => [hi[0], CANDIDATES[i + 1][0], hi, CANDIDATES[i + 1]] as const))(
    "%s over %s",
    (_hiKind, loKind, hi, lo) => {
      const expected = loKind === "approved" ? lo : hi;
      expect(leafBadge(merge(hi[1], lo[1]))?.kind).toBe(expected[0]);
      expect(leafBadge(merge(lo[1], hi[1]))?.kind).toBe(expected[0]);
    },
  );

  it("executor_blocked counts READY blocked_on entries when gate.blocks is 0", () => {
    const leaf = merge({
      gate: { state: "executor_blocked", approvals: 0, blocks: 0, fresh_for_head: true },
      ready: {
        commit: "c",
        model: "m",
        at: "2026-11-08T11:00:00Z",
        blocked_on: [
          { acceptance: "A1", reason: "x" },
          { acceptance: "A2", reason: "y" },
        ],
      },
    });
    expect(leafBadge(leaf)).toEqual({ kind: "blocked", text: "blocked (2)" });
  });

  it("does not depend on worker order", () => {
    const ws = [worker({ id: "a", status: "running" }), worker({ id: "b", status: "failed" })];
    expect(leafBadge(merge({ workers: ws }))?.kind).toBe("failed");
    expect(leafBadge(merge({ workers: [...ws].reverse() }))?.kind).toBe("failed");
  });
});

describe("outlineBadge", () => {
  it("present, 404 and no state: badge text, hover and the leaf key a click passes", () => {
    const present = outlineBadge({ kind: "ok", snapshot: mock }, "M10", NOW);
    expect(present).toEqual({
      text: "blocked (1)",
      leafKey: "M10",
      hover: [
        "claim: alpha · feature/rm-alpha · 3h ago",
        "workers: w-0001 running",
        "worktrees: 2",
        "READY: abc1234",
        "reviews: sol block",
        "holds: —",
      ].join("\n"),
    });

    const heldList = outlineBadge({ kind: "ok", snapshot: mock }, "M9.4", NOW);
    expect(heldList).toEqual({
      text: "held",
      leafKey: "M9.4",
      hover: [
        "claim: gamma · feature/rm-gamma · 2d ago",
        "workers: w-0003 completed",
        "worktrees: 0",
        "READY: —",
        "reviews: grok approve",
        "holds: hold list: waiting on the maintainer",
      ].join("\n"),
    });
    expect(outlineBadge({ kind: "ok", snapshot: mock }, "M9.3", NOW)?.hover).toContain(
      "holds: M9.3",
    );

    const counted = outlineBadge(
      {
        kind: "ok",
        snapshot: {
          schema: 2,
          leaves: {
            k: merge({
              gate: { state: "executor_blocked", approvals: 0, blocks: 0, fresh_for_head: true },
              ready: {
                commit: "c",
                model: "m",
                at: "2026-11-08T11:00:00Z",
                blocked_on: [
                  { acceptance: "A1", reason: "x" },
                  { acceptance: "A2", reason: "y" },
                ],
              },
            }),
          },
          leafless_workers: [],
        },
      },
      "k",
      NOW,
    );
    expect(counted?.text).toBe("blocked (2)");
    expect(counted?.leafKey).toBe("k");

    const named = outlineBadge(
      {
        kind: "ok",
        snapshot: {
          schema: 2,
          leaves: {
            k: merge({
              holds: [
                { source: "hold_list", id: "M1", reason: null },
                { source: "gate", id: "G9", reason: "a title" },
              ],
            }),
          },
          leafless_workers: [],
        },
      },
      "k",
      NOW,
    );
    expect(named?.text).toBe("held (2)");
    expect(named?.leafKey).toBe("k");
    expect(named?.hover.endsWith("holds: hold list; G9")).toBe(true);

    const claimed = outlineBadge(
      {
        kind: "ok",
        snapshot: {
          schema: 1,
          leaves: {
            k: merge({
              claim: { codename: "c", branch: "b", registered_at: "2026-11-08T11:59:30Z" },
            }),
          },
          leafless_workers: [],
        },
      },
      "k",
      NOW,
    );
    expect(claimed?.text).toBe("claimed");
    expect(claimed?.hover).toContain("workers: —");
    expect(claimed?.hover).toContain("worktrees: 0");
    expect(claimed?.hover).toContain("READY: —");
    expect(claimed?.hover).toContain("reviews: —");
    expect(claimed?.hover.endsWith("holds: —")).toBe(true);

    expect(outlineBadge({ kind: "unavailable" }, "M10", NOW)).toBeNull();
    expect(
      outlineBadge(
        { kind: "ok", snapshot: { schema: 1, leaves: { k: emptyLeaf() }, leafless_workers: [] } },
        "k",
        NOW,
      ),
    ).toBeNull();
    expect(outlineBadge({ kind: "ok", snapshot: mock }, "missing", NOW)).toBeNull();
  });
});

/** An outline node as the GUI loads it: its `node_key` is a UUID, never the snapshot's key. */
const outlineNode = (id: string, title = `title ${id}`): OutlineNodeRef & { node_key: string } => ({
  id,
  node_key: `0b7e-${id}-uuid`,
  title,
});

describe("buildOrchestrationView", () => {
  const outline = [
    outlineNode("M9.3"),
    outlineNode("M9.4"),
    outlineNode("M10"),
    outlineNode("M11"),
  ];

  // The snapshot keys leaves by node id; joining on the outline's node_key renders every leaf as missing.
  it("joins on node id: outline leaves keep their id and title, only absent ids are missing; badges from the mock", () => {
    const view = buildOrchestrationView(mock, outline, NOW);
    expect(view.map((g) => [g.displayId, g.title, g.inOutline, g.badge?.text ?? null])).toEqual([
      ["M9.3", "title M9.3", true, "held"],
      ["M9.4", "title M9.4", true, "held"],
      ["M10", "title M10", true, "blocked (1)"],
      ["M12", "—", false, "blocked (1)"],
      ["M13", "—", false, "unknown"],
      ["", "No leaf", false, null],
    ]);
  });

  it("keeps numeric-looking display ids in outline order, not sorted", () => {
    const snap: OrchestrationSnapshot = {
      schema: 1,
      leaves: { "M1.2": emptyLeaf(), "2": emptyLeaf(), "M1.10": emptyLeaf() },
      leafless_workers: [],
    };
    const view = buildOrchestrationView(
      snap,
      [outlineNode("M1.10"), outlineNode("M1.2"), outlineNode("2")],
      NOW,
    );
    expect(view.map((g) => g.displayId)).toEqual(["M1.10", "M1.2", "2"]);
  });

  // M17.9 item 3: the node array is the Gantt's dependency-step order (M0.2
  // depends on M0.3). Groups follow the outline rows, then No leaf. M0.10
  // would sort before M0.2 if the order were the ids.
  it("lists groups in the outline's row order, not the Gantt node array (M0.2 depends on M0.3)", () => {
    const ganttOrder = [
      outlineNode("M0.1"),
      outlineNode("M0.3"),
      outlineNode("M2"),
      outlineNode("M0.2"),
    ];
    const rowOrder = ["M0.1", "M0.2", "M0.3", "M2"];
    const snap: OrchestrationSnapshot = {
      schema: 1,
      leaves: {
        "M0.1": emptyLeaf(),
        "M0.2": emptyLeaf(),
        "M0.3": emptyLeaf(),
        M2: emptyLeaf(),
      },
      leafless_workers: [worker({ id: "w-9" })],
    };
    const view = buildOrchestrationView(snap, outlineNodesInRowOrder(ganttOrder, rowOrder), NOW);
    expect(view.map((g) => (g.key === null ? g.title : g.displayId))).toEqual([
      "M0.1",
      "M0.2",
      "M0.3",
      "M2",
      "No leaf",
    ]);
    expect(
      outlineNodesInRowOrder(
        [outlineNode("M0.10"), outlineNode("M0.2"), outlineNode("M0.1")],
        ["M0.1", "M0.2", "M0.10"],
      ).map((n) => n.id),
    ).toEqual(["M0.1", "M0.2", "M0.10"]);
    expect(outlineNodesInRowOrder([outlineNode("M0.1")], ["missing", "M0.1"]).map((n) => n.id)).toEqual([
      "M0.1",
    ]);
  });

  it("formats mock rows: ages from now, null account empty, stale review, two worktrees, flags verbatim", () => {
    const g = buildOrchestrationView(mock, outline, NOW).find((x) => x.key === "M10")!;
    expect(g.claim).toEqual({ codename: "alpha", branch: "feature/rm-alpha", registered: "3h ago" });
    expect(g.workers).toEqual([
      {
        id: "w-0001",
        harnessModel: "claude / opus",
        account: "",
        status: "running",
        lastActivity: "30m ago",
        started: "2h ago",
        ended: "—",
        flags: ["stalled", "steering_changed"],
      },
    ]);
    expect(g.worktrees.map((t) => [t.dirty, t.ahead, t.behind])).toEqual([
      ["yes", "3", "0"],
      ["no", "0", "2"],
    ]);
    expect(g.reviews[0].fresh).toBe("stale");
    expect(g.gate).toEqual({ state: "blocked", approvals: "0", blocks: "1", fresh: "stale" });
  });

  it("renders explicit unknown as unknown and a null hold reason as —", () => {
    const view = buildOrchestrationView(mock, outline, NOW);
    const u = view.find((x) => x.key === "M13")!;
    expect(u.workers[0]).toMatchObject({
      harnessModel: "unknown / unknown",
      status: "unknown",
      lastActivity: "unknown",
      started: "unknown",
      ended: "unknown",
      account: "",
    });
    expect(u.worktrees[0]).toEqual({
      path: "work/.worktrees/epsilon",
      branch: "unknown",
      dirty: "unknown",
      ahead: "unknown",
      behind: "unknown",
    });
    expect(u.reviews[0].fresh).toBe("unknown");
    expect(u.gate).toEqual({ state: "unknown", approvals: "unknown", blocks: "unknown", fresh: "unknown" });
    const held = view.find((x) => x.key === "M9.3")!;
    expect(held.holds).toEqual([{ source: "gate", id: "M9.3", reason: "—" }]);
    const ex = view.find((x) => x.key === "M12")!;
    expect(ex.ready?.blockedOn).toEqual(["A2: needs a path outside the touch zones"]);
  });

  it("renders unknown holds, flags, READY, gate and claim as unknown text, not a map of the string", () => {
    const snap: OrchestrationSnapshot = {
      schema: 2,
      leaves: {
        k: {
          status: "unknown",
          claim: "unknown",
          workers: [worker({ status: "unknown", flags: "unknown" })],
          worktrees: [],
          reviews: [],
          ready: "unknown",
          gate: "unknown",
          holds: "unknown",
        },
      },
      leafless_workers: [],
    };
    const [g] = buildOrchestrationView(snap, [outlineNode("k")], NOW);
    expect(g.workers[0].flags).toEqual(["unknown"]);
    expect(g.holds).toEqual([{ source: "unknown", id: "unknown", reason: "unknown" }]);
    expect(g.ready).toEqual({ commit: "unknown", model: "unknown", age: "unknown", blockedOn: [] });
    expect(g.gate).toEqual({ state: "unknown", approvals: "unknown", blocks: "unknown", fresh: "unknown" });
    expect(g.claim).toEqual({ codename: "unknown", branch: "unknown", registered: "unknown" });
    expect(g.badge).toEqual({ kind: "unknown", text: "unknown" });
    expect(outlineBadge({ kind: "ok", snapshot: snap }, "k", NOW)?.hover).toContain("holds: unknown");
  });

  it("a schema 1 snapshot (no optional fields) shows — and an empty account, never false, 0 or clean", () => {
    const snap: OrchestrationSnapshot = {
      schema: 1,
      leaves: {
        k: {
          status: "running",
          claim: { codename: "c", branch: "b", registered_at: "2026-11-08T11:59:30Z" },
          workers: [worker({ status: "running", pid_alive: true })],
          worktrees: [{ path: "p", branch: "b", dirty: false }],
          reviews: [{ model: "m", verdict: "approve", commit: "c", fresh_for_head: true }],
        },
      },
      leafless_workers: [],
    };
    const [g] = buildOrchestrationView(snap, [outlineNode("k")], NOW);
    expect(g.badge).toEqual({ kind: "running", text: "running" });
    expect(g.claim?.registered).toBe("now");
    expect(g.workers[0]).toMatchObject({ account: "", lastActivity: "—", flags: [], ended: "—" });
    expect(g.worktrees[0]).toEqual({ path: "p", branch: "b", dirty: "no", ahead: "—", behind: "—" });
    expect(g.reviews).toEqual([{ model: "m", verdict: "approve", commit: "c", fresh: "fresh" }]);
    expect([g.ready, g.gate, g.holds]).toEqual([null, null, []]);
  });

  it("null or omitted claim, worktree, review, READY and gate text shows —", () => {
    const snap = {
      schema: 2,
      leaves: {
        k: {
          claim: { codename: null, branch: null, registered_at: null },
          workers: [],
          worktrees: [{ path: null, branch: null, dirty: null }],
          reviews: [{ model: null, verdict: null, commit: null, fresh_for_head: null }],
          ready: { commit: null, at: null, blocked_on: [{ acceptance: null, reason: null }] },
          gate: { state: null, blocks: null, fresh_for_head: null },
          holds: [{ source: null, id: null, reason: null }],
        },
      },
      leafless_workers: [],
    } as unknown as OrchestrationSnapshot;
    const [g] = buildOrchestrationView(snap, [outlineNode("k")], NOW);
    expect(g.claim).toEqual({ codename: "—", branch: "—", registered: "—" });
    expect(g.worktrees[0]).toEqual({
      path: "—",
      branch: "—",
      dirty: "—",
      ahead: "—",
      behind: "—",
    });
    expect(g.reviews).toEqual([{ model: "—", verdict: "—", commit: "—", fresh: "—" }]);
    expect(g.ready).toEqual({ commit: "—", model: "—", age: "—", blockedOn: ["—: —"] });
    expect(g.gate).toEqual({ state: "—", approvals: "—", blocks: "—", fresh: "—" });
    expect(g.holds).toEqual([{ source: "—", id: "—", reason: "—" }]);
  });

  it("freshness follows fresh_for_head only: a carried approval stays fresh, a block lists first, unknown stays unknown", () => {
    const readyCommit = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const carried = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const leaf = merge({
      reviews: [
        { model: "sol", verdict: "approve", commit: carried, fresh_for_head: true },
        { model: "opus", verdict: "block", commit: readyCommit, fresh_for_head: false },
        { model: "grok", verdict: "unknown", commit: "unknown", fresh_for_head: "unknown" },
      ],
      ready: { commit: readyCommit, model: "opus", at: "2026-11-08T11:00:00Z" },
    });
    const [g] = buildOrchestrationView(
      { schema: 2, leaves: { k: leaf }, leafless_workers: [] },
      [outlineNode("k")],
      NOW,
    );
    expect(g.reviews).toEqual([
      { model: "opus", verdict: "block", commit: readyCommit, fresh: "stale" },
      { model: "sol", verdict: "approve", commit: carried, fresh: "fresh" },
      { model: "grok", verdict: "unknown", commit: "unknown", fresh: "unknown" },
    ]);
    expect(g.ready).toEqual({
      commit: readyCommit.slice(0, 12),
      model: "opus",
      age: "1h ago",
      blockedOn: [],
    });
    expect(g.reviews[1].commit).not.toBe(g.ready?.commit);
  });

  it("an empty snapshot has no groups; leafless workers alone make one No leaf group", () => {
    const empty: OrchestrationSnapshot = { schema: 1, leaves: {}, leafless_workers: [] };
    expect(buildOrchestrationView(empty, [outlineNode("k")], NOW)).toEqual([]);
    const only = buildOrchestrationView(
      { ...empty, leafless_workers: [worker({ id: "w-9", account: "work" })] },
      [],
      NOW,
    );
    expect(only.map((g) => [g.key, g.title, g.badge, g.workers.map((w) => [w.id, w.account])])).toEqual([
      [null, "No leaf", null, [["w-9", "work"]]],
    ]);
  });
});

/** A fetch that records each request as `METHOD url` and answers with `reply()`. */
function recordingFetch(reply: () => Promise<Response>) {
  const requests: string[] = [];
  const fetchImpl = ((input: RequestInfo | URL, init?: RequestInit) => {
    requests.push(`${init?.method ?? "GET"} ${String(input)}`);
    return reply();
  }) as typeof fetch;
  return { requests, fetchImpl };
}

const respond = (body: string, status: number) => () => Promise.resolve(new Response(body, { status }));

describe("loadOrchestration", () => {
  it("makes one GET of /api/orchestration per load and returns the snapshot", async () => {
    const { requests, fetchImpl } = recordingFetch(respond(JSON.stringify(mockJson), 200));
    expect(await loadOrchestration(fetchImpl)).toEqual({ kind: "ok", snapshot: mock });
    expect(requests).toEqual(["GET /api/orchestration"]);
  });

  it("404 (a server without the route) is unavailable", async () => {
    const { requests, fetchImpl } = recordingFetch(respond("Not Found", 404));
    expect(await loadOrchestration(fetchImpl)).toEqual({ kind: "unavailable" });
    expect(requests).toEqual(["GET /api/orchestration"]);
  });

  it("tells subscribers about that load, including a 404, until they unsubscribe", async () => {
    const seen: string[] = [];
    const stop = subscribeOrchestration((notice) => seen.push(notice.load.kind));
    try {
      expect(await loadOrchestration(recordingFetch(respond(JSON.stringify(mockJson), 200)).fetchImpl)).toEqual({
        kind: "ok",
        snapshot: mock,
      });
      expect(await loadOrchestration(recordingFetch(respond("Not Found", 404)).fetchImpl)).toEqual({
        kind: "unavailable",
      });
      expect(seen).toEqual(["ok", "unavailable"]);
    } finally {
      stop();
    }
    await loadOrchestration(recordingFetch(respond("Not Found", 404)).fetchImpl);
    expect(seen).toEqual(["ok", "unavailable"]);
  });

  it.each([
    ["HTTP 500", respond("boom", 500), "orchestration: HTTP 500"],
    ["a network failure", () => Promise.reject(new TypeError("Failed to fetch")), "TypeError: Failed to fetch"],
    ["a body that is not JSON", respond("<html>", 200), "SyntaxError"],
  ])("%s is an error", async (_label, reply, message) => {
    const r = await loadOrchestration(recordingFetch(reply).fetchImpl);
    expect(r.kind).toBe("error");
    expect(r.kind === "error" && r.message).toContain(message);
  });
});

type OutlineClick = {
  type: string;
  target: OutlineEl;
  currentTarget: OutlineEl | null;
  bubbles: boolean;
  cancelable: boolean;
  defaultPrevented: boolean;
  button: number;
  detail: number;
  timeStamp: number;
  clientX: number;
  clientY: number;
  pageX: number;
  pageY: number;
  screenX: number;
  screenY: number;
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  isTrusted: boolean;
  stopped: boolean;
  preventDefault: () => void;
  stopPropagation: () => void;
  stopImmediatePropagation: () => void;
  getModifierState: () => boolean;
};

/** Enough of a document for React to mount `App` and for the test to read a badge or a drawer group. */
class OutlineEl {
  nodeType = 1;
  nodeName = "DIV";
  parentNode: OutlineEl | null = null;
  childNodes: OutlineEl[] = [];
  ownerDocument: OutlineEl | null = null;
  nodeValue: string | null = null;
  namespaceURI: string | null = "http://www.w3.org/1999/xhtml";
  attrs = new Map<string, string>();
  style = outlineStyle();
  private listeners = new Map<string, ((event: { type: string; target: OutlineEl }) => void)[]>();

  get tagName() {
    return this.nodeName;
  }
  get children() {
    return this.childNodes.filter((n) => n.nodeType === 1);
  }
  get firstChild() {
    return this.childNodes[0] ?? null;
  }
  get lastChild() {
    return this.childNodes[this.childNodes.length - 1] ?? null;
  }
  get nextSibling(): OutlineEl | null {
    const kids = this.parentNode?.childNodes ?? [];
    const i = kids.indexOf(this);
    return i >= 0 ? (kids[i + 1] ?? null) : null;
  }
  get previousSibling(): OutlineEl | null {
    const kids = this.parentNode?.childNodes ?? [];
    const i = kids.indexOf(this);
    return i > 0 ? (kids[i - 1] ?? null) : null;
  }
  get parentElement(): OutlineEl | null {
    return this.parentNode?.nodeType === 1 ? this.parentNode : null;
  }
  get isConnected(): boolean {
    return this.nodeType === 9 || (this.parentNode?.isConnected ?? false);
  }
  get className() {
    return this.attrs.get("class") ?? "";
  }
  set className(value: string) {
    this.attrs.set("class", value);
  }
  get id() {
    return this.attrs.get("id") ?? "";
  }
  set id(value: string) {
    this.attrs.set("id", value);
  }
  get textContent(): string {
    if (this.nodeType === 3) return this.nodeValue ?? "";
    return this.childNodes.map((c) => c.textContent).join("");
  }
  set textContent(value: string) {
    if (this.nodeType === 3) {
      this.nodeValue = value;
      return;
    }
    this.childNodes = [];
    if (value) this.appendChild(this.ownerDocument!.createText(value));
  }
  get classList() {
    const names = () => this.className.split(/\s+/).filter(Boolean);
    return {
      add: (...xs: string[]) => {
        this.className = [...new Set([...names(), ...xs])].join(" ");
      },
      remove: (...xs: string[]) => {
        const drop = new Set(xs);
        this.className = names().filter((n) => !drop.has(n)).join(" ");
      },
      contains: (n: string) => names().includes(n),
      toggle: (n: string) => {
        if (names().includes(n)) this.classList.remove(n);
        else this.classList.add(n);
      },
      get length() {
        return names().length;
      },
    };
  }
  setAttribute(name: string, value: string) {
    this.attrs.set(name, String(value));
  }
  getAttribute(name: string) {
    return this.attrs.has(name) ? this.attrs.get(name)! : null;
  }
  removeAttribute(name: string) {
    this.attrs.delete(name);
  }
  hasAttribute(name: string) {
    return this.attrs.has(name);
  }
  appendChild<T extends OutlineEl>(child: T): T {
    child.parentNode?.removeChild(child);
    child.parentNode = this;
    child.ownerDocument = this.nodeType === 9 ? this : this.ownerDocument;
    this.childNodes.push(child);
    return child;
  }
  insertBefore<T extends OutlineEl>(child: T, before: OutlineEl | null): T {
    if (!before) return this.appendChild(child);
    child.parentNode?.removeChild(child);
    child.parentNode = this;
    child.ownerDocument = this.nodeType === 9 ? this : this.ownerDocument;
    const i = this.childNodes.indexOf(before);
    if (i < 0) this.childNodes.push(child);
    else this.childNodes.splice(i, 0, child);
    return child;
  }
  removeChild<T extends OutlineEl>(child: T): T {
    const i = this.childNodes.indexOf(child);
    if (i >= 0) this.childNodes.splice(i, 1);
    child.parentNode = null;
    return child;
  }
  addEventListener(type: string, fn: (event: { type: string; target: OutlineEl }) => void) {
    const list = this.listeners.get(type) ?? [];
    list.push(fn);
    this.listeners.set(type, list);
  }
  removeEventListener(type: string, fn: (event: { type: string; target: OutlineEl }) => void) {
    const list = (this.listeners.get(type) ?? []).filter((f) => f !== fn);
    this.listeners.set(type, list);
  }
  click() {
    this.deliverClick({
      type: "click",
      target: this,
      currentTarget: null,
      bubbles: true,
      cancelable: true,
      defaultPrevented: false,
      button: 0,
      detail: 1,
      timeStamp: Date.now(),
      clientX: 0,
      clientY: 0,
      pageX: 0,
      pageY: 0,
      screenX: 0,
      screenY: 0,
      altKey: false,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      isTrusted: false,
      stopped: false,
      preventDefault() {
        this.defaultPrevented = true;
      },
      stopPropagation() {
        this.stopped = true;
      },
      stopImmediatePropagation() {
        this.stopped = true;
      },
      getModifierState() {
        return false;
      },
    });
  }
  private deliverClick(event: OutlineClick) {
    if (event.stopped) return;
    event.currentTarget = this;
    for (const fn of [...(this.listeners.get("click") ?? [])]) fn(event);
    this.parentNode?.deliverClick(event);
  }
  getBoundingClientRect() {
    return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) };
  }
  contains(node: OutlineEl | null): boolean {
    let cur: OutlineEl | null = node;
    while (cur) {
      if (cur === this) return true;
      cur = cur.parentNode;
    }
    return false;
  }
  focus() {
    return undefined;
  }
  blur() {
    return undefined;
  }
  querySelector(selector: string) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
  querySelectorAll(selector: string): OutlineEl[] {
    const steps = selector.trim().split(/\s+/);
    let matched = outlineDescendants(this).filter((el) => outlineMatches(el, steps[0] ?? ""));
    for (const step of steps.slice(1)) {
      const next: OutlineEl[] = [];
      for (const el of matched) {
        for (const desc of outlineDescendants(el)) {
          if (outlineMatches(desc, step)) next.push(desc);
        }
      }
      matched = next;
    }
    return matched;
  }
  closest(selector: string): OutlineEl | null {
    if (this.nodeType === 1 && outlineMatches(this, selector)) return this;
    return this.parentNode?.closest(selector) ?? null;
  }
  createElement(name: string) {
    const el = new OutlineEl();
    el.nodeName = name.toUpperCase();
    el.ownerDocument = this.nodeType === 9 ? this : this.ownerDocument;
    return el;
  }
  createElementNS(_ns: string, name: string) {
    return this.createElement(name);
  }
  createText(value: string) {
    const text = new OutlineEl();
    text.nodeType = 3;
    text.nodeName = "#text";
    text.nodeValue = value;
    text.ownerDocument = this.nodeType === 9 ? this : this.ownerDocument;
    return text;
  }
  getElementById(id: string) {
    return this.querySelector(`#${id}`);
  }
}

function outlineStyle() {
  const values = new Map<string, string>();
  const api = {
    setProperty(name: string, value: string) {
      values.set(name, value);
    },
    removeProperty(name: string) {
      values.delete(name);
    },
    getPropertyValue(name: string) {
      return values.get(name) ?? "";
    },
    get cssText() {
      return [...values.entries()].map(([k, v]) => `${k}: ${v}`).join("; ");
    },
    set cssText(value: string) {
      values.clear();
      for (const part of value.split(";")) {
        const [k, v] = part.split(":");
        if (k && v) values.set(k.trim(), v.trim());
      }
    },
  };
  return new Proxy(api, {
    get(target, prop) {
      if (typeof prop !== "string") return undefined;
      if (prop in target) return target[prop as keyof typeof target];
      return values.get(prop) ?? "";
    },
    set(_target, prop, value) {
      if (typeof prop === "string") values.set(prop, String(value));
      return true;
    },
  });
}

function outlineDescendants(root: OutlineEl): OutlineEl[] {
  const out: OutlineEl[] = [];
  const walk = (node: OutlineEl) => {
    for (const child of node.childNodes) {
      if (child.nodeType === 1) out.push(child);
      walk(child);
    }
  };
  walk(root);
  return out;
}

function outlineMatches(el: OutlineEl, part: string): boolean {
  if (part === "*") return el.nodeType === 1;
  let rest = part;
  let tag: string | null = null;
  if (rest[0] !== "." && rest[0] !== "#") {
    const found = /^[a-zA-Z][\w-]*/.exec(rest);
    if (found) {
      tag = found[0].toUpperCase();
      rest = rest.slice(found[0].length);
    }
  }
  if (tag && el.nodeName !== tag) return false;
  const classes: string[] = [];
  let id: string | null = null;
  for (const piece of rest.matchAll(/([.#])([\w-]+)/g)) {
    if (piece[1] === ".") classes.push(piece[2] ?? "");
    else id = piece[2] ?? null;
  }
  if (id && el.id !== id) return false;
  const have = new Set(el.className.split(/\s+/).filter(Boolean));
  return classes.every((c) => have.has(c));
}

function installOutlineDocument(): OutlineEl {
  const doc = new OutlineEl();
  doc.nodeType = 9;
  doc.nodeName = "#document";
  doc.ownerDocument = doc;
  const html = doc.createElement("html");
  const head = doc.createElement("head");
  const body = doc.createElement("body");
  doc.appendChild(html);
  html.appendChild(head);
  html.appendChild(body);
  const storage = new Map<string, string>();
  const localStorage = {
    getItem: (key: string) => (storage.has(key) ? storage.get(key)! : null),
    setItem: (key: string, value: string) => {
      storage.set(key, String(value));
    },
    removeItem: (key: string) => {
      storage.delete(key);
    },
    clear: () => storage.clear(),
    key: (index: number) => [...storage.keys()][index] ?? null,
    get length() {
      return storage.size;
    },
  };
  const win = {
    document: doc,
    console,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    queueMicrotask,
    localStorage,
    sessionStorage: localStorage,
    innerWidth: 1200,
    innerHeight: 800,
    devicePixelRatio: 1,
    location: { protocol: "http:", href: "http://127.0.0.1/", search: "", hostname: "127.0.0.1" },
    navigator: { userAgent: "vitest" },
    getComputedStyle: () => outlineStyle(),
    requestAnimationFrame: (cb: (time: number) => void) => setTimeout(() => cb(Date.now()), 0),
    cancelAnimationFrame: (id: ReturnType<typeof setTimeout>) => clearTimeout(id),
    addEventListener() {
      return undefined;
    },
    removeEventListener() {
      return undefined;
    },
    getSelection: () => ({ removeAllRanges() { return undefined; } }),
    matchMedia: () => ({
      matches: false,
      addEventListener() {
        return undefined;
      },
      removeEventListener() {
        return undefined;
      },
    }),
    scrollTo() {
      return undefined;
    },
    HTMLIFrameElement: class {},
    ResizeObserver: class {
      observe() {
        return undefined;
      }
      unobserve() {
        return undefined;
      }
      disconnect() {
        return undefined;
      }
    },
  };
  const g = globalThis as unknown as Record<string, unknown>;
  for (const [key, value] of [
    ["window", win],
    ["document", doc],
    ["localStorage", localStorage],
    ["getComputedStyle", win.getComputedStyle],
    ["requestAnimationFrame", win.requestAnimationFrame],
    ["cancelAnimationFrame", win.cancelAnimationFrame],
    ["ResizeObserver", win.ResizeObserver],
    ["IS_REACT_ACT_ENVIRONMENT", true],
  ] as const) {
    try {
      g[key] = value;
    } catch {
      Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
    }
  }
  if ((globalThis as { window?: unknown }).window !== win) {
    throw new Error("window was not installed");
  }
  Object.assign(doc, {
    documentElement: html,
    head,
    body,
    defaultView: win,
    scrollingElement: html,
    compatMode: "CSS1Compat",
    readyState: "complete",
    visibilityState: "visible",
    hidden: false,
    activeElement: body,
    createTextNode: (value: string) => doc.createText(value),
    elementFromPoint: () => null,
  });
  return doc;
}

type OutlineDoc = OutlineEl & {
  body: OutlineEl;
  documentElement: OutlineEl;
};

function outlineRoadmap(view: string) {
  return {
    version: 1,
    fingerprint: view,
    view_fingerprint: view,
    nodes: [
      {
        id: "M0.2",
        node_key: "nk-m02",
        type: "task",
        title: view === "1" ? "Roadmap validator in CI" : "Roadmap validator reloaded",
        status: "In Progress",
        parent_id: null,
        dependencies: [],
        sibling_order: 0,
      },
    ],
    registry: {},
    registry_by_node: {},
    tree: [{ id: "M0.2", outline_depth: 0, row_index: 0 }],
    dependency_depths: { "M0.2": 0 },
    dependency_spans: { "M0.2": 1 },
    edges: [],
    ordered_ids: ["M0.2"],
    row_depths: [0],
    git_enrichment: {},
    dependency_inheritance: {},
    activity: {},
  };
}

function outlineSnapshot(phase: "running" | "held") {
  return {
    schema: 2,
    leaves: {
      "M0.2": {
        status: "running",
        claim: null,
        workers:
          phase === "running"
            ? [{ id: "w-1", harness: "claude", model: "opus", status: "running", pid_alive: true }]
            : [],
        worktrees: [],
        reviews: [],
        holds: phase === "held" ? [{ source: "hold_list", id: "M0.2", reason: "wait" }] : [],
      },
    },
    leafless_workers: [],
  };
}

/** The base fetch is not awaited, so this stays pending after the roadmap body is ready. */
const ORCH_HOLD_MS = 250;

describe("roadmap load shows an outline badge before the drawer opens", () => {
  // The base already calls fetchOrchestration on every load. Holding that response
  // makes the outline title show first, with no badge, unless the load waits for it.
  it("shows the leaf badge with the roadmap text, and the reloaded badge with the reloaded text, drawer closed", async () => {
    const doc = installOutlineDocument() as OutlineDoc;
    localStorage.setItem("pmGanttRefreshSec", "1");
    let view = "1";
    let phase: "running" | "held" = "running";
    let fingerprintCalls = 0;
    const previousFetch = globalThis.fetch;
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/orchestration")) {
        const body = outlineSnapshot(phase);
        return new Promise((resolve) => {
          setTimeout(() => resolve(json(body)), ORCH_HOLD_MS);
        });
      }
      if (url.includes("/api/roadmap/fingerprint")) {
        fingerprintCalls += 1;
        return json({ fingerprint: view, view_fingerprint: view });
      }
      if (url.includes("/api/roadmap")) return json(outlineRoadmap(view));
      if (url.includes("/api/repo")) return json({ repo_root: "/repo", repo_id: "repo-1" });
      return json({}, 404);
    }) as typeof fetch;

    const root = await mountOutlineApp(doc);
    const badge = () => doc.querySelector("button.worker-stall-badge")?.textContent ?? null;
    const drawerOpen = () => doc.textContent.includes("Workers on each leaf");
    const firstBadgeWith = async (title: string) => {
      const start = Date.now();
      while (Date.now() - start < 4000) {
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 15));
        });
        if (doc.body.textContent.includes(title)) return badge();
      }
      throw new Error(`never saw ${title}; outline text: ${doc.body.textContent.slice(0, 400)}`);
    };
    try {
      expect(await firstBadgeWith("Roadmap validator in CI")).toBe("running");
      expect(drawerOpen()).toBe(false);
      let settled = -1;
      const settleStart = Date.now();
      while (Date.now() - settleStart < 1000) {
        if (badge() === "running" && fingerprintCalls === settled && settled > 0) break;
        settled = fingerprintCalls;
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 40));
        });
      }
      expect(badge()).toBe("running");
      view = "2";
      phase = "held";
      expect(await firstBadgeWith("Roadmap validator reloaded")).toBe("held");
      expect(drawerOpen()).toBe(false);
    } finally {
      await act(async () => {
        root.unmount();
      });
      globalThis.fetch = previousFetch;
    }
  }, 15000);
});

describe("the open drawer lists groups in outline row order", () => {
  it("shows M0.1, M0.2, M0.3, M2, M0.10, No leaf when the node array is the Gantt order", async () => {
    const doc = installOutlineDocument() as OutlineDoc;
    const previousFetch = globalThis.fetch;
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    const rowIds = ["M0.1", "M0.2", "M0.3", "M2", "M0.10"];
    const ganttIds = ["M0.1", "M0.3", "M2", "M0.2", "M0.10"];
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/orchestration")) {
        return json({
          schema: 2,
          leaves: Object.fromEntries(rowIds.map((id) => [id, emptyLeaf()])),
          leafless_workers: [worker({ id: "w-9" })],
        });
      }
      if (url.includes("/api/roadmap/fingerprint")) return json({ fingerprint: "order", view_fingerprint: "order" });
      if (url.includes("/api/roadmap")) {
        const node = (id: string, i: number) => ({
          id,
          node_key: `nk-${id}`,
          type: "task",
          title: `title ${id}`,
          status: "In Progress",
          parent_id: null,
          dependencies: [],
          sibling_order: i,
        });
        return json({
          version: 1,
          fingerprint: "order",
          view_fingerprint: "order",
          nodes: ganttIds.map((id, i) => node(id, i)),
          registry: {},
          registry_by_node: {},
          tree: rowIds.map((id, i) => ({ id, outline_depth: 0, row_index: i })),
          dependency_depths: Object.fromEntries(rowIds.map((id) => [id, 0])),
          dependency_spans: Object.fromEntries(rowIds.map((id) => [id, 1])),
          edges: [],
          ordered_ids: rowIds,
          row_depths: rowIds.map(() => 0),
          git_enrichment: {},
          dependency_inheritance: {},
          activity: {},
        });
      }
      if (url.includes("/api/repo")) return json({ repo_root: "/repo", repo_id: "repo-1" });
      return json({}, 404);
    }) as typeof fetch;

    const root = await mountOutlineApp(doc);
    const groupIds = () =>
      doc.querySelectorAll("h4.worker-section-title").map((heading) => {
        const id = heading.querySelector("button.modal-dep-id-link") ?? heading.querySelector("code");
        if (id) return id.textContent;
        return heading.textContent.includes("No leaf") ? "No leaf" : "";
      });
    try {
      const start = Date.now();
      let opened = false;
      while (Date.now() - start < 4000) {
        await act(async () => {
          await new Promise((resolve) => setTimeout(resolve, 20));
        });
        const button = doc.querySelectorAll("button").find((b) => b.textContent === "Orchestration");
        if (button && !opened) {
          await act(async () => {
            button.click();
          });
          opened = true;
        }
        if (opened && groupIds().includes("No leaf")) break;
      }
      expect(groupIds()).toEqual(["M0.1", "M0.2", "M0.3", "M2", "M0.10", "No leaf"]);
    } finally {
      await act(async () => {
        root.unmount();
      });
      globalThis.fetch = previousFetch;
    }
  }, 15000);
});

async function mountOutlineApp(doc: OutlineDoc) {
  const { createRoot } = await import("react-dom/client");
  const { default: App } = await import("./App");
  const host = doc.createElement("div");
  doc.body.appendChild(host);
  const root = createRoot(host as unknown as Element);
  await act(async () => {
    root.render(createReactElement(App));
  });
  return root;
}

describe("pollOrchestration (15 s, only while open)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("open: one load; +15 s: one more; closed: none", async () => {
    const { requests, fetchImpl } = recordingFetch(respond("Not Found", 404));
    const stop = pollOrchestration(() => void loadOrchestration(fetchImpl));
    expect(requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(14_999);
    expect(requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(requests).toEqual(["GET /api/orchestration", "GET /api/orchestration"]);
    stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(requests).toHaveLength(2);
  });
});

describe("copyCommand", () => {
  it.each([
    ["worker status", "w-0001", "specy-road worker status w-0001"],
    ["worker open", "w_1.2", "specy-road worker open w_1.2"],
    ["review status", "M17.3", "specy-road review status M17.3"],
    ["worker status", "it's a $(rm -rf ~)", `specy-road worker status 'it'\\''s a $(rm -rf ~)'`],
    ["review status", "M1;ls", "specy-road review status 'M1;ls'"],
  ] as const)("%s %s", (kind, id, expected) => {
    expect(copyCommand(kind, id)).toBe(expected);
  });
});

/** Every import or re-export clause the source takes from `../api`; a dynamic import is `import()`. */
function apiImports(source: string): string[] {
  const re = /\b(?:import|export)\b([^;]*?)\bfrom\s*["']\.\.\/api(?:\.ts)?["']|\bimport\s*\(\s*["']\.\.\/api(?:\.ts)?["']/g;
  return [...source.matchAll(re)].map((m) => (m[1] ?? "import()").replace(/\s+/g, " ").trim());
}

describe("OrchestrationDrawer.tsx imports from api.ts", () => {
  it("only fetchOrchestration", () => {
    expect(apiImports(drawerSource)).toEqual(["{ fetchOrchestration }"]);
  });

  it.each([
    [`import { fetchOrchestration, patchNode } from "../api";`, "{ fetchOrchestration, patchNode }"],
    [`import * as api from "../api";`, "* as api"],
    [`import type {\n  Fingerprint,\n} from "../api.ts";`, "type { Fingerprint, }"],
    [`const m = await import("../api");`, "import()"],
  ])("the check sees %s", (source, clause) => {
    expect(apiImports(source)).toEqual([clause]);
  });
});
