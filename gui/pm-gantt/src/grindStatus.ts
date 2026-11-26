/**
 * Grind status (M17.14): `specy-road grind-session --status --json`'s object,
 * served unchanged by `GET /api/grind-status?until=&under=` (M22.68's builder).
 *
 * Pure helpers only: the loader takes the fetch, the poll owns its timer, and
 * every text helper takes the clock, so vitest drives them without a DOM. The
 * section text follows the CLI's `render_text` line for line; every string
 * the server sends is shown as sent.
 */

export type GrindScope = { until: string; under: string };

export type GrindWorker = { id: string; harness: string; state: string; lease: string | null; flags: string[] };
export type GrindReason = { kind: string; reason: string; next: string[] };
export type GrindLeaf = { id: string; title: string };
/**
 * M17.15, on each claimed leaf whose review was evaluated: the commit under review, whether the PM can approve
 * over its blocks, and what that decision would settle. Optional: a server from before M17.15 sends none.
 */
export type GrindApprovalOffer = { commit?: string; can_approve_over_block?: boolean; settles?: string[] };
export type GrindHeld = GrindLeaf & GrindApprovalOffer & {
  claimed: boolean;
  reasons: GrindReason[];
  state?: string | null;
  error?: string;
  worker?: GrindWorker;
};
export type GrindActive = GrindLeaf & GrindApprovalOffer & {
  claimed: boolean;
  status: string | null;
  review: string | null;
  review_error?: string;
  note?: string;
  worker?: GrindWorker;
};
export type GrindLedgerEntry = {
  id: string;
  kind: string;
  node: string;
  summary: string | null;
  why_now: string | null;
  options: { label: string; effect: string }[] | null;
  recommendation: string | null;
  recommendation_reason: string | null;
  default_if_unanswered: string | null;
  needed_by: string | null;
  pros_cons: string;
  ledger: string;
};

/** A decision made in the PM GUI that no coordinator has processed yet (M17.15). */
export type GrindGuiPending = { id: string; node: string; kind: string; answer: string; next: string[] };

export type GrindStatusReport = {
  generated_at: string;
  source: { branch: string | null; head: string | null; fetched: boolean };
  goal: string;
  scope: { rule: string; until: string | null; under: string | null; leaves: string[] };
  totals: Record<string, number>;
  held: GrindHeld[];
  active: GrindActive[];
  ready: GrindLeaf[];
  waiting: (GrindLeaf & { waiting_on: string[] })[];
  awaiting_merge: (GrindLeaf & { reason: string })[];
  not_pickable: (GrindLeaf & { reason: string })[];
  estimate: {
    method: string;
    inputs: {
      n: number;
      first: string | null;
      last: string | null;
      recent: number;
      window_days: number;
      minimum: number;
      minimum_span_hours: number;
      remaining: number;
      completions: { id: string; at: string }[];
    };
    earliest: string | null;
    latest: string | null;
    reason: string | null;
  };
  decisions: {
    ledger: GrindLedgerEntry[];
    ledger_outside_scope: { id: string; node: string | null; summary: string | null }[];
    held: (GrindReason & { node: string; options: string })[];
    /** Optional: a server from before M17.15 sends none, and the modal shows no section for it. */
    gui_pending?: GrindGuiPending[];
  };
  sessions: {
    brainstorm: { slug: string; mode: string; ideas: number }[];
    presence: {
      agent: string;
      branch: string | null;
      note: string | null;
      expires: string;
      stale_reason: string | null;
    }[];
  };
  missing: { record: string; field: string }[];
};

/* ---------- load ---------- */

export type GrindStatusLoad =
  | { kind: "ok"; report: GrindStatusReport }
  /** 404: a server from before M17.14. */
  | { kind: "unavailable" }
  /** 400: the CLI's exit-2 cases (no scope, unknown node); `detail` as the server sent it. */
  | { kind: "refused"; detail: string }
  | { kind: "error"; message: string };

export function grindStatusUrl(scope: GrindScope): string {
  const q = new URLSearchParams();
  if (scope.until.trim()) q.set("until", scope.until.trim());
  if (scope.under.trim()) q.set("under", scope.under.trim());
  const s = q.toString();
  return s ? `/api/grind-status?${s}` : "/api/grind-status";
}

/** One GET of `/api/grind-status`; never throws. */
export async function loadGrindStatus(fetchImpl: typeof fetch, scope: GrindScope): Promise<GrindStatusLoad> {
  try {
    const r = await fetchImpl(grindStatusUrl(scope));
    if (r.status === 404) return { kind: "unavailable" };
    if (r.status === 400) {
      const body = (await r.json()) as { detail?: unknown };
      return { kind: "refused", detail: String(body.detail) };
    }
    if (!r.ok) return { kind: "error", message: `grind status: HTTP ${r.status}` };
    return { kind: "ok", report: (await r.json()) as GrindStatusReport };
  } catch (e: unknown) {
    return { kind: "error", message: String(e) };
  }
}

/** The text shown for a load that is not a report. */
export function loadFailureText(load: Exclude<GrindStatusLoad, { kind: "ok" }>): string {
  if (load.kind === "unavailable") return "the server does not provide the status";
  if (load.kind === "refused") return load.detail;
  return load.message;
}

/* ---------- view state: the report kept, the error beside it ---------- */

export type GrindStatusState = {
  /** The scope currently requested, as `grindStatusUrl` writes it. */
  requested: string;
  /** The last good report, with its own returned goal and scope. */
  report: GrindStatusReport | null;
  /** The last load's failure text; null after a good load. */
  error: string | null;
};

/** Request `scope`: from now on only its results replace the report; the report on screen stays until then. */
export function requestScope(state: GrindStatusState, scope: GrindScope): GrindStatusState {
  return { ...state, requested: grindStatusUrl(scope) };
}

/**
 * Apply one load's result. A result for a scope other than the one now
 * requested is dropped; a failure keeps the last good report.
 */
export function applyGrindStatus(state: GrindStatusState, requestedUrl: string, load: GrindStatusLoad): GrindStatusState {
  if (requestedUrl !== state.requested) return state;
  if (load.kind === "ok") return { ...state, report: load.report, error: null };
  return { ...state, error: loadFailureText(load) };
}

/* ---------- poll ---------- */

/** The interval select's choices, in seconds; 0 is Off. */
export const GRIND_STATUS_INTERVALS: readonly { sec: number; label: string }[] = [
  { sec: 0, label: "Off" },
  { sec: 30, label: "30 s" },
  { sec: 60, label: "60 s" },
  { sec: 120, label: "2 min" },
  { sec: 300, label: "5 min" },
];
export const DEFAULT_GRIND_STATUS_INTERVAL_SEC = 60;

/** A stored interval preference, or the default when it is not one of the choices. */
export function parseIntervalSec(stored: string | null): number {
  const n = Number(stored);
  return stored !== null && GRIND_STATUS_INTERVALS.some((i) => i.sec === n) ? n : DEFAULT_GRIND_STATUS_INTERVAL_SEC;
}

export type GrindStatusPoll = {
  /** Load at once (even while a load runs) and restart the interval. */
  refreshNow: () => void;
  stop: () => void;
};

/**
 * Calls `load` now and every `intervalSec` (none when 0) until `stop`. A tick
 * while a load is still running is skipped, so slow loads never pile up.
 */
export function pollGrindStatus(load: () => Promise<void>, intervalSec: number): GrindStatusPoll {
  let running = 0;
  let timer: ReturnType<typeof setInterval> | null = null;
  const run = () => {
    running += 1;
    void load().finally(() => {
      running -= 1;
    });
  };
  const restart = () => {
    if (timer !== null) clearInterval(timer);
    timer =
      intervalSec > 0
        ? setInterval(() => {
            if (running === 0) run();
          }, intervalSec * 1000)
        : null;
  };
  const refreshNow = () => {
    run();
    restart();
  };
  refreshNow();
  return {
    refreshNow,
    stop: () => {
      if (timer !== null) clearInterval(timer);
      timer = null;
    },
  };
}

/* ---------- text ---------- */

/** "12 s ago", "4 min ago", "3 h ago", "2 d ago"; "now" for a future time (clock skew). */
export function ageText(iso: string, now: Date): string {
  const s = Math.floor((now.getTime() - new Date(iso).getTime()) / 1000);
  if (Number.isNaN(s)) return "";
  if (s < 0) return "now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86_400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86_400)} d ago`;
}

/** Last updated: the local time of `generated_at` and its age. */
export function lastUpdatedText(report: GrindStatusReport, now: Date): string {
  const time = new Date(report.generated_at).toLocaleTimeString();
  return `Last updated ${time} (${ageText(report.generated_at, now)})`;
}

const TOTAL_KEYS = [
  "total",
  "done",
  "cancelled",
  "remaining",
  "held",
  "active",
  "ready",
  "waiting",
  "awaiting_merge",
  "not_pickable",
];

export function totalsLine(report: GrindStatusReport): string {
  return "totals: " + TOTAL_KEYS.map((k) => `${k.replaceAll("_", " ")} ${report.totals[k]}`).join(", ");
}

/** The report's own checkout, as the CLI prints it. */
export function sourceLine(report: GrindStatusReport): string {
  const { branch, head, fetched } = report.source;
  return `as of ${branch ?? "(detached HEAD)"} @ ${(head ?? "?").slice(0, 12)}, this checkout${fetched ? "" : ", not fetched"}`;
}

export type GrindSection = { title: string; lines: string[] };

const NONE = ["(none)"];

function leafSection<T>(title: string, items: T[], fmt: (item: T) => string): GrindSection {
  return { title: `${title} (${items.length})`, lines: items.length ? items.map(fmt) : NONE };
}

function activeLine(a: GrindActive): string {
  const parts = [`review ${a.review ?? a.review_error ?? "none (no claim)"}`];
  if (a.worker) parts.push(`worker ${a.worker.id} (${a.worker.harness}, ${a.worker.state})`);
  if (a.note) parts.push(a.note);
  return `${a.id} ${a.title}: ${parts.join("; ")}`;
}

const dash = (v: string | null | undefined) => v || "-";

function estimateLines(e: GrindStatusReport["estimate"]): string[] {
  const i = e.inputs;
  const lines = [
    `method: ${e.method}`,
    `inputs: n=${i.n}, first ${dash(i.first)}, last ${dash(i.last)}, recent ${i.recent} in ${i.window_days} days, ` +
      `minimum ${i.minimum} completions over ${i.minimum_span_hours} hours, remaining ${i.remaining}`,
  ];
  if (e.reason) return [...lines, e.reason];
  return [...lines, `earliest: ${e.earliest}`, `latest: ${e.latest}`];
}

function decisionLines(d: GrindStatusReport["decisions"]): string[] {
  const lines: string[] = [];
  for (const e of d.ledger) {
    const opts = (e.options ?? []).map((o) => `${o.label} (${o.effect})`).join("; ") || "-";
    lines.push(
      `${e.id} [${e.kind}] node ${e.node} (${e.ledger} ledger), needed-by ${dash(e.needed_by)}`,
      `  ${e.summary}`,
      `  why now: ${e.why_now}`,
      `  options: ${opts}`,
      `  recommendation: ${e.recommendation} — ${e.recommendation_reason}`,
      `  default if unanswered: ${e.default_if_unanswered}`,
      `  pros/cons: ${e.pros_cons}`,
    );
  }
  for (const e of d.ledger_outside_scope) lines.push(`outside scope: ${e.id} node ${e.node}: ${e.summary}`);
  for (const h of d.held) {
    lines.push(`held ${h.node}: ${h.reason}`, ...h.next.map((n) => `  next: \`${n}\``), `  ${h.options}`);
  }
  return lines.length ? lines : NONE;
}

/**
 * "Decided in the GUI, not yet processed", as the CLI prints it: only while an item waits, so a server from
 * before M17.15 (no `gui_pending`) and an empty list both show no section.
 */
function guiPendingSections(pending: GrindGuiPending[] | undefined): GrindSection[] {
  if (!pending?.length) return [];
  const lines = pending.flatMap((g) => [
    `${g.id} [${g.kind}] node ${g.node}: ${g.answer}`,
    ...g.next.map((n) => `  next: ${n}`),
  ]);
  return [{ title: "Decided in the GUI, not yet processed", lines }];
}

/** The report's sections in the CLI's order, each line as `render_text` prints it. */
export function grindStatusSections(r: GrindStatusReport): GrindSection[] {
  const sections = [
    leafSection("Held", r.held, (h) => `${h.id} ${h.title}: ${h.reasons.map((x) => x.reason).join("; ")}`),
    leafSection("Active", r.active, activeLine),
    leafSection("Ready", r.ready, (x) => `${x.id} ${x.title}`),
    leafSection("Waiting", r.waiting, (x) => `${x.id} ${x.title}: waiting on ${x.waiting_on.join(", ")}`),
    leafSection("Finished, awaiting merge", r.awaiting_merge, (x) => `${x.id} ${x.title}: ${x.reason}`),
    leafSection("Not pickable", r.not_pickable, (x) => `${x.id} ${x.title}: ${x.reason}`),
    { title: "Estimate", lines: estimateLines(r.estimate) },
    { title: "Decisions waiting on a person", lines: decisionLines(r.decisions) },
    ...guiPendingSections(r.decisions.gui_pending),
    leafSection("Open brainstorm sessions", r.sessions.brainstorm, (b) => `${b.slug} (${b.mode}, ${b.ideas} ideas)`),
    leafSection(
      "Live sessions",
      r.sessions.presence,
      (p) =>
        `${p.agent} on ${dash(p.branch)}, expires ${p.expires}, note: ${dash(p.note)}` +
        (p.stale_reason ? `, stale: ${p.stale_reason}` : ""),
    ),
  ];
  if (r.missing.length) {
    sections.push({ title: "Missing", lines: r.missing.map((m) => `${m.record}: ${m.field}`) });
  }
  return sections;
}
