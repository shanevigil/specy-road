import { useCallback, useEffect, useState } from "react";
import { fetchWorkerEvents, fetchWorkers } from "../api";
import type { WorkerDetail, WorkerRow } from "../types";
import {
  createWorkerSelection,
  type WorkerSelectionState,
} from "../workerSelection";
import {
  formatCost,
  formatSeconds,
  isToolCall,
  phaseSegments,
} from "../workerTimeline";
import { ModalFrame } from "./ModalFrame";

type Props = {
  open: boolean;
  onClose: () => void;
};

/** Workers grouped by leaf, in the order the server listed them (oldest worker first). */
function groupByNode(rows: WorkerRow[]): [string, WorkerRow[]][] {
  const out = new Map<string, WorkerRow[]>();
  for (const r of rows) {
    const list = out.get(r.node_id) ?? [];
    list.push(r);
    out.set(r.node_id, list);
  }
  return [...out.entries()];
}

function PhaseBar({ phases }: { phases: WorkerDetail["phases"] }) {
  const segs = phaseSegments(phases);
  return (
    <div className="worker-phase">
      <div
        className="worker-phase-bar"
        role="img"
        aria-label="Phase durations of the latest turn"
      >
        {segs.map((s, i) =>
          s.pct > 0 ? (
            <span
              key={s.name}
              className={`worker-phase-seg worker-phase-seg--${i % 4}`}
              style={{ width: `${s.pct}%` }}
              title={`${s.label}: ${formatSeconds(s.seconds)}`}
            />
          ) : null,
        )}
      </div>
      <ul className="worker-phase-legend">
        {segs.map((s, i) => (
          <li key={s.name}>
            <span className={`worker-phase-swatch worker-phase-seg--${i % 4}`} />
            {s.label}: {formatSeconds(s.seconds)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function WorkerDetailView({ d }: { d: WorkerDetail }) {
  const stalls = d.events.filter((e) => e.type === "stalled").length;
  const u = d.usage;
  const n = (v: number | null) => (v == null ? "?" : String(v));
  return (
    <div className="worker-detail">
      <p className="outline-meta">
        <code>{d.worker_id}</code> {d.node_id} · attempt {d.attempt} ·{" "}
        {d.harness}/{d.model} · <strong>{d.state}</strong>
        {d.flags.length ? ` [${d.flags.join(", ")}]` : ""}
        {stalls > 0 ? (
          <span className="worker-stall-badge">stalled ×{stalls}</span>
        ) : null}
      </p>
      <h4 className="worker-section-title">Latest turn</h4>
      <PhaseBar phases={d.phases} />
      <p className="outline-meta">
        Usage ({u.turns} turn{u.turns === 1 ? "" : "s"}): in {n(u.input_tokens)} (
        {n(u.cached_input_tokens)} cached), out {n(u.output_tokens)}, reasoning{" "}
        {n(u.reasoning_tokens)}, {formatCost(u.cost_usd, u.cost_is_estimate)}
      </p>
      <h4 className="worker-section-title">Events</h4>
      <ol className="worker-event-list">
        {d.events.map((e) => {
          const tool = isToolCall(e);
          const cls = [
            "worker-event",
            tool ? "worker-event--tool" : "",
            e.type === "stalled" ? "worker-event--stalled" : "",
          ].join(" ");
          return (
            <li key={e.seq} className={cls}>
              <span className="worker-event-seq">#{e.seq}</span>
              <span className="worker-event-at">{e.at.slice(11, 19)}</span>
              <span className="worker-event-type">
                {e.type === "stalled" ? "⚠ stalled" : tool ? "tool" : e.type}
              </span>
              <span className="worker-event-summary">{e.summary}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function WorkersDrawer({ open, onClose }: Props) {
  const [rows, setRows] = useState<WorkerRow[]>([]);
  const [view, setView] = useState<WorkerSelectionState<WorkerDetail>>({
    selected: null,
    detail: null,
    loading: false,
    error: null,
  });
  // One controller for the drawer's life: a newer selection drops older replies.
  const [selection] = useState(() =>
    createWorkerSelection(fetchWorkerEvents, setView),
  );
  const { selected, detail } = view;
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  /** Reload the list; keep `keepId` selected when it is still listed, else the newest worker. */
  const load = useCallback(
    async (keepId: string | null) => {
      setLoading(true);
      setMsg(null);
      try {
        const r = await fetchWorkers();
        setRows(r.workers);
        const keep = r.workers.find((w) => w.worker_id === keepId);
        const pick = keep ?? r.workers[r.workers.length - 1];
        if (pick) await selection.select(pick.worker_id);
        else selection.clear();
      } catch (e: unknown) {
        setMsg(String(e));
      } finally {
        setLoading(false);
      }
    },
    [selection],
  );

  useEffect(() => {
    if (!open) return;
    void load(null);
  }, [open, load]);

  if (!open) return null;

  return (
    <ModalFrame
      title="Workers"
      titleId="workers-drawer-title"
      onClose={onClose}
      storageKey="workers"
      footer={
        msg || view.error ? (
          <p className="outline-meta">{msg ?? view.error}</p>
        ) : null
      }
      bodyClassName="modal-body--workspace"
    >
      <p className="outline-meta">
        What each worker did, read from <code>work/.workers/</code> in the main
        worktree. Read-only: nothing here changes a worker.
      </p>
      <div className="workspace-notes-layout">
        <div className="workspace-notes-sidebar">
          <div className="workspace-notes-actions">
            <button type="button" onClick={() => void load(selected)}>
              Refresh
            </button>
          </div>
          {loading ? <p className="outline-meta">Loading…</p> : null}
          {rows.length === 0 && !loading ? (
            <p className="workspace-empty">No workers under work/.workers/.</p>
          ) : null}
          {groupByNode(rows).map(([node, list]) => (
            <div key={node} className="worker-group">
              <h4 className="worker-section-title">{node}</h4>
              <ul
                className="workspace-file-list"
                role="listbox"
                aria-label={`Workers on ${node}`}
              >
                {list.map((w) => (
                  <li key={w.worker_id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={selected === w.worker_id}
                      className={
                        selected === w.worker_id
                          ? "workspace-file-pill selected"
                          : "workspace-file-pill"
                      }
                      title={w.last_event ? `#${w.last_event.seq} ${w.last_event.type}: ${w.last_event.summary}` : ""}
                      onClick={() => void selection.select(w.worker_id)}
                    >
                      #{w.attempt} {w.worker_id} · {w.state}
                      <br />
                      <span className="outline-meta">
                        {w.harness}/{w.model} ·{" "}
                        {formatCost(w.total_cost_usd, w.cost_is_estimate)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="workspace-notes-editor">
          {detail ? (
            <WorkerDetailView d={detail} />
          ) : view.loading ? (
            <p className="outline-meta">Loading {selected}…</p>
          ) : (
            <p className="outline-meta">Select a worker.</p>
          )}
        </div>
      </div>
    </ModalFrame>
  );
}
