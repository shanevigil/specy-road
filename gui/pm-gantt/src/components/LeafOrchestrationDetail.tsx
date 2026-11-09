import { useCallback, useEffect, useState } from "react";
import { fetchOrchestration } from "../api";
import {
  buildOrchestrationView,
  copyCommand,
  type CopyKind,
  type OrchestrationGroupView,
  type OrchestrationLoad,
  type OrchestrationSnapshot,
  type OutlineNodeRef,
} from "../orchestrationSnapshot";

/**
 * Dev builds with `?mock=orchestration` show M17.2's mock. The drawer and the
 * edit-modal section share this so both mounts read the same snapshot.
 */
// eslint-disable-next-line react-refresh/only-export-components -- shared loader for both mounts
export function loadDisplayedOrchestration(
  fetchLive: () => Promise<OrchestrationLoad> = fetchOrchestration,
): Promise<OrchestrationLoad> {
  if (
    import.meta.env.DEV &&
    new URLSearchParams(window.location.search).get("mock") === "orchestration"
  ) {
    return import("../fixtures/orchestration_snapshot_mock.json").then(
      (m): OrchestrationLoad => ({
        kind: "ok",
        snapshot: m.default as unknown as OrchestrationSnapshot,
      }),
    );
  }
  return fetchLive();
}

function sourceLabel(source: string): string {
  return source === "hold_list" ? "hold list" : source;
}

function CellTable({
  columns,
  rows,
  codeAt,
}: {
  columns: string[];
  rows: string[][];
  /** Column indexes shown in `<code>` (paths, branches, commits, ids). */
  codeAt: number[];
}) {
  return (
    <table className="workspace-file-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.join("\u0000")}>
            {row.map((cell, j) => (
              <td key={columns[j]}>{codeAt.includes(j) ? <code>{cell}</code> : cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Read-only orchestration for one leaf. The drawer and the edit modal both mount this. */
export function LeafOrchestrationDetail({
  group,
  onCopy,
}: {
  group: OrchestrationGroupView;
  onCopy: (kind: CopyKind, id: string) => void;
}) {
  const { claim, ready, gate } = group;
  return (
    <div className="worker-detail">
      <button
        type="button"
        title={copyCommand("handoff status", group.displayId)}
        onClick={() => onCopy("handoff status", group.displayId)}
      >
        Copy handoff status
      </button>
      {claim ? (
        <p className="outline-meta">
          Claim <code>{claim.codename}</code> · {claim.branch} · registered {claim.registered}
        </p>
      ) : (
        <p className="outline-meta">Claim —</p>
      )}
      <p className="worker-section-title">Worktrees</p>
      <p className="outline-meta">Ahead and behind are against the integration branch.</p>
      {group.worktrees.length === 0 ? (
        <p className="outline-meta">—</p>
      ) : (
        <CellTable
          columns={["Path", "Branch", "Dirty", "Ahead", "Behind"]}
          codeAt={[0, 1]}
          rows={group.worktrees.map((t) => [t.path, t.branch, t.dirty, t.ahead, t.behind])}
        />
      )}
      <p className="worker-section-title">READY</p>
      {ready ? (
        <>
          <p className="outline-meta">
            <code>{ready.commit}</code> · {ready.model} · {ready.age}
          </p>
          {ready.blockedOn.map((line) => (
            <p key={line} className="outline-meta">
              {line}
            </p>
          ))}
        </>
      ) : (
        <p className="outline-meta">—</p>
      )}
      <p className="worker-section-title">Reviews</p>
      {group.reviews.length === 0 ? (
        <p className="outline-meta">—</p>
      ) : (
        <CellTable
          columns={["Model", "Verdict", "Commit", "Fresh for HEAD"]}
          codeAt={[2]}
          rows={group.reviews.map((r) => [r.model, r.verdict, r.commit, r.fresh])}
        />
      )}
      <p className="worker-section-title">Gate</p>
      {gate ? (
        <p className="outline-meta">
          {gate.state} · approvals {gate.approvals} · blocks {gate.blocks} · fresh for HEAD{" "}
          {gate.fresh}
        </p>
      ) : (
        <p className="outline-meta">—</p>
      )}
      <p className="worker-section-title">Holds</p>
      {group.holds.length === 0 ? (
        <p className="outline-meta">—</p>
      ) : (
        <CellTable
          columns={["Source", "Id", "Reason"]}
          codeAt={[1]}
          rows={group.holds.map((h) => [sourceLabel(h.source), h.id, h.reason])}
        />
      )}
    </div>
  );
}

/**
 * Collapsed read-only "Orchestration" section for a leaf's edit modal.
 * Loads once when opened; it does not save and does not poll.
 */
export function LeafOrchestrationSection({
  nodeKey,
  nodes,
}: {
  nodeKey: string;
  nodes: readonly OutlineNodeRef[];
}) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<{ result: OrchestrationLoad; at: Date } | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    void loadDisplayedOrchestration().then((result) => {
      if (live) setLoaded({ result, at: new Date() });
    });
    return () => {
      live = false;
    };
  }, [open, nodeKey]);

  const copy = useCallback(async (kind: CopyKind, id: string) => {
    const cmd = copyCommand(kind, id);
    try {
      await navigator.clipboard.writeText(cmd);
      setNote(`Copied: ${cmd}`);
    } catch {
      setNote("copy failed");
    }
  }, []);

  const group =
    loaded?.result.kind === "ok"
      ? (buildOrchestrationView(loaded.result.snapshot, nodes, loaded.at).find(
          (g) => g.key === nodeKey,
        ) ?? null)
      : null;

  return (
    <details
      className="worker-group"
      onToggle={(e) => {
        const next = e.currentTarget.open;
        if (next) setLoaded(null);
        setOpen(next);
      }}
    >
      <summary className="worker-section-title">Orchestration</summary>
      {open && !loaded ? <p className="outline-meta">Loading…</p> : null}
      {loaded?.result.kind === "unavailable" ? (
        <p className="workspace-empty">
          This server does not provide the orchestration snapshot yet.
        </p>
      ) : null}
      {loaded?.result.kind === "error" ? (
        <p className="outline-meta">{loaded.result.message}</p>
      ) : null}
      {loaded?.result.kind === "ok" && group == null ? (
        <p className="outline-meta">No orchestration state for this leaf.</p>
      ) : null}
      {group ? <LeafOrchestrationDetail group={group} onCopy={(kind, id) => void copy(kind, id)} /> : null}
      {note ? <p className="outline-meta">{note}</p> : null}
    </details>
  );
}
