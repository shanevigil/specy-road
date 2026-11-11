import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";
import {
  GRIND_STATUS_INTERVALS,
  applyGrindStatus,
  grindStatusSections,
  lastUpdatedText,
  loadGrindStatus,
  parseIntervalSec,
  grindStatusUrl,
  pollGrindStatus,
  requestScope,
  sourceLine,
  totalsLine,
  type GrindScope,
  type GrindStatusPoll,
  type GrindStatusReport,
  type GrindStatusState,
} from "../grindStatus";
import {
  EMPTY_FORM,
  decisionCodeStore,
  decisionTargets,
  resultText,
  reviewDecision,
  sendDecision,
  targetLabel,
  type DecisionForm,
  type DecisionTarget,
  type ReviewedDecision,
} from "../pmDecision";
import { BROWSER_PREF_KEYS, readBrowserPref, writeBrowserPref } from "../repoBrowserPrefs";
import { IconRefresh } from "../toolbarIcons";
import { ModalFrame } from "./ModalFrame";

type Props = {
  onClose: () => void;
  /** Per-repo browser preferences: the scope fields and the interval. */
  repoId: string | null;
};

/*
 * Inline styles: `main.tsx` loads only `index.css`, so a class added for this
 * modal alone would not reach the build. `pre-wrap` keeps each line the
 * server's text makes, and every line break inside that text, as sent.
 */
const LINES: CSSProperties = { whiteSpace: "pre-wrap", fontSize: "0.9em" };
const ERROR: CSSProperties = { color: "var(--bar-blocked)" };
const CONTROLS: CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.75rem" };
const FIELD: CSSProperties = { display: "block", margin: "0.4rem 0" };
const WORDS: CSSProperties = { width: "100%", boxSizing: "border-box" };

const fetchImpl: typeof fetch = (input, init) => fetch(input, init);

const sameTarget = (a: DecisionTarget, b: DecisionTarget | null) =>
  !!b &&
  a.kind === b.kind &&
  (a.kind === "answer"
    ? b.kind === "answer" && a.entry.id === b.entry.id
    : b.kind === "approve-over-block" && a.leaf.id === b.leaf.id);

/**
 * PM decisions (M17.15): choose an entry to answer or a leaf to approve over its block, type why and the code,
 * **Review decision**, then **Record decision** sends the reviewed request. The code lives in `decisionCodeStore`
 * (page memory), so closing and reopening Status keeps it until a reload: never in web storage, a URL or a body.
 */
function DecisionPanel({ report, onRecorded }: { report: GrindStatusReport; onRecorded: () => void }) {
  const [form, setForm] = useState<Omit<DecisionForm, "code">>(EMPTY_FORM);
  const code = useSyncExternalStore(decisionCodeStore.subscribe, decisionCodeStore.get);
  const [reviewed, setReviewed] = useState<ReviewedDecision | null>(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const targets = decisionTargets(report);
  if (!targets.length && !result) return null;

  /** Any edit drops the review: Record decision sends only what was last reviewed. */
  const edit = (patch: Partial<Omit<DecisionForm, "code">>) => {
    setForm((f) => ({ ...f, ...patch }));
    setReviewed(null);
  };
  const editCode = (value: string) => {
    decisionCodeStore.set(value);
    setReviewed(null);
  };
  const record = async () => {
    if (!reviewed?.ok) return;
    setSending(true);
    const sent = await sendDecision(fetchImpl, reviewed.request);
    setSending(false);
    setResult(resultText(sent));
    if (sent.kind === "ok") {
      setForm(EMPTY_FORM);
      setReviewed(null);
      onRecorded();
    }
  };
  const t = form.target;
  const selected = targets.findIndex((x) => sameTarget(x, t));

  return (
    <section>
      <h4 className="worker-section-title">Decide</h4>
      <p className="outline-meta">
        Answer an open question, or approve a leaf over its reviewers&apos; block. A coordinator processes what
        you record.
      </p>
      <label style={FIELD}>
        Decision{" "}
        <select value={selected} onChange={(e) => edit({ target: targets[Number(e.target.value)] ?? null, choice: null })}>
          <option value={-1}>Choose…</option>
          {targets.map((x, i) => (
            <option key={targetLabel(x)} value={i}>
              {targetLabel(x)}
            </option>
          ))}
        </select>
      </label>
      {t?.kind === "answer" ? (
        <fieldset style={FIELD}>
          <legend>Option</legend>
          {(t.entry.options ?? []).map((o) => (
            <label key={o.label} style={FIELD}>
              <input
                type="radio"
                name="pm-decision-option"
                checked={!!form.choice && "label" in form.choice && form.choice.label === o.label}
                onChange={() => edit({ choice: { label: o.label } })}
              />{" "}
              {o.label} ({o.effect})
            </label>
          ))}
          <label style={FIELD}>
            <input
              type="radio"
              name="pm-decision-option"
              checked={!!form.choice && "other" in form.choice}
              onChange={() => edit({ choice: { other: true } })}
            />{" "}
            Other (your words alone)
          </label>
        </fieldset>
      ) : null}
      {t?.kind === "approve-over-block" ? (
        <div style={LINES}>{[`Commit ${t.leaf.commit}`, "Settles:", ...t.leaf.settles.map((x) => `  ${x}`)].join("\n")}</div>
      ) : null}
      <label style={FIELD}>
        Why, in your own words
        <textarea style={WORDS} rows={3} value={form.words} onChange={(e) => edit({ words: e.target.value })} />
      </label>
      <label style={FIELD}>
        Code from the terminal that started the GUI{" "}
        <input type="password" autoComplete="off" value={code} onChange={(e) => editCode(e.target.value)} />
      </label>
      <div className="workspace-notes-actions" style={CONTROLS}>
        <button type="button" onClick={() => setReviewed(reviewDecision({ ...form, code }))}>
          Review decision
        </button>
        {reviewed?.ok ? (
          <button type="button" disabled={sending} onClick={() => void record()}>
            Record decision
          </button>
        ) : null}
      </div>
      {reviewed && !reviewed.ok ? <p style={ERROR}>{reviewed.error}</p> : null}
      {reviewed?.ok ? <div style={LINES}>{reviewed.lines.join("\n")}</div> : null}
      {result ? <p className="outline-meta">{result}</p> : null}
    </section>
  );
}

/**
 * Read-only grind status (M17.14), with PM decisions below it (M17.15). Mounted only while open, so its poll and
 * its age clock stop when it closes.
 */
export function StatusModal({ onClose, repoId }: Props) {
  const [scope, setScope] = useState<GrindScope>(() => ({
    until: readBrowserPref(BROWSER_PREF_KEYS.grindStatusUntil, repoId) ?? "",
    under: readBrowserPref(BROWSER_PREF_KEYS.grindStatusUnder, repoId) ?? "",
  }));
  const [intervalSec, setIntervalSec] = useState(() =>
    parseIntervalSec(readBrowserPref(BROWSER_PREF_KEYS.grindStatusIntervalSec, repoId)),
  );
  const [status, setStatus] = useState<GrindStatusState>(() =>
    requestScope({ requested: "", report: null, error: null }, scope),
  );
  const [now, setNow] = useState(() => new Date());
  const scopeRef = useRef(scope);
  const pollRef = useRef<GrindStatusPoll | null>(null);

  const load = useCallback(async () => {
    const requested = scopeRef.current;
    const result = await loadGrindStatus(fetchImpl, requested);
    setStatus((s) => applyGrindStatus(s, grindStatusUrl(requested), result));
    setNow(new Date());
  }, []);

  useEffect(() => {
    const poll = pollGrindStatus(load, intervalSec);
    pollRef.current = poll;
    return poll.stop;
  }, [load, intervalSec]);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  /** Every edit of Until or Under requests its scope at once; a late answer for an earlier one is dropped. */
  const changeScope = (key: keyof GrindScope, value: string) => {
    const next = { ...scopeRef.current, [key]: value };
    writeBrowserPref(BROWSER_PREF_KEYS.grindStatusUntil, repoId, next.until);
    writeBrowserPref(BROWSER_PREF_KEYS.grindStatusUnder, repoId, next.under);
    scopeRef.current = next;
    setScope(next);
    setStatus((s) => requestScope(s, next));
    pollRef.current?.refreshNow();
  };

  const onIntervalChange = (sec: number) => {
    writeBrowserPref(BROWSER_PREF_KEYS.grindStatusIntervalSec, repoId, String(sec));
    setIntervalSec(sec);
  };

  const { report, error } = status;
  const field = (key: keyof GrindScope, label: string) => (
    <label>
      {label}{" "}
      <input
        type="text"
        size={10}
        value={scope[key]}
        placeholder="node id"
        onChange={(e) => changeScope(key, e.target.value)}
      />
    </label>
  );

  return (
    <ModalFrame title="Grind status" titleId="grind-status-title" onClose={onClose} storageKey="grind-status">
      <p className="outline-meta">
        `specy-road grind-session --status` for this server&apos;s checkout. Both fields empty: the milestone
        session&apos;s parent. Decisions you record below go to the integration branch for a coordinator.
      </p>
      <div className="workspace-notes-actions" style={CONTROLS}>
        {field("until", "Until")}
        {field("under", "Under")}
        <label>
          Refresh every{" "}
          <select value={intervalSec} onChange={(e) => onIntervalChange(Number(e.target.value))}>
            {GRIND_STATUS_INTERVALS.map((i) => (
              <option key={i.sec} value={i.sec}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="app-header-icon-btn"
          aria-label="Refresh now"
          title="Refresh now"
          onClick={() => pollRef.current?.refreshNow()}
        >
          <IconRefresh />
        </button>
      </div>
      {!report && !error ? <p className="outline-meta">Loading…</p> : null}
      {report ? (
        <>
          <h4 className="worker-section-title">
            Goal {report.goal}: {report.scope.rule}
          </h4>
          <p className="outline-meta">{totalsLine(report)}</p>
          <p className="outline-meta">
            {lastUpdatedText(report, now)} · {sourceLine(report)}
            {error ? <span style={ERROR}> · {error}</span> : null}
          </p>
        </>
      ) : null}
      {!report && error ? <p style={ERROR}>{error}</p> : null}
      {report
        ? grindStatusSections(report).map((s) => (
            <section key={s.title}>
              <h4 className="worker-section-title">{s.title}</h4>
              <div style={LINES}>{s.lines.join("\n")}</div>
            </section>
          ))
        : null}
      {report ? <DecisionPanel report={report} onRecorded={() => pollRef.current?.refreshNow()} /> : null}
    </ModalFrame>
  );
}
