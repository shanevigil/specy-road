/**
 * PM decisions from the status modal (M17.15): answer an open ledger question, or approve a claimed leaf over
 * reviewer blocks, through `POST /api/pm-decisions`.
 *
 * Pure helpers only, so vitest drives the whole confirm flow without a DOM: what the report offers, the form's
 * errors, the **Review decision** preview and the request it fixes, the send (the fetch injected) and the result
 * text. Nothing is sent before the review: `reviewDecision` returns the request, and **Record decision** sends
 * exactly that one. The code goes only into the `X-PM-Decision-Code` header, never into the body or a URL.
 */
import type { GrindLedgerEntry, GrindStatusReport } from "./grindStatus";

export const DECISION_CODE_HEADER = "X-PM-Decision-Code";
export const PM_DECISIONS_URL = "/api/pm-decisions";
const ANSWERABLE = ["decision", "human-action"];

/** What an approval over a block offers for one claimed leaf, as the status sends it. */
export type ApprovalOffer = { id: string; title: string; commit: string; settles: string[] };

/** What the PM decides about. */
export type DecisionTarget =
  | { kind: "answer"; entry: GrindLedgerEntry }
  | { kind: "approve-over-block"; leaf: ApprovalOffer };

/** An option label, or Other: the words alone. */
export type AnswerChoice = { label: string } | { other: true };

export type DecisionForm = {
  target: DecisionTarget | null;
  /** Answers only. */
  choice: AnswerChoice | null;
  words: string;
  /** The code `specy-road gui` printed; page memory only. */
  code: string;
};

export const EMPTY_FORM: DecisionForm = { target: null, choice: null, words: "", code: "" };

/** The open decision and human-action entries the status lists in scope. */
export function answerableEntries(report: GrindStatusReport): GrindLedgerEntry[] {
  return report.decisions.ledger.filter((e) => ANSWERABLE.includes(e.kind));
}

/**
 * The claimed leaves the server says can be approved over their blocks. A server from before M17.15 sends no
 * `can_approve_over_block`, so it offers none.
 */
export function approvalOffers(report: GrindStatusReport): ApprovalOffer[] {
  const out: ApprovalOffer[] = [];
  for (const leaf of [...report.held, ...report.active]) {
    if (leaf.can_approve_over_block === true && typeof leaf.commit === "string" && Array.isArray(leaf.settles)) {
      out.push({ id: leaf.id, title: leaf.title, commit: leaf.commit, settles: leaf.settles });
    }
  }
  return out;
}

/** Every target the report offers, answers first. */
export function decisionTargets(report: GrindStatusReport): DecisionTarget[] {
  return [
    ...answerableEntries(report).map((entry): DecisionTarget => ({ kind: "answer", entry })),
    ...approvalOffers(report).map((leaf): DecisionTarget => ({ kind: "approve-over-block", leaf })),
  ];
}

export function targetLabel(t: DecisionTarget): string {
  return t.kind === "answer"
    ? `Answer ${t.entry.id} (${t.entry.kind}, node ${t.entry.node}): ${t.entry.summary ?? ""}`
    : `Approve ${t.leaf.id} ${t.leaf.title} over the block`;
}

/** Why the form cannot be reviewed yet, or null. */
export function formError(form: DecisionForm): string | null {
  if (!form.target) return "Choose what to decide.";
  if (form.target.kind === "answer" && !form.choice) return "Choose one of the options, or Other.";
  if (!form.words.trim()) return "Say why, in your own words.";
  if (!form.code.trim()) return "Enter the code `specy-road gui` printed in its terminal.";
  return null;
}

export type DecisionRequest = {
  body: Record<string, unknown>;
  headers: Record<string, string>;
};

export type ReviewedDecision =
  | { ok: true; lines: string[]; request: DecisionRequest }
  | { ok: false; error: string };

/**
 * The **Review decision** step: every part the PM chose or settles, and the one request **Record decision**
 * sends. For an answer: the entry, the option (or Other) and the words; for an approval: the leaf, the commit,
 * every line it settles and the words. The request carries the commit and settles exactly as shown.
 */
export function reviewDecision(form: DecisionForm): ReviewedDecision {
  const error = formError(form);
  if (error || !form.target) return { ok: false, error: error ?? "" };
  const words = form.words.trim();
  const headers = { "Content-Type": "application/json", [DECISION_CODE_HEADER]: form.code.trim() };
  const t = form.target;
  if (t.kind === "answer") {
    const label = form.choice && "label" in form.choice ? form.choice.label : null;
    return {
      ok: true,
      lines: [
        `Answer ${t.entry.id} (${t.entry.kind}, node ${t.entry.node}): ${t.entry.summary ?? ""}`,
        label === null ? "Option: Other (the words alone)" : `Option: ${label}`,
        `Words: ${words}`,
        `Recorded answer: ${label === null ? words : `${label}: ${words}`}`,
      ],
      request: { body: { kind: "answer", id: t.entry.id, option: label, words }, headers },
    };
  }
  return {
    ok: true,
    lines: [
      `Approve ${t.leaf.id} ${t.leaf.title} over the block`,
      `Commit: ${t.leaf.commit}`,
      "Settles:",
      ...t.leaf.settles.map((s) => `  ${s}`),
      `Words: ${words}`,
    ],
    request: {
      body: { kind: "approve-over-block", node_id: t.leaf.id, commit: t.leaf.commit, settles: t.leaf.settles, words },
      headers,
    },
  };
}

export type DecisionRecorded = {
  id: string;
  integration_commit: string | null;
  destination: string;
  gate_met?: boolean;
  detail?: string;
};

export type DecisionResult =
  | { kind: "ok"; recorded: DecisionRecorded }
  | { kind: "refused"; status: number; detail: string }
  | { kind: "error"; message: string };

/** **Record decision**: one POST of the reviewed request; never throws. */
export async function sendDecision(fetchImpl: typeof fetch, request: DecisionRequest): Promise<DecisionResult> {
  try {
    const r = await fetchImpl(PM_DECISIONS_URL, {
      method: "POST",
      headers: request.headers,
      body: JSON.stringify(request.body),
    });
    if (r.status === 404) return { kind: "refused", status: 404, detail: "the server does not take PM decisions" };
    const body = (await r.json()) as { detail?: unknown };
    if (!r.ok) return { kind: "refused", status: r.status, detail: String(body.detail) };
    return { kind: "ok", recorded: body as DecisionRecorded };
  } catch (e: unknown) {
    return { kind: "error", message: String(e) };
  }
}

/** The result as the modal shows it. */
export function resultText(result: DecisionResult): string {
  if (result.kind === "error") return result.message;
  if (result.kind === "refused") return `Not recorded (${result.status}): ${result.detail}`;
  const r = result.recorded;
  const where = r.integration_commit ? `${r.destination} as ${r.integration_commit}` : r.destination;
  const head = `Recorded ${r.id} on ${where}.`;
  if (r.gate_met === false) return `${head} ${r.detail ?? "The review gate is still not met."}`;
  return `${head} A coordinator processes it at its next status check.`;
}
