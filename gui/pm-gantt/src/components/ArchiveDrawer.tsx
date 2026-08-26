import { useCallback, useEffect, useState } from "react";
import {
  createArchive,
  deepenArchive,
  fetchArchives,
  previewArchive,
  restoreArchive,
} from "../api";
import type { ArchiveRecord, ArchivesResponse } from "../types";
import { ModalFrame } from "./ModalFrame";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Reload the roadmap after any write — archiving changes the live graph. */
  onChanged: () => void;
};

function gitLine(rec: ArchiveRecord): string {
  const g = rec.git ?? {};
  const bits: string[] = [];
  if (g.nearest_tag) bits.push(`tag ${g.nearest_tag}`);
  if (g.merge_commit) bits.push(`merge ${g.merge_commit.slice(0, 12)}`);
  if (g.rollup_branch) bits.push(g.rollup_branch);
  // Every provenance field is best-effort; say so rather than showing a blank.
  return bits.length ? bits.join(" · ") : "no git provenance recorded";
}

export function ArchiveDrawer({ open, onClose, onChanged }: Props) {
  const [data, setData] = useState<ArchivesResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState("");
  const [preview, setPreview] = useState<string[] | null>(null);
  const [deep, setDeep] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setData(await fetchArchives());
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const run = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      setBusy(true);
      setMsg(null);
      try {
        await fn();
        setMsg(label);
        setPreview(null);
        await refresh();
        onChanged();
      } catch (e) {
        setMsg(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [refresh, onChanged],
  );

  const doPreview = useCallback(async () => {
    try {
      setPreview((await previewArchive(selectedNode)).summary);
      setMsg(null);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }, [selectedNode]);

  if (!open) return null;

  const eligible = data?.eligible ?? [];
  const records = data?.records ?? [];

  return (
    <ModalFrame
      title="Archive"
      onClose={onClose}
      storageKey="pm-gui.archive-drawer"
      footer={
        msg ? (
          <span className="archive-msg" role="status">
            {msg}
          </span>
        ) : null
      }
    >
      <section className="archive-section">
        <h3>Archive completed work</h3>
        {eligible.length === 0 ? (
          <p className="archive-empty">
            Nothing is complete enough to archive yet. A subtree becomes
            eligible when every leaf under it is Complete.
          </p>
        ) : (
          <div className="archive-create">
            <select
              value={selectedNode}
              onChange={(e) => {
                setSelectedNode(e.target.value);
                setPreview(null);
              }}
              disabled={busy}
              aria-label="Subtree to archive"
            >
              <option value="">Select a completed subtree…</option>
              {eligible.map((e) => (
                <option key={e.node_id} value={e.node_id}>
                  {e.node_id} — {e.title}
                </option>
              ))}
            </select>
            <label className="archive-deep-toggle">
              <input
                type="checkbox"
                checked={deep}
                onChange={(e) => setDeep(e.target.checked)}
                disabled={busy}
              />
              Deep archive (bundle into a tarball)
            </label>
            <button
              type="button"
              disabled={!selectedNode || busy}
              onClick={() => void doPreview()}
            >
              Preview
            </button>
            <button
              type="button"
              disabled={!selectedNode || busy}
              onClick={() =>
                void run(`Archived ${selectedNode}.`, () =>
                  createArchive(selectedNode, { deep }),
                )
              }
            >
              Archive
            </button>
          </div>
        )}
        {preview ? (
          <pre className="archive-preview" aria-label="Archive preview">
            {preview.join("\n")}
          </pre>
        ) : null}
      </section>

      <section className="archive-section">
        <h3>Archived ({records.length})</h3>
        {records.length === 0 ? (
          <p className="archive-empty">No archives yet.</p>
        ) : (
          <ul className="archive-list">
            {records.map((rec) => (
              <li key={rec.archive_id} className="archive-item">
                <div className="archive-item-head">
                  <strong>{rec.root_node_id}</strong>
                  <span className={`archive-depth archive-depth--${rec.depth}`}>
                    {rec.depth}
                  </span>
                  <span className="archive-when">{rec.archived_at}</span>
                </div>
                <div className="archive-item-nodes">
                  {rec.nodes_summary.map((n) => n.id).join(", ")}
                </div>
                <div className="archive-item-git">{gitLine(rec)}</div>
                <div className="archive-item-actions">
                  {rec.depth === "shallow" ? (
                    <button
                      type="button"
                      disabled={busy}
                      title="Bundle into a tarball; only a reference file stays browsable"
                      onClick={() =>
                        void run(`Deep-archived ${rec.archive_id}.`, () =>
                          deepenArchive(rec.archive_id),
                        )
                      }
                    >
                      Deep archive
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    title="Put this subtree back into the live roadmap"
                    onClick={() =>
                      void run(`Restored ${rec.root_node_id}.`, () =>
                        restoreArchive(rec.archive_id),
                      )
                    }
                  >
                    Restore
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </ModalFrame>
  );
}
