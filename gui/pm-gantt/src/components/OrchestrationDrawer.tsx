import { useCallback, useEffect, useState } from "react";
import { fetchOrchestration } from "../api";
import {
  buildOrchestrationView,
  copyCommand,
  pollOrchestration,
  type CopyKind,
  type OrchestrationGroupView,
  type OrchestrationLoad,
  type OutlineNodeRef,
} from "../orchestrationSnapshot";
import { LeafOrchestrationDetail, loadDisplayedOrchestration } from "./LeafOrchestrationDetail";
import { ModalFrame } from "./ModalFrame";

type Props = {
  open: boolean;
  onClose: () => void;
  /** The outline the GUI already loaded: display ids and titles for snapshot leaf keys. */
  nodes: readonly OutlineNodeRef[];
  /** Open the edit modal for a display id. */
  onOpenNode: (id: string) => void;
  /** Open the Workers drawer on a worker id. */
  onOpenWorker: (id: string) => void;
  /** Show only the group of this leaf `node_key`; null or absent shows every group. */
  filterLeafId?: string | null;
};

/** A dev build with `?mock=orchestration` shows M17.2's mock instead of the server's snapshot. */
function load(): Promise<OrchestrationLoad> {
  return loadDisplayedOrchestration(fetchOrchestration);
}

const WORKER_COLUMNS = [
  "Worker",
  "Harness / model",
  "Account",
  "Status",
  "Last activity",
  "Started",
  "Ended",
  "Flags",
  "Copy CLI",
];

function CopyButton({
  kind,
  id,
  label,
  onCopy,
}: {
  kind: CopyKind;
  id: string;
  label: string;
  onCopy: (kind: CopyKind, id: string) => void;
}) {
  return (
    <button type="button" title={copyCommand(kind, id)} onClick={() => onCopy(kind, id)}>
      {label}
    </button>
  );
}

function GroupView({
  g,
  inOutline,
  detailOpen,
  onToggleDetail,
  onOpenNode,
  onOpenWorker,
  onCopy,
}: {
  g: OrchestrationGroupView;
  inOutline: boolean;
  detailOpen: boolean;
  onToggleDetail: () => void;
  onOpenNode: (id: string) => void;
  onOpenWorker: (id: string) => void;
  onCopy: (kind: CopyKind, id: string) => void;
}) {
  return (
    <div className="worker-group">
      <h4 className="worker-section-title">
        {g.key === null ? null : inOutline ? (
          <button
            type="button"
            className="modal-dep-id-link"
            onClick={() => onOpenNode(g.displayId)}
          >
            {g.displayId}
          </button>
        ) : (
          <code>{g.displayId}</code>
        )}{" "}
        {g.title}
        {g.badge ? <span className="worker-stall-badge">{g.badge.text}</span> : null}
        {g.key === null ? null : (
          <>
            {" "}
            <CopyButton kind="handoff status" id={g.displayId} label="Copy handoff status" onCopy={onCopy} />{" "}
            <button type="button" aria-expanded={detailOpen} onClick={onToggleDetail}>
              {detailOpen ? "Hide detail" : "Detail"}
            </button>
          </>
        )}
      </h4>
      {g.claim ? (
        <p className="outline-meta">
          Claim <code>{g.claim.codename}</code> · {g.claim.branch} · registered{" "}
          {g.claim.registered}
        </p>
      ) : null}
      {g.workers.length === 0 ? (
        <p className="outline-meta">No workers.</p>
      ) : (
        <table className="workspace-file-table">
          <thead>
            <tr>
              {WORKER_COLUMNS.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {g.workers.map((w) => (
              <tr key={w.id}>
                <td>
                  <button
                    type="button"
                    className="modal-dep-id-link"
                    onClick={() => onOpenWorker(w.id)}
                  >
                    {w.id}
                  </button>
                </td>
                <td>{w.harnessModel}</td>
                <td>{w.account}</td>
                <td>{w.status}</td>
                <td>{w.lastActivity}</td>
                <td>{w.started}</td>
                <td>{w.ended}</td>
                <td>
                  {w.flags.map((f) => (
                    <span key={f} className="worker-stall-badge">
                      {f}
                    </span>
                  ))}
                </td>
                <td>
                  <CopyButton kind="worker status" id={w.id} label="status" onCopy={onCopy} />{" "}
                  <CopyButton kind="worker open" id={w.id} label="open" onCopy={onCopy} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {g.key !== null && detailOpen ? (
        <LeafOrchestrationDetail group={g} onCopy={onCopy} />
      ) : null}
    </div>
  );
}

export function OrchestrationDrawer({
  open,
  onClose,
  nodes,
  onOpenNode,
  onOpenWorker,
  filterLeafId = null,
}: Props) {
  const [loaded, setLoaded] = useState<{ result: OrchestrationLoad; at: Date } | null>(null);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(filterLeafId);
  const [selectionBound, setSelectionBound] = useState({ filterLeafId, open });
  if (selectionBound.filterLeafId !== filterLeafId || selectionBound.open !== open) {
    setSelectionBound({ filterLeafId, open });
    setSelectedKey(filterLeafId);
  }

  const reload = useCallback(async () => {
    setLoading(true);
    const result = await load();
    setLoaded({ result, at: new Date() });
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    return pollOrchestration(() => void reload());
  }, [open, reload]);

  const copy = useCallback(async (kind: CopyKind, id: string) => {
    const cmd = copyCommand(kind, id);
    try {
      await navigator.clipboard.writeText(cmd);
      setNote(`Copied: ${cmd}`);
    } catch {
      setNote("copy failed");
    }
  }, []);

  if (!open) return null;

  const result = loaded?.result ?? null;
  const groups =
    loaded && loaded.result.kind === "ok"
      ? buildOrchestrationView(loaded.result.snapshot, nodes, loaded.at).filter(
          (g) => filterLeafId === null || g.key === filterLeafId,
        )
      : [];
  const outlineKeys = new Set(nodes.map((n) => n.node_key));

  return (
    <ModalFrame
      title="Orchestration"
      titleId="orchestration-drawer-title"
      onClose={onClose}
      storageKey="orchestration"
      footer={note ? <p className="outline-meta">{note}</p> : null}
    >
      <p className="outline-meta">
        Workers on each leaf, from the server&apos;s orchestration snapshot.
        Read-only: nothing here changes a worker, claim or review. Refreshes
        every 15 s while open.
      </p>
      <div className="workspace-notes-actions">
        <button type="button" onClick={() => void reload()}>
          Refresh
        </button>
      </div>
      {loading && !result ? <p className="outline-meta">Loading…</p> : null}
      {result?.kind === "unavailable" ? (
        <p className="workspace-empty">
          This server does not provide the orchestration snapshot yet.
        </p>
      ) : null}
      {result?.kind === "error" ? <p className="outline-meta">{result.message}</p> : null}
      {result?.kind === "ok" && groups.length === 0 ? (
        <p className="workspace-empty">No claim or worker in the snapshot.</p>
      ) : null}
      {groups.map((g) => (
        <GroupView
          key={g.key ?? "(no leaf)"}
          g={g}
          inOutline={g.key !== null && outlineKeys.has(g.key)}
          detailOpen={g.key !== null && g.key === selectedKey}
          onToggleDetail={() =>
            setSelectedKey((cur) => (g.key !== null && cur === g.key ? null : g.key))
          }
          onOpenNode={onOpenNode}
          onOpenWorker={onOpenWorker}
          onCopy={(kind, id) => void copy(kind, id)}
        />
      ))}
    </ModalFrame>
  );
}
