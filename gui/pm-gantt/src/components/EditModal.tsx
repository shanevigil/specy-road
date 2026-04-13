import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DependencyInheritanceEntry, RoadmapNode } from "../types";
import {
  fetchPlanningArtifacts,
  fetchPlanningFile,
  getSettings,
  patchNode,
  postLlmReview,
  savePlanningFile,
  scaffoldPlanning,
} from "../api";
import { hasLlmConfigured } from "../llmConfigured";
import { getDefaultEditModalRect, type ModalRect } from "../modalRect";
import { titleToCodename } from "../titleCodename";
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
  /** Open another task in a new dialog (dependency id). */
  onOpenNode?: (nodeId: string) => void;
  /** Called after a successful autosave so the roadmap can refresh. */
  onPersisted?: () => void;
  /** localStorage key suffix for size/position (one per open dialog). */
  modalStorageKey: string;
  /** Global stacking order for this dialog (higher = on top). */
  stackZIndex?: number;
  /** Multiple task dialogs: backdrop does not dim or block the rest of the UI. */
  backdropPassThrough?: boolean;
  /** Only the topmost stacked dialog should close on Escape. */
  closeOnEscape?: boolean;
  /** Keep the window below the app header (viewport Y of header bottom). */
  headerMinTop: number;
  /** First-open position (stacked offset); consumed after layout. */
  spawnInitialRect?: ModalRect;
  /** Tile layout: parent positions all task windows. */
  editTileMode?: boolean;
  tileRect?: ModalRect | null;
  /** Positions to restore when leaving tile mode. */
  resumeFreeRect?: ModalRect | null;
  /** Focused task dialog (accent title bar). */
  titleBarActive?: boolean;
  /** User focused this dialog (bring to front). */
  onActivate?: () => void;
  /** Report position/size for stacking and tile restore. */
  onRectCommit?: (r: ModalRect) => void;
};

type SavedSnap = {
  title: string;
  path: string;
  content: string;
};

/** Explicit first, then inherited-only ids (inherited list includes both). */
function dependencyLineItems(
  entry: DependencyInheritanceEntry,
): { id: string; inheritedOnly: boolean }[] {
  const explicit = new Set(entry.explicit);
  const out: { id: string; inheritedOnly: boolean }[] = [];
  for (const id of entry.explicit) {
    out.push({ id, inheritedOnly: false });
  }
  for (const id of entry.inherited) {
    if (!explicit.has(id)) {
      out.push({ id, inheritedOnly: true });
    }
  }
  return out;
}

/** One line for “active work” from registry + Git remote (same sources as the table Dev/meta columns). */
function gitWorkSummary(
  nid: string,
  registryByNode: Record<string, Record<string, unknown>> | undefined,
  gitEnrichment: Record<string, Record<string, unknown>> | undefined,
  prHints: Record<string, string> | undefined,
): string | null {
  const g = gitEnrichment?.[nid];
  if (g?.kind === "github_pr" || g?.kind === "gitlab_mr") {
    const prTitle = (g.title as string) || "";
    const author = (g.author as string) || "";
    const url = (g.url as string) || "";
    const bits = [
      prTitle ? `Open PR/MR: ${prTitle}` : "",
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
  onOpenNode,
  onPersisted,
  modalStorageKey,
  stackZIndex = 50,
  backdropPassThrough = false,
  closeOnEscape = true,
  headerMinTop,
  spawnInitialRect,
  editTileMode = false,
  tileRect = null,
  resumeFreeRect = null,
  titleBarActive = false,
  onActivate,
  onRectCommit,
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
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewReport, setReviewReport] = useState<string | null>(null);
  const [reviewErr, setReviewErr] = useState<string | null>(null);
  const [llmConfigured, setLlmConfigured] = useState(false);
  /** Bumps when the user changes selection in the review textarea (for Append selection). */
  const [reviewSelectionTick, setReviewSelectionTick] = useState(0);

  const reviewTextareaRef = useRef<HTMLTextAreaElement>(null);

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
    setReviewReport(null);
    setReviewErr(null);
    setHydrated(false);
    fetchPlanningArtifacts(node.id)
      .then((a) => {
        const anc = (a.ancestor_planning_files || []).map((f) => ({
          role: f.role || "ancestor",
          path: f.path,
        }));
        const leaf = (a.files || []).map((f) => ({ role: f.role, path: f.path }));
        const fs = [...anc, ...leaf];
        setFiles(fs);
        const nt = node.title || "";
        if (fs.length > 0) {
          const sheet = leaf.find((x) => x.role === "sheet");
          setActivePath(sheet ? sheet.path : fs[0].path);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node?.id]);

  useEffect(() => {
    if (!node) return;
    void getSettings()
      .then((s) => {
        const llm = (s.llm as Record<string, unknown>) || {};
        setLlmConfigured(hasLlmConfigured(llm));
      })
      .catch(() => setLlmConfigured(false));
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

  const depItems = useMemo(
    () =>
      dependencyInheritance != null
        ? dependencyLineItems(dependencyInheritance)
        : [],
    [dependencyInheritance],
  );

  const titleIdAttr = `edit-title-${modalStorageKey.replace(/[^a-zA-Z0-9_.-]/g, "_")}`;

  const getDefaultRect = useCallback(
    () => getDefaultEditModalRect({ minTop: headerMinTop }),
    [headerMinTop],
  );

  if (!node) return null;

  const roadmapStatus = (node.status as string) || "Not Started";
  const codename = titleToCodename(title) || "—";
  const titleBarText = `Edit ${node.id} - ${codename} - ${roadmapStatus}`;

  const workLine = gitWorkSummary(
    node.id,
    registryByNode,
    gitEnrichment,
    prHints,
  );

  const runLlmReview = () => {
    if (!node) return;
    setReviewBusy(true);
    setReviewErr(null);
    void getSettings()
      .then((s) => {
        const llm = (s.llm as Record<string, unknown>) || {};
        return postLlmReview(node.id, llm);
      })
      .then((report) => {
        setReviewReport(report);
      })
      .catch((e: unknown) => {
        setReviewErr(String(e));
        setReviewReport(null);
      })
      .finally(() => setReviewBusy(false));
  };

  const dismissReview = () => {
    setReviewReport(null);
    setReviewErr(null);
  };

  const appendToDocument = (chunk: string) => {
    const t = chunk.trim();
    if (!t) return;
    setContent((prev) => {
      const p = prev.replace(/\s+$/, "");
      return p ? `${p}\n\n${t}\n` : `${t}\n`;
    });
  };

  const appendSelectionFromReview = () => {
    const el = reviewTextareaRef.current;
    if (!el) return;
    const a = el.selectionStart;
    const b = el.selectionEnd;
    const slice = reviewReport?.slice(
      Math.min(a, b),
      Math.max(a, b),
    );
    if (slice?.trim()) appendToDocument(slice);
  };

  const appendEntireReport = () => {
    if (reviewReport) appendToDocument(reviewReport);
  };

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
        const anc = (a.ancestor_planning_files || []).map((f) => ({
          role: f.role || "ancestor",
          path: f.path,
        }));
        const leaf = (a.files || []).map((f) => ({ role: f.role, path: f.path }));
        const fs = [...anc, ...leaf];
        setFiles(fs);
        const nt = node.title || "";
        if (fs.length > 0) {
          const sheet = leaf.find((x) => x.role === "sheet");
          setActivePath(sheet ? sheet.path : fs[0].path);
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

  void reviewSelectionTick;
  const hasReviewTextSelection = (() => {
    const el = reviewTextareaRef.current;
    if (!el || !reviewReport) return false;
    const a = el.selectionStart;
    const b = el.selectionEnd;
    return (
      a !== b &&
      reviewReport.slice(Math.min(a, b), Math.max(a, b)).trim() !== ""
    );
  })();

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

  const llmReviewDisabled = !llmConfigured || reviewBusy;
  const llmReviewTitle = llmConfigured
    ? "Have an LLM provide a suggested clean up"
    : "Configure an LLM in Settings to enable this";

  return (
    <ModalFrame
      title={titleBarText}
      titleTooltip={titleBarText}
      titleId={titleIdAttr}
      onClose={onClose}
      storageKey={`edit-${modalStorageKey}`}
      getDefaultRect={getDefaultRect}
      initialRectOverride={spawnInitialRect}
      minTop={headerMinTop}
      forcedRect={editTileMode && tileRect ? tileRect : null}
      resumeFreeRect={resumeFreeRect ?? null}
      suppressPositionPersist={editTileMode}
      titleBarActive={titleBarActive}
      onActivate={onActivate}
      onRectCommit={onRectCommit}
      footer={footer}
      bodyClassName="modal-body--edit"
      zIndex={stackZIndex}
      backdropPassThrough={backdropPassThrough}
      closeOnEscape={closeOnEscape}
    >
      <div className="modal-edit-fields">
        {loading ? <p className="modal-edit-loading">Loading…</p> : null}
        <label>
          Title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoComplete="off"
          />
        </label>
        {workLine ? (
          <p className="modal-edit-work-line" title={workLine}>
            {workLine}
          </p>
        ) : null}
      </div>
      {dependencyInheritance != null ? (
        <div className="modal-deps-line">
          <span className="modal-deps-line-label">Dependencies:</span>{" "}
          {depItems.length > 0 ? (
            <span className="modal-deps-line-ids">
              {depItems.map(({ id, inheritedOnly }) => (
                <button
                  key={id}
                  type="button"
                  className={
                    inheritedOnly
                      ? "modal-dep-id-link modal-dep-id-link--inherited"
                      : "modal-dep-id-link"
                  }
                  title={
                    inheritedOnly
                      ? `Open task ${id} (inherited from ancestors)`
                      : `Open task ${id}`
                  }
                  onClick={() => onOpenNode?.(id)}
                >
                  {id}
                </button>
              ))}
            </span>
          ) : (
            <span className="modal-deps-none">None</span>
          )}
        </div>
      ) : null}
      {files.length > 0 ? (
        <section className="modal-edit-planning-section">
          <div className="modal-edit-planning-toolbar">
            <label className="modal-edit-planning-file-label">
              <span className="modal-edit-planning-file-text">Planning file</span>
              <select
                className="modal-edit-planning-select"
                value={activePath || ""}
                onChange={(e) => setActivePath(e.target.value || null)}
              >
                {files.map((f) => (
                  <option key={f.path} value={f.path}>
                    {f.role}: {f.path}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="modal-edit-llm-review-btn"
              disabled={llmReviewDisabled}
              title={llmReviewTitle}
              aria-label="LLM Review. Have an LLM provide a suggested clean up"
              onClick={() => runLlmReview()}
            >
              {reviewBusy ? "Running…" : "LLM Review"}
            </button>
          </div>
          {reviewErr ? (
            <p className="modal-review-error modal-review-error--toolbar">
              {reviewErr}
            </p>
          ) : null}
          <div
            className={
              reviewReport != null
                ? "modal-edit-review-split"
                : "modal-edit-review-split modal-edit-review-split--single"
            }
          >
            <div className="modal-edit-md-column">
              <MarkdownWorkspace
                className="modal-markdown-fill constitution-md-workspace"
                value={content}
                onChange={setContent}
                spellCheck
                editorLabel="Planning markdown"
              />
            </div>
            {reviewReport != null ? (
              <div className="modal-edit-review-pane">
                <div className="modal-edit-review-actions">
                  <button type="button" onClick={() => dismissReview()}>
                    Dismiss
                  </button>
                  <button
                    type="button"
                    onClick={() => appendSelectionFromReview()}
                    disabled={!hasReviewTextSelection}
                    title="Append selected text from the report to the planning document"
                  >
                    Append selection
                  </button>
                  <button
                    type="button"
                    onClick={() => appendEntireReport()}
                    title="Append the full report to the planning document"
                  >
                    Append entire report
                  </button>
                </div>
                <textarea
                  ref={reviewTextareaRef}
                  className="modal-edit-review-textarea"
                  readOnly
                  value={reviewReport}
                  aria-label="LLM review report"
                  onSelect={() => setReviewSelectionTick((n) => n + 1)}
                  onMouseUp={() => setReviewSelectionTick((n) => n + 1)}
                  onKeyUp={() => setReviewSelectionTick((n) => n + 1)}
                />
              </div>
            ) : null}
          </div>
        </section>
      ) : (
        <section className="modal-edit-planning-section modal-edit-planning-section--empty">
          <div className="planning-missing-banner">
            <p>
              No feature sheet yet for this node. Run{" "}
              <code>specy-road scaffold-planning &lt;NODE_ID&gt;</code> to create{" "}
              <code>planning/&lt;id&gt;_&lt;slug&gt;_&lt;node_key&gt;.md</code> and
              set <code>planning_dir</code>.
            </p>
            <button
              type="button"
              disabled={scaffolding}
              onClick={onScaffoldPlanning}
            >
              {scaffolding ? "Creating…" : "Create planning file"}
            </button>
          </div>
        </section>
      )}
    </ModalFrame>
  );
}
