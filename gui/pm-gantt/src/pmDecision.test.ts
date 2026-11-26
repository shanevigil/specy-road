import { describe, expect, it } from "vitest";
import modalSource from "./components/StatusModal.tsx?raw";
import mockJson from "./fixtures/grind_status_mock.json";
import { grindStatusSections, type GrindStatusReport } from "./grindStatus";
import {
  DECISION_CODE_HEADER,
  EMPTY_FORM,
  PM_DECISIONS_URL,
  approvalOffers,
  decisionCodeStore,
  decisionTargets,
  resultText,
  reviewDecision,
  sendDecision,
  type DecisionForm,
  type DecisionRequest,
} from "./pmDecision";

const mock = mockJson as unknown as GrindStatusReport;
const SETTLES = ['block by opus at abc with findings ["correctness: A1 regressed"]', "approval shortfall: need 1, have 0"];
const COMMIT = "0123456789abcdef0123456789abcdef01234567";

/** The mock with M1.3 blocked and approvable, and one decision waiting on a coordinator. */
function withOffer(): GrindStatusReport {
  const r = structuredClone(mock);
  r.active[0] = { ...r.active[0], commit: COMMIT, can_approve_over_block: true, settles: SETTLES };
  r.decisions.gui_pending = [
    { id: "D7", node: "M1.4", kind: "answer", answer: "yaml: ship it", next: ["commit the line", "then act on it"] },
  ];
  return r;
}

/** M17.14's original response: none of M17.15's fields. */
function olderServer(): GrindStatusReport {
  const r = structuredClone(mock);
  for (const leaf of [...r.held, ...r.active] as Record<string, unknown>[]) {
    delete leaf.commit;
    delete leaf.can_approve_over_block;
    delete leaf.settles;
  }
  delete r.decisions.gui_pending;
  return r;
}

function recordingFetch(status: number, body: unknown) {
  const calls: { url: string; init: RequestInit | undefined }[] = [];
  const fetchImpl = ((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return Promise.resolve(new Response(JSON.stringify(body), { status }));
  }) as typeof fetch;
  return { calls, fetchImpl };
}

describe("what the report offers", () => {
  it("answers for the in-scope ledger entries; an approval only where the server says it can", () => {
    expect(decisionTargets(mock).map((t) => t.kind)).toEqual(["answer"]);   // M1.3 cannot be approved over
    const targets = decisionTargets(withOffer());
    expect(targets.map((t) => t.kind)).toEqual(["answer", "approve-over-block"]);
    expect(approvalOffers(withOffer())).toEqual([{ id: "M1.3", title: "Leaf M1.3", commit: COMMIT, settles: SETTLES }]);
  });

  it("an older server: no approval offered, no pending section, no error", () => {
    const r = olderServer();
    expect(approvalOffers(r)).toEqual([]);
    expect(decisionTargets(r).map((t) => t.kind)).toEqual(["answer"]);
    const titles = grindStatusSections(r).map((s) => s.title);
    expect(titles).not.toContain("Decided in the GUI, not yet processed");
    expect(titles).toEqual(grindStatusSections(mock).map((s) => s.title));
  });

  it("shows the decisions decided in the GUI and their next steps", () => {
    const pending = grindStatusSections(withOffer()).find((s) => s.title === "Decided in the GUI, not yet processed");
    expect(pending?.lines).toEqual(["D7 [answer] node M1.4: yaml: ship it", "  next: commit the line", "  next: then act on it"]);
  });
});

describe("the confirm flow", () => {
  const [answerTarget, approveTarget] = decisionTargets(withOffer());

  it.each<[string, DecisionForm, string]>([
    ["nothing chosen", { ...EMPTY_FORM, words: "w", code: "c" }, "Choose what to decide."],
    ["no option", { ...EMPTY_FORM, target: answerTarget, words: "w", code: "c" }, "Choose one of the options, or Other."],
    ["empty reason", { ...EMPTY_FORM, target: approveTarget, words: "  ", code: "c" }, "Say why, in your own words."],
    ["two lines", { ...EMPTY_FORM, target: answerTarget, choice: { label: "yaml" }, words: "ship\nit", code: "c" },
      "Keep your words on one line."],
    ["a carriage return", { ...EMPTY_FORM, target: approveTarget, words: "false\r alarm", code: "c" },
      "Keep your words on one line."],
    ["no code", { ...EMPTY_FORM, target: approveTarget, words: "w", code: " " },
      "Enter the code `specy-road gui` printed in its terminal."],
  ])("%s: a form error and no request", (_name, form, error) => {
    expect(reviewDecision(form)).toEqual({ ok: false, error });
  });

  it("an answer's review names the entry, the option and the words; Other records the words alone", () => {
    const base = { ...EMPTY_FORM, target: answerTarget, words: " ship it ", code: " c0de " };
    const label = reviewDecision({ ...base, choice: { label: "yaml" } });
    expect(label).toEqual({
      ok: true,
      lines: [
        "Answer D1 (decision, node M1.4): Pick the parser",
        "Option: yaml",
        "Words: ship it",
        "Recorded answer: yaml: ship it",
      ],
      request: {
        body: { kind: "answer", id: "D1", option: "yaml", words: "ship it" },
        headers: { "Content-Type": "application/json", [DECISION_CODE_HEADER]: "c0de" },
      },
    });
    const other = reviewDecision({ ...base, choice: { other: true } });
    expect(other.ok && other.lines.slice(1)).toEqual(["Option: Other (the words alone)", "Words: ship it",
      "Recorded answer: ship it"]);
    expect(other.ok && other.request.body.option).toBeNull();
  });

  it("an approval's review names the leaf, the commit, every settles line and the words; the request carries them", () => {
    const r = reviewDecision({ ...EMPTY_FORM, target: approveTarget, words: "false alarm", code: "c0de" });
    expect(r.ok && r.lines).toEqual([
      "Approve M1.3 Leaf M1.3 over the block",
      `Commit: ${COMMIT}`,
      "Settles:",
      ...SETTLES.map((s) => `  ${s}`),
      "Words: false alarm",
    ]);
    expect(r.ok && r.request.body).toEqual({ kind: "approve-over-block", node_id: "M1.3", commit: COMMIT,
      settles: SETTLES, words: "false alarm" });
    expect(JSON.stringify(r.ok && r.request.body)).not.toContain("c0de");   // the code only in the header
  });

  it("Record decision posts the reviewed request once, the code only in its header", async () => {
    const r = reviewDecision({ ...EMPTY_FORM, target: approveTarget, words: "false alarm", code: "c0de" });
    const request = (r.ok ? r.request : null) as DecisionRequest;
    const recorded = { id: "D2", integration_commit: "f".repeat(40), destination: "origin/dev", gate_met: true };
    const { calls, fetchImpl } = recordingFetch(200, recorded);
    const result = await sendDecision(fetchImpl, request);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(PM_DECISIONS_URL);
    expect(calls[0].url).not.toContain("c0de");
    expect(calls[0].init?.method).toBe("POST");
    expect(calls[0].init?.headers).toEqual({ "Content-Type": "application/json", [DECISION_CODE_HEADER]: "c0de" });
    expect(JSON.parse(String(calls[0].init?.body))).toEqual(request.body);
    expect(resultText(result)).toBe(`Recorded D2 on origin/dev as ${"f".repeat(40)}. A coordinator processes it at its next status check.`);
  });

  it.each([
    [403, { detail: "wrong or missing X-PM-Decision-Code" }, "Not recorded (403): wrong or missing X-PM-Decision-Code"],
    [409, { detail: "reload the status" }, "Not recorded (409): reload the status"],
    [404, { detail: "no API route" }, "Not recorded (404): the server does not take PM decisions"],
  ])("a %i refusal shows the server's detail", async (status, body, text) => {
    const request = { body: {}, headers: {} };
    expect(resultText(await sendDecision(recordingFetch(status, body).fetchImpl, request))).toBe(text);
  });

  it("a recorded decision whose gate is still not met says so; a local answer names the local ledger", () => {
    const unmet = { id: "D2", integration_commit: "abc", destination: "origin/dev", gate_met: false,
      detail: "the registry was not stamped" };
    expect(resultText({ kind: "ok", recorded: unmet })).toBe("Recorded D2 on origin/dev as abc. the registry was not stamped");
    expect(resultText({ kind: "ok", recorded: { id: "D9", integration_commit: null, destination: "local ledger" } }))
      .toBe("Recorded D9 on local ledger. A coordinator processes it at its next status check.");
  });
});

describe("StatusModal keeps the code in page memory only", () => {
  it("never stores it in web storage or a URL", () => {
    expect(modalSource).not.toMatch(/localStorage|sessionStorage/);
    expect(modalSource).toContain('type="password"');
    expect(modalSource).toContain("sendDecision(fetchImpl, reviewed.request)");
  });

  it("keeps the code entered for the page across closing and reopening Status", () => {
    const seen: string[] = [];
    const close = decisionCodeStore.subscribe(() => seen.push(decisionCodeStore.get()));   // Status open
    decisionCodeStore.set("c0de");
    close();   // Status closed: the modal unmounts
    const reopen = decisionCodeStore.subscribe(() => undefined);
    expect(decisionCodeStore.get()).toBe("c0de");   // reopened: no need to type it again
    expect(seen).toEqual(["c0de"]);
    reopen();
    decisionCodeStore.set("");
    expect(modalSource).toContain("useSyncExternalStore(decisionCodeStore.subscribe, decisionCodeStore.get)");
    expect(modalSource).toContain("value={code} onChange={(e) => editCode(e.target.value)}");   // the input reads the store
  });
});
