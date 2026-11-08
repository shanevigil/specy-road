import { describe, expect, it } from "vitest";
import mockJson from "./fixtures/orchestration_snapshot_mock.json";
import {
  buildOrchestrationView,
  leafBadge,
  optionalKeys,
  requiredKeys,
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
    const w = scratch.leaves["k-blocked"].workers[0];
    w.stauts = w.status;
    delete w.status;
    delete scratch.leafless_workers;
    const { unlisted, missing } = contractProblems(scratch);
    expect(unlisted).toEqual(["leaves.*.workers[].stauts"]);
    expect(missing).toEqual(["leafless_workers", "leaves.k-blocked.workers[0].status"]);
  });

  // Each field is still present on a sibling entry, so only a per-object
  // check sees it missing.
  it.each([
    ["leaves", "k-blocked", "workers", 0, "harness"],
    ["leaves", "k-unknown", "workers", 1, "pid_alive"],
    ["leaves", "k-blocked", "worktrees", 1, "dirty"],
    ["leaves", "k-held-list", "reviews", 0, "fresh_for_head"],
    ["leaves", "k-exec-blocked", "claim", "branch"],
    ["leaves", "k-held-gate"],
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
        ? ["claim", "workers", "worktrees", "reviews"].map((k) => `${at}.${k}`)
        : [at];
    expect(contractProblems(scratch)).toEqual({ unlisted: [], missing: expected });
  });

  it("the mock covers every worker status", () => {
    const all = [...Object.values(mock.leaves).flatMap((l) => l.workers), ...mock.leafless_workers];
    expect(new Set(all.map((w) => w.status))).toEqual(
      new Set(["claimed", "running", "exited_ok", "exited_failed", "abandoned", "unknown"]),
    );
  });
});

const worker = (over: Partial<SnapshotWorker> = {}): SnapshotWorker => ({
  id: "w-1",
  harness: "claude",
  model: "opus",
  status: "exited_ok",
  pid_alive: false,
  started_at: "2026-11-08T10:00:00Z",
  ended_at: null,
  ...over,
});

const emptyLeaf = (): SnapshotLeaf => ({ claim: null, workers: [], worktrees: [], reviews: [] });

/** Each badge candidate alone, in M17.1's precedence order. */
const CANDIDATES: [string, Partial<SnapshotLeaf>, string][] = [
  ["blocked", { gate: { state: "blocked", approvals: 0, blocks: 2, fresh_for_head: true } }, "blocked (2)"],
  ["held", { holds: [{ source: "hold_list", id: "M1", reason: "r" }] }, "held"],
  ["exited_failed", { workers: [worker({ status: "exited_failed" })] }, "exited_failed"],
  ["stalled", { workers: [worker({ flags: ["stalled"] })] }, "stalled"],
  ["running", { workers: [worker({ status: "running" })] }, "running"],
  ["ready", { ready: { commit: "c", model: "m", at: "2026-11-08T11:00:00Z" } }, "READY awaiting review"],
  ["approved", { gate: { state: "approved", approvals: 2, blocks: 0, fresh_for_head: true } }, "approved"],
  ["claimed", { claim: { codename: "c", branch: "b", registered_at: "2026-11-08T09:00:00Z" } }, "claimed"],
  ["abandoned", { workers: [worker({ status: "abandoned" })] }, "abandoned"],
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
    const ws = [worker({ id: "a", status: "running" }), worker({ id: "b", status: "exited_failed" })];
    expect(leafBadge(merge({ workers: ws }))?.kind).toBe("exited_failed");
    expect(leafBadge(merge({ workers: [...ws].reverse() }))?.kind).toBe("exited_failed");
  });
});

const outlineNode = (id: string, node_key: string, title = `title ${id}`): OutlineNodeRef => ({
  id,
  node_key,
  title,
});

describe("buildOrchestrationView", () => {
  const outline = [
    outlineNode("M9.3", "k-held-gate"),
    outlineNode("M9.4", "k-held-list"),
    outlineNode("M10", "k-blocked"),
    outlineNode("M11", "k-no-state"),
  ];

  it("orders groups by outline, then unlisted keys by key, then No leaf; badges from the mock", () => {
    const view = buildOrchestrationView(mock, outline, NOW);
    expect(view.map((g) => [g.displayId, g.title, g.badge?.text ?? null])).toEqual([
      ["M9.3", "title M9.3", "held"],
      ["M9.4", "title M9.4", "held"],
      ["M10", "title M10", "blocked (1)"],
      ["k-exec-blocked", "—", "blocked (1)"],
      ["k-unknown", "—", "claimed"],
      ["", "No leaf", null],
    ]);
  });

  it("keeps numeric-looking display ids in outline order, not sorted", () => {
    const snap: OrchestrationSnapshot = {
      schema: 1,
      leaves: { a: emptyLeaf(), b: emptyLeaf(), c: emptyLeaf() },
      leafless_workers: [],
    };
    const view = buildOrchestrationView(
      snap,
      [outlineNode("M1.10", "c"), outlineNode("M1.2", "a"), outlineNode("2", "b")],
      NOW,
    );
    expect(view.map((g) => g.displayId)).toEqual(["M1.10", "M1.2", "2"]);
  });

  it("formats mock rows: ages from now, null account empty, stale review, two worktrees, flags verbatim", () => {
    const g = buildOrchestrationView(mock, outline, NOW).find((x) => x.key === "k-blocked")!;
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
      ["dirty", "3", "0"],
      ["clean", "0", "2"],
    ]);
    expect(g.reviews[0].fresh).toBe("stale");
    expect(g.gate).toEqual({ state: "blocked", approvals: "0", blocks: "1", fresh: "stale" });
  });

  it("renders explicit unknown as unknown and a null hold reason as —", () => {
    const view = buildOrchestrationView(mock, outline, NOW);
    const u = view.find((x) => x.key === "k-unknown")!;
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
    const held = view.find((x) => x.key === "k-held-gate")!;
    expect(held.holds).toEqual([{ source: "gate", id: "M9.3", reason: "—" }]);
    const ex = view.find((x) => x.key === "k-exec-blocked")!;
    expect(ex.ready?.blockedOn).toEqual(["A2: needs a path outside the touch zones"]);
  });

  it("a schema 1 snapshot (no optional fields) shows — and an empty account, never false, 0 or clean", () => {
    const snap: OrchestrationSnapshot = {
      schema: 1,
      leaves: {
        k: {
          claim: { codename: "c", branch: "b", registered_at: "2026-11-08T11:59:30Z" },
          workers: [worker({ status: "running", pid_alive: true })],
          worktrees: [{ path: "p", branch: "b", dirty: false }],
          reviews: [{ model: "m", verdict: "approve", commit: "c", fresh_for_head: true }],
        },
      },
      leafless_workers: [],
    };
    const [g] = buildOrchestrationView(snap, [outlineNode("M1", "k")], NOW);
    expect(g.badge).toEqual({ kind: "running", text: "running" });
    expect(g.claim?.registered).toBe("now");
    expect(g.workers[0]).toMatchObject({ account: "", lastActivity: "—", flags: [], ended: "—" });
    expect(g.worktrees[0]).toEqual({ path: "p", branch: "b", dirty: "clean", ahead: "—", behind: "—" });
    expect([g.ready, g.gate, g.holds]).toEqual([null, null, []]);
  });

  it("an empty snapshot has no groups; leafless workers alone make one No leaf group", () => {
    const empty: OrchestrationSnapshot = { schema: 1, leaves: {}, leafless_workers: [] };
    expect(buildOrchestrationView(empty, [outlineNode("M1", "k")], NOW)).toEqual([]);
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
