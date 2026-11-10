import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
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
  type GrindStatusState,
} from "../grindStatus";
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

const fetchImpl: typeof fetch = (input, init) => fetch(input, init);

/**
 * Read-only grind status (M17.14). Mounted only while open, so its poll and
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
        `specy-road grind-session --status` for this server&apos;s checkout. Read-only. Both fields empty: the
        milestone session&apos;s parent.
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
    </ModalFrame>
  );
}
