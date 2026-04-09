import { useEffect, useState } from "react";
import type { RoadmapNode } from "../types";
import {
  fetchPlanningArtifacts,
  fetchPlanningFile,
  patchNode,
  savePlanningFile,
} from "../api";

type Props = {
  node: RoadmapNode | null;
  onClose: () => void;
  onSaved: () => void;
};

export function EditModal({ node, onClose, onSaved }: Props) {
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState("Not Started");
  const [files, setFiles] = useState<{ role: string; path: string }[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!node) return;
    setTitle(node.title || "");
    setStatus((node.status as string) || "Not Started");
    setErr(null);
    setLoading(true);
    fetchPlanningArtifacts(node.id)
      .then((a) => {
        const fs = (a.files || []).map((f) => ({ role: f.role, path: f.path }));
        setFiles(fs);
        if (fs.length > 0) {
          setActivePath(fs[0].path);
          return fetchPlanningFile(fs[0].path);
        }
        setActivePath(null);
        setContent("");
        return null;
      })
      .then((f) => {
        if (f) setContent(f.content);
      })
      .catch((e: unknown) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [node]);

  useEffect(() => {
    if (!activePath || !node) return;
    setLoading(true);
    fetchPlanningFile(activePath)
      .then((f) => setContent(f.content))
      .catch((e: unknown) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [activePath, node]);

  if (!node) return null;

  const saveNodeFields = async () => {
    await patchNode(node.id, [
      { key: "title", value: title },
      { key: "status", value: status },
    ]);
    onSaved();
  };

  const saveFile = async () => {
    if (!activePath) return;
    await savePlanningFile(activePath, content);
    onSaved();
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-labelledby="edit-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id="edit-title">
          Edit {node.id}
        </h2>
        {err ? <p style={{ color: "crimson" }}>{err}</p> : null}
        {loading ? <p>Loading…</p> : null}
        <label>
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {[
              "Not Started",
              "In Progress",
              "Complete",
              "Blocked",
              "Cancelled",
            ].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        {files.length > 0 ? (
          <>
            <label>Planning file</label>
            <select
              value={activePath || ""}
              onChange={(e) => setActivePath(e.target.value || null)}
            >
              {files.map((f) => (
                <option key={f.path} value={f.path}>
                  {f.role}: {f.path}
                </option>
              ))}
            </select>
            <label>Markdown</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
            />
          </>
        ) : (
          <p className="outline-meta">
            No planning_dir or planning files for this node. Set planning_dir on
            the node or run scaffold-planning.
          </p>
        )}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>
            Close
          </button>
          <button type="button" onClick={() => saveNodeFields().then(onClose)}>
            Save fields
          </button>
          {activePath ? (
            <button type="button" onClick={() => saveFile().then(onClose)}>
              Save markdown
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
