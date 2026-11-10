import { useCallback, useEffect, useRef, useState } from "react";
import {
  GRIND_STATUS_INTERVALS,
  applyGrindStatus,
  grindStatusSections,
  grindStatusUrl,
  lastUpdatedText,
  loadGrindStatus,
  parseIntervalSec,
  pollGrindStatus,
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
  const [draft, setDraft] = useState<GrindScope>(scope);
  const [intervalSec, setIntervalSec] = useState(() =>
    parseIntervalSec(readBrowserPref(BROWSER_PREF_KEYS.grindStatusIntervalSec, repoId)),
  );
  const [status, setStatus] = useState<GrindStatusState>(() => ({
    requested: grindStatusUrl(scope),
    report: null,
    error: null,
  }));
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

  const commitScope = () => {
    const next = { until: draft.until.trim(), under: draft.under.trim() };
    if (next.until === scope.until && next.under === scope.under) return;
    writeBrowserPref(BROWSER_PREF_KEYS.grindStatusUntil, repoId, next.until);
    writeBrowserPref(BROWSER_PREF_KEYS.grindStatusUnder, repoId, next.under);
    scopeRef.current = next;
    setScope(next);
    setStatus((s) => ({ ...s, requested: grindStatusUrl(next) }));
    pollRef.current?.refreshNow();
  };

  const onIntervalChange = (sec: number) => {
    writeBrowserPref(BROWSER_PREF_KEYS.grindStatusIntervalSec, repoId, String(sec));
    setIntervalSec(sec);
  };

  const { report, error } = status;
  const field = (key: keyof GrindScope, label: string) => (
    <label className="grind-status-field">
      {label}{" "}
      <input
        type="text"
        value={draft[key]}
        placeholder="node id"
        onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
        onBlur={commitScope}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitScope();
        }}
      />
    </label>
  );

  return (
    <ModalFrame title="Grind status" titleId="grind-status-title" onClose={onClose} storageKey="grind-status">
      <p className="outline-meta">
        `specy-road grind-session --status` for this server&apos;s checkout. Read-only. Both fields empty: the
        milestone session&apos;s parent.
      </p>
      <div className="workspace-notes-actions grind-status-controls">
        {field("until", "Until")}
        {field("under", "Under")}
        <label className="grind-status-field">
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
            {error ? <span className="grind-status-error"> · {error}</span> : null}
          </p>
        </>
      ) : null}
      {!report && error ? <p className="grind-status-error">{error}</p> : null}
      {report
        ? grindStatusSections(report).map((s) => (
            <section key={s.title} className="grind-status-section">
              <h4 className="worker-section-title">{s.title}</h4>
              <div className="grind-status-lines">{s.lines.join("\n")}</div>
            </section>
          ))
        : null}
    </ModalFrame>
  );
}
