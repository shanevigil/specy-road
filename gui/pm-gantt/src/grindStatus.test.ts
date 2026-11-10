/// <reference types="node" />
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import modalSource from "./components/StatusModal.tsx?raw";
import mockJson from "./fixtures/grind_status_mock.json";
import {
  applyGrindStatus,
  grindStatusSections,
  grindStatusUrl,
  lastUpdatedText,
  loadFailureText,
  loadGrindStatus,
  pollGrindStatus,
  requestScope,
  type GrindScope,
  type GrindStatusLoad,
  type GrindStatusReport,
  type GrindStatusState,
} from "./grindStatus";

const mock = mockJson as unknown as GrindStatusReport;
/** The one stylesheet `main.tsx` loads; read from disk because vitest turns CSS imports into "". */
const shippedCss = readFileSync(new URL("./index.css", import.meta.url), "utf8");
const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

function recordingFetch(reply: (url: string) => Promise<Response>) {
  const requests: string[] = [];
  const fetchImpl = ((input: RequestInfo | URL) => {
    requests.push(String(input));
    return reply(String(input));
  }) as typeof fetch;
  return { requests, fetchImpl };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const A: GrindScope = { until: "M1", under: "" };
const B: GrindScope = { until: "", under: "M2" };

describe("loadGrindStatus", () => {
  it("200 is the report, the scope in the query", async () => {
    const { requests, fetchImpl } = recordingFetch(() => Promise.resolve(json(mock, 200)));
    expect(await loadGrindStatus(fetchImpl, { until: " M1 ", under: "M2" })).toEqual({ kind: "ok", report: mock });
    expect(await loadGrindStatus(fetchImpl, { until: "", under: "" })).toEqual({ kind: "ok", report: mock });
    expect(requests).toEqual(["/api/grind-status?until=M1&under=M2", "/api/grind-status"]);
  });

  it("404 is unavailable with its text; 400 is refused with the detail unchanged", async () => {
    const r404 = await loadGrindStatus(
      recordingFetch(() => Promise.resolve(json({ detail: "no API route" }, 404))).fetchImpl,
      A,
    );
    expect(r404).toEqual({ kind: "unavailable" });
    expect(loadFailureText(r404 as Exclude<GrindStatusLoad, { kind: "ok" }>)).toBe(
      "the server does not provide the status",
    );
    const detail = "grind-session --status needs a scope: pass --until NODE or --under NODE, or start a session";
    const r400 = await loadGrindStatus(recordingFetch(() => Promise.resolve(json({ detail }, 400))).fetchImpl, A);
    expect(r400).toEqual({ kind: "refused", detail });
    expect(loadFailureText(r400 as Exclude<GrindStatusLoad, { kind: "ok" }>)).toBe(detail);
  });

  it("never throws: a network failure is an error", async () => {
    const r = await loadGrindStatus(recordingFetch(() => Promise.reject(new TypeError("offline"))).fetchImpl, A);
    expect(r).toEqual({ kind: "error", message: "TypeError: offline" });
  });
});

describe("pollGrindStatus", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("loads at open and every 60 s; none after stop", async () => {
    let loads = 0;
    const poll = pollGrindStatus(async () => void (loads += 1), 60);
    expect(loads).toBe(1);
    await vi.advanceTimersByTimeAsync(59_999);
    expect(loads).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(loads).toBe(2);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(loads).toBe(3);
    poll.stop();
    await vi.advanceTimersByTimeAsync(600_000);
    expect(loads).toBe(3);
  });

  it("Off loads once at open, then never", async () => {
    let loads = 0;
    pollGrindStatus(async () => void (loads += 1), 0);
    await vi.advanceTimersByTimeAsync(600_000);
    expect(loads).toBe(1);
  });

  it("a tick while a load is running is skipped", async () => {
    const slow = deferred<void>();
    let loads = 0;
    const poll = pollGrindStatus(() => {
      loads += 1;
      return loads === 1 ? slow.promise : Promise.resolve();
    }, 30);
    await vi.advanceTimersByTimeAsync(90_000);
    expect(loads).toBe(1);
    slow.resolve();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(loads).toBe(2);
    poll.stop();
  });

  it("refresh now loads at once and restarts the interval", async () => {
    let loads = 0;
    const poll = pollGrindStatus(async () => void (loads += 1), 60);
    await vi.advanceTimersByTimeAsync(50_000);
    poll.refreshNow();
    expect(loads).toBe(2);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(loads).toBe(2);
    await vi.advanceTimersByTimeAsync(50_000);
    expect(loads).toBe(3);
    poll.stop();
  });
});

describe("scope change and a failed load", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("a late answer for the earlier scope never replaces the new report; a failure keeps it beside the error", async () => {
    const reportA = { ...mock, goal: "M1", scope: { ...mock.scope, rule: "until M1" } };
    const reportB = { ...mock, goal: "M2", scope: { ...mock.scope, rule: "under M2: its subtree" } };
    const pending = new Map<string, ReturnType<typeof deferred<Response>>>();
    const { fetchImpl } = recordingFetch((url) => {
      const d = deferred<Response>();
      pending.set(url, d);
      return d.promise;
    });
    let state: GrindStatusState = requestScope({ requested: "", report: null, error: null }, A);
    let scope = A;
    const poll = pollGrindStatus(async () => {
      const requested = scope;
      const r = await loadGrindStatus(fetchImpl, requested);
      state = applyGrindStatus(state, grindStatusUrl(requested), r);
    }, 60);
    scope = B;
    state = requestScope(state, B);
    poll.refreshNow();
    pending.get(grindStatusUrl(B))!.resolve(json(reportB, 200));
    await vi.advanceTimersByTimeAsync(0);
    pending.get(grindStatusUrl(A))!.resolve(json(reportA, 200));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.report?.goal).toBe("M2");
    expect(state.error).toBeNull();

    await vi.advanceTimersByTimeAsync(60_000);
    pending.get(grindStatusUrl(B))!.resolve(json({ detail: "no node M2" }, 400));
    await vi.advanceTimersByTimeAsync(0);
    expect(state.report?.goal).toBe("M2");
    expect(state.report?.scope.rule).toBe("under M2: its subtree");
    expect(state.error).toBe("no node M2");
    poll.stop();
  });
});

describe("lastUpdatedText", () => {
  it("the time of generated_at and its age, which grows after a failed load", () => {
    const now = new Date(Date.parse(mock.generated_at) + 12_000);
    const time = new Date(mock.generated_at).toLocaleTimeString();
    expect(lastUpdatedText(mock, now)).toBe(`Last updated ${time} (12 s ago)`);
    const failed = applyGrindStatus({ requested: "u", report: mock, error: null }, "u", { kind: "unavailable" });
    expect(failed.error).toBe("the server does not provide the status");
    expect(lastUpdatedText(failed.report!, new Date(now.getTime() + 180_000))).toBe(
      `Last updated ${time} (3 min ago)`,
    );
  });
});

describe("grindStatusSections", () => {
  it("every section in the CLI's order, the server's text unchanged", () => {
    const sections = grindStatusSections(mock);
    expect(sections.map((s) => s.title)).toEqual([
      "Held (1)",
      "Active (1)",
      "Ready (1)",
      "Waiting (1)",
      "Finished, awaiting merge (1)",
      "Not pickable (1)",
      "Estimate",
      "Decisions waiting on a person",
      "Open brainstorm sessions (1)",
      "Live sessions (1)",
      "Missing",
    ]);
    const byTitle = Object.fromEntries(sections.map((s) => [s.title, s.lines]));
    expect(byTitle["Decisions waiting on a person"]).toEqual([
      "D1 [decision] node M1.4 (shared ledger), needed-by -",
      "  Pick the parser",
      "  why now: M1.1 cannot start without it",
      "  options: yaml (one more dependency); json (no comments)",
      "  recommendation: yaml — people edit these files by hand",
      "  default if unanswered: json after the deadline",
      "  pros/cons: not recorded: the decisions schema has no field for them",
      "outside scope: D2 node M2.1: Somewhere else",
      "held M1.2: open gate M1.20 among its unmet dependencies",
      "  next: `specy-road set-gate-status M1.20 --status Complete`",
      "  no options recorded (not a ledger entry)",
    ]);
    expect(byTitle["Missing"]).toEqual([
      "D1: needed_by",
      "work/brainstorm-broken.yaml: unreadable: cannot read work/brainstorm-broken.yaml: while parsing a flow node",
    ]);
    expect(byTitle["Active (1)"]).toEqual(["M1.3 Leaf M1.3: review waiting; worker w-0001 (claude-code, starting)"]);
  });
});

describe("StatusModal source", () => {
  it("styles only with classes the loaded stylesheet defines, and shows section text with its line breaks", () => {
    const classes = [...modalSource.matchAll(/className="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/));
    expect(classes.length).toBeGreaterThan(0);
    for (const c of classes) expect(shippedCss, c).toContain(`.${c}`);
    expect(modalSource).toContain('whiteSpace: "pre-wrap"');
    expect(modalSource).toContain('s.lines.join("\\n")');
  });

  it("applies an Until or Under edit from the change handler, not on blur or Enter", () => {
    expect(modalSource).toMatch(/onChange=\{\(e\) => changeScope\(key, e\.target\.value\)\}/);
    expect(modalSource).not.toMatch(/onBlur|onKeyDown/);
  });
});
