import { useEffect, useRef, useState } from "react";
import type { DependencyInheritanceEntry, RoadmapNode } from "../types";
import {
  fetchPlanningArtifacts,
  fetchPlanningFile,
  patchNode,
  savePlanningFile,
  scaffoldPlanning,
} from "../api";
import { getDefaultEditModalRect } from "../modalRect";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";

type Props = {
  node: RoadmapNode | null;
  /** Explicit vs ancestor-inherited dependency display ids (from API). */
  dependencyInheritance?: DependencyInheritanceEntry;
  /** Same maps as the outline table: registry row, PR/MR enrichment, PR hint HTML. */
  registryByNode?: Record<string, Record<string, unknown>>;
  gitEnrichment?: Record<string, Record<string, unknown>>;
  prHints?: Record<string, string>;
  onClose: () => void;
  /** Called after a successful autosave so the roadmap can refresh. */
  onPersisted?: () => void;
};

type SavedSnap = {
  title: string;
  path: string;
  content: string;
};

/** One line for “active work” from registry + Git remote (same sources as the table Dev/meta columns). */
function gitWorkSummary(
  nid: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitEnrichment: Record<string, Record<string, unknown>> | undefined,
  prHints: Record<string, string> | undefined,
): string | null {
  const g = gitEnrichment?.[nid];
  if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
    const title = (g.title as string) || "";
    const author = (g.author as string) || "";
    const url = (g.url as string) || "";
    const bits = [
      title ? `Open PR/MR: ${title}` : "",
      author ? `@${author}` : "",
      url ? url : "",
    ].filter(Boolean);
    if (bits.length) return bits.join(" · ");
  }
  const hint = prHints?.[nid];
  if (hint) return hint.replace(/<br>/g, " · ");
  const reg = registryByNode?.[nid];
  const branch = reg?.branch as string | undefined;
  const started = reg?.started;
  const line = [branch && `branch ${branch}`, started && `started ${started}`]
    .filter(Boolean)
    .join(" · ");
  return line || null;
}

export function EditModal({
  node,
  dependencyInheritance,
  registryByNode,
  gitEnrichment,
  prHints,
  onClose,
  onPersisted,
}: Props) {
  const [title, setTitle] = useState("");
  const [files, setFiles] = useState<{ role: string; path: string }[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [persistMsg, setPersistMsg] = useState<string | null>(null);
  const [scaffolding, setScaffolding] = useState(false);

  const lastSaved = useRef<SavedSnap>({
    title: "",
    path: "",
    content: "",
  });

  useEffect(() => {
    if (!node) return;
    setTitle(node.title || "");
    setErr(null);
    setPersistMsg(null);
    setHydrated(false);
    fetchPlanningArtifacts(node.id)
      .then((a) => {
        const fs = (a.files || []).map((f) => ({ role: f.role, path: f.path }));
        setFiles(fs);
        const nt = node.title || "";
        if (fs.length > 0) {
          setActivePath(fs[0].path);
          lastSaved.current = {
            title: nt,
            path: "",
            content: "",
          };
        } else {
          setActivePath(null);
          setContent("");
          lastSaved.current = {
            title: nt,
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
    if (title === lastSaved.current.title) {
      return;
    }
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      patchNode(node.id, [{ key: "title", value: title }])
        .then(() => {
          lastSaved.current = { ...lastSaved.current, title };
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
  }, [title, hydrated, node, loading, onPersisted]);

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

  const roadmapStatus = (node.status as string) || "Not Started";
  const workLine = gitWorkSummary(
    node.id,
    registryByNode,
    gitEnrichment,
    prHints,
  );

  const onScaffoldPlanning = () => {
    if (!node) return;
    setScaffolding(true);
    setErr(null);
    void scaffoldPlanning(node.id)
      .then(() => {
        onPersisted?.();
        return fetchPlanningArtifacts(node.id);
      })
      .then((a) => {
        const fs = (a.files || []).map((f) => ({ role: f.role, path: f.path }));
        setFiles(fs);
        const nt = node.title || "";
        if (fs.length > 0) {
          setActivePath(fs[0].path);
          lastSaved.current = {
            title: nt,
            path: "",
            content: "",
          };
        } else {
          setActivePath(null);
          setContent("");
          lastSaved.current = {
            title: nt,
            path: "",
            content: "",
          };
          setHydrated(true);
        }
      })
      .catch((e: unknown) => setErr(String(e)))
      .finally(() => setScaffolding(false));
  };

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
      storageKey="edit"
      getDefaultRect={getDefaultEditModalRect}
      footer={footer}
      bodyClassName="modal-body--edit"
    >
      <div className="modal-edit-fields">
        {loading ? <p>Loading…</p> : null}
        <label>
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoComplete="off"
          />
        </label>
        <div className="modal-status-readonly">
          <div className="modal-field-label">Status (roadmap)</div>
          <p className="modal-status-value">{roadmapStatus}</p>
          <p className="outline-meta">
            Not editable here — update the roadmap JSON (or your team’s
            finish/merge workflow). Active work from the Git remote and{" "}
            <code>roadmap/registry.yaml</code> is summarized in the table and
            below when configured.
          </p>
          <div className="modal-field-label">Work signal (Git / registry)</div>
          {workLine ? (
            <p className="modal-git-work-line">{workLine}</p>
          ) : (
            <p className="outline-meta">—</p>
          )}
        </div>
      </div>
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
        <section className="modal-edit-planning-section">
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
              className="modal-markdown-fill constitution-md-workspace"
              value={content}
              onChange={setContent}
              spellCheck
              defaultViewMode="split"
              sourceLabel="Planning markdown source"
              previewLabel="Planning markdown preview"
            />
          </div>
        </section>
      ) : (
        <section className="modal-edit-planning-section modal-edit-planning-section--empty">
          <div className="planning-missing-banner">
            <p>
              No planning folder yet for this node. Create{" "}
              <code>overview.md</code>, <code>plan.md</code>, and{" "}
              <code>tasks.md</code> under <code>planning/&lt;node-id&gt;/</code>{" "}
              and set <code>planning_dir</code> on the node (same as{" "}
              <code>specy-road scaffold-planning &lt;NODE_ID&gt;</code>).
            </p>
            <button
              type="button"
              disabled={scaffolding}
              onClick={onScaffoldPlanning}
            >
              {scaffolding ? "Creating…" : "Create planning folder"}
            </button>
          </div>
        </section>
      )}
    </ModalFrame>
  );
}
