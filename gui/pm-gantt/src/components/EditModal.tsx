import { useEffect, useRef, useState } from "react";
import type { DependencyInheritanceEntry, RoadmapNode } from "../types";
import {
  fetchPlanningArtifacts,
  fetchPlanningFile,
  patchNode,
  savePlanningFile,
} from "../api";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";

type Props = {
  node: RoadmapNode | null;
  /** Explicit vs ancestor-inherited dependency display ids (from API). */
  dependencyInheritance?: DependencyInheritanceEntry;
  onClose: () => void;
  /** Called after a successful autosave so the roadmap can refresh. */
  onPersisted?: () => void;
};

type SavedSnap = {
  title: string;
  status: string;
  path: string;
  content: string;
};

export function EditModal({
  node,
  dependencyInheritance,
  onClose,
  onPersisted,
}: Props) {
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState("Not Started");
  const [files, setFiles] = useState<{ role: string; path: string }[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);

  const lastSaved = useRef<SavedSnap>({
    title: "",
    status: "",
    path: "",
    content: "",
  });

  useEffect(() => {
    if (!node) return;
    setTitle(node.title || "");
    setStatus((node.status as string) || "Not Started");
    setErr(null);
    setPersistMsg(null);
    setHydrated(false);
    fetchPlanningArtifacts(node.id)
      .then((a) => {
        const fs = (a.files || []).map((f) => ({ role: f.role, path: f.path }));
        setFiles(fs);
        const nt = node.title || "";
        const ns = (node.status as string) || "Not Started";
        if (fs.length > 0) {
          setActivePath(fs[0].path);
          lastSaved.current = {
            title: nt,
            status: ns,
            path: "",
            content: "",
          };
        } else {
          setActivePath(null);
          setContent("");
          lastSaved.current = {
            title: nt,
            status: ns,
            path: "",
            content: "",
          };
          setHydrated(true);
        }
      })
      .catch((e: unknown) => {
        setErr(String(e));
        setHydrated(true);
      });
    // Depend on node id only so parent roadmap refresh does not reset the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node?.id]);

  useEffect(() => {
    if (!node) return;
    if (!activePath) {
      setContent("");
      setHydrated(true);
      return;
    }
    setLoading(true);
    setHydrated(false);
    fetchPlanningFile(activePath)
      .then((f) => {
        setContent(f.content);
        lastSaved.current = {
          ...lastSaved.current,
          path: activePath,
          content: f.content,
        };
      })
      .catch((e: unknown) => setErr(String(e)))
      .finally(() => {
        setLoading(false);
        setHydrated(true);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePath, node?.id]);

  useEffect(() => {
    if (!hydrated || !node || loading) return;
    if (title === lastSaved.current.title && status === lastSaved.current.status    ) {
      return;
    }
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      patchNode(node.id, [
        { key: "title", value: title },
        { key: "status", value: status },
      ])
        .then(() => {
          lastSaved.current = { ...lastSaved.current, title, status };
          setPersistMsg("Saved.");
          onPersisted?.();
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          setErr(String(e));
          setPersistMsg(null);
        });
    }, 500);
    return () => window.clearTimeout(t);
  }, [title, status, hydrated, node, loading, onPersisted]);

  useEffect(() => {
    if (!hydrated || !node || loading || !activePath) return;
    if (
      content === lastSaved.current.content &&
      activePath === lastSaved.current.path
    ) {
      return;
    }
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      savePlanningFile(activePath, content)
        .then(() => {
          lastSaved.current = {
            ...lastSaved.current,
            content,
            path: activePath,
          };
          setPersistMsg("Saved.");
          onPersisted?.();
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          setErr(String(e));
          setPersistMsg(null);
        });
    }, 600);
    return () => window.clearTimeout(t);
  }, [content, activePath, hydrated, node, loading, onPersisted]);

  if (!node) return null;

  const footer =
    persistMsg || err ? (
      <>
        {err ? (
          <span style={{ color: "crimson" }}>{err}</span>
        ) : (
          <span>{persistMsg}</span>
        )}
      </>
    ) : null;

  return (
    <ModalFrame
      title={`Edit ${node.id}`}
      titleId="edit-title"
      onClose={onClose}
      footer={footer}
      bodyClassName="modal-body--edit"
    >
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
      {dependencyInheritance != null ? (
        <div className="modal-deps">
          <div className="modal-deps-label">Dependencies (display ids)</div>
          {dependencyInheritance.explicit.length > 0 ? (
            <p className="modal-deps-explicit">
              <strong>Explicit:</strong>{" "}
              {dependencyInheritance.explicit.join(", ")}
            </p>
          ) : null}
          {dependencyInheritance.inherited.length > 0 ? (
            <p className="modal-deps-inherited">
              <strong>Inherited from ancestors:</strong>{" "}
              {dependencyInheritance.inherited.join(", ")}
            </p>
          ) : null}
          {dependencyInheritance.explicit.length === 0 &&
          dependencyInheritance.inherited.length === 0 ? (
            <p className="outline-meta">
              No dependencies (none explicit, none inherited); eligible for parallel
              execution with respect to deps.
            </p>
          ) : null}
          <p className="outline-meta">
            Stored dependencies use stable node keys; edit the roadmap JSON or use
            CLI tools to change explicit deps.
          </p>
        </div>
      ) : null}
      {files.length > 0 ? (
        <div className="modal-edit-planning">
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
          <MarkdownWorkspace
            className="modal-markdown-fill"
            value={content}
            onChange={setContent}
            spellCheck={false}
            defaultViewMode="split"
            sourceLabel="Planning markdown source"
            previewLabel="Planning markdown preview"
          />
        </div>
      ) : (
        <p className="outline-meta">
          No planning_dir or planning files for this node. Set planning_dir on
          the node or run scaffold-planning.
        </p>
      )}
    </ModalFrame>
  );
}
