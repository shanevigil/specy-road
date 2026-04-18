import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import type { DependencyInheritanceEntry, RoadmapNode } from "../types";
import {
  fetchPlanningArtifacts,
  fetchPlanningFile,
  getSettings,
  patchNode,
  PmGuiConcurrencyError,
  postLlmReview,
  savePlanningFile,
  scaffoldPlanning,
} from "../api";
import { usePmGuiHandlers } from "../usePmGuiHandlers";
import { hasLlmConfigured } from "../llmConfigured";
import { getDefaultEditModalRect, type ModalRect } from "../modalRect";
import { pmDisplayStatus } from "../pmDisplayStatus";
import { titleToCodename } from "../titleCodename";
import {
  mergeBySectionChoices,
  splitByH2,
} from "../planningSectionUtils";
import { MarkdownWorkspace } from "./MarkdownWorkspace";
import { ModalFrame } from "./ModalFrame";
import { PlanningSheetDiffPane } from "./PlanningSheetDiffPane";

type TitleConflict = {
  hasConflict: boolean;
  peerIds: string[];
  duplicateTitle: boolean;
  duplicateSlug: boolean;
};

function analyzeTitleConflict(
  draftTitle: string,
  selfId: string,
  allNodes: RoadmapNode[],
): TitleConflict {
  const trimmed = draftTitle.trim();
  const slug = titleToCodename(draftTitle);
  const peerIdsTitle = new Set<string>();
  const peerIdsSlug = new Set<string>();
  for (const p of allNodes) {
    if (p.id === selfId) continue;
    if (trimmed.length > 0 && (p.title || "").trim() === trimmed) {
      peerIdsTitle.add(p.id);
    }
    if (slug) {
      const ps = titleToCodename(p.title || "");
      if (ps && ps === slug) peerIdsSlug.add(p.id);
    }
  }
  const duplicateTitle = peerIdsTitle.size > 0;
  const duplicateSlug = peerIdsSlug.size > 0;
  const peerIds = Array.from(
    new Set([...peerIdsTitle, ...peerIdsSlug]),
  ).sort();
  return {
    hasConflict: duplicateTitle || duplicateSlug,
    peerIds,
    duplicateTitle,
    duplicateSlug,
  };
}

type Props = {
  node: RoadmapNode | null;
  /** All roadmap nodes (for duplicate title / slug checks). */
  allNodes?: RoadmapNode[];
  /** Explicit vs ancestor-inherited dependency display ids (from API). */
  dependencyInheritance?: DependencyInheritanceEntry;
  /** Same maps as the outline table: registry row, PR/MR enrichment, PR hint HTML. */
  registryByNode?: Record<string, Record<string, unknown>>;
  /** Outline/Gantt display status after registry + phase subtree rollup (when enabled). */
  pmDisplayStatusResolved?: string;
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
  /** Current git branch matches this task's registered branch — title/planning edits disabled. */
  readOnlyCheckout?: boolean;
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

/** Roadmap deps belong in the graph and Dependencies field, not repeated in markdown. */
const PLANNING_ROADMAP_DEPENDENCY_HINT =
  "Use the Dependencies field above and roadmap ordering on the main view for roadmap structure. Avoid restating milestones or gating in this sheet—they go stale when work moves. LLM Review suggests removing that kind of prose.";

export function EditModal({
  node,
  allNodes = [],
  dependencyInheritance,
  registryByNode,
  pmDisplayStatusResolved,
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
  readOnlyCheckout = false,
}: Props) {
  const { onConcurrencyConflict } = usePmGuiHandlers();
  const [title, setTitle] = useState("");
  /** Repo-relative paths of ancestor feature sheets (read-only context); not editable in this dialog. */
  const [ancestorFiles, setAncestorFiles] = useState<
    { path: string; exists: boolean }[]
  >([]);
  /** This node's single planning file (`planning_dir`); flat layout — no file picker. */
  const [sheetPath, setSheetPath] = useState<string | null>(null);
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
  /** Stable “before” document for diff + merge (set when LLM review completes). */
  const [contentSnapshotAtReview, setContentSnapshotAtReview] = useState<
    string | null
  >(null);
  /** When true, show TipTap + raw proposed text instead of the diff pane. */
  const [showRawCompare, setShowRawCompare] = useState(false);
  const [sectionChoices, setSectionChoices] = useState<
    Array<"before" | "proposed" | null>
  >([]);
  /** Bumps when the user changes selection in the review textarea (for Append selection). */
  const [reviewSelectionTick, setReviewSelectionTick] = useState(0);

  const reviewTextareaRef = useRef<HTMLTextAreaElement>(null);
  const sectionScrollRefs = useRef<(HTMLDivElement | null)[]>([]);

  const titleConflict = useMemo(() => {
    if (!node) {
      return {
        hasConflict: false,
        peerIds: [] as string[],
        duplicateTitle: false,
        duplicateSlug: false,
      };
    }
    return analyzeTitleConflict(title, node.id, allNodes);
  }, [allNodes, node, title]);

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
    setContentSnapshotAtReview(null);
    setShowRawCompare(false);
    setSectionChoices([]);
    setHydrated(false);
    fetchPlanningArtifacts(node.id)
      .then((a) => {
        const anc = (a.ancestor_planning_files || []).map((f) => ({
          path: f.path,
          exists: f.exists !== false,
        }));
        setAncestorFiles(anc);
        const leaf = a.files || [];
        const sheet = leaf.find((x) => x.role === "sheet") || leaf[0];
        const nt = node.title || "";
        if (sheet?.path) {
          setSheetPath(sheet.path);
          lastSaved.current = {
            title: nt,
            path: "",
            content: "",
          };
        } else {
          setSheetPath(null);
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
    // Re-fetch when server renames planning file (title → codename slug) or path otherwise changes.
    // eslint-disable-next-line @eslint-react/exhaustive-deps
  }, [node?.id, node?.planning_dir]);

  useEffect(() => {
    if (!node) return;
    void getSettings()
      .then((s) => {
        const llm = (s.llm as Record<string, unknown>) || {};
        setLlmConfigured(hasLlmConfigured(llm));
      })
      .catch(() => setLlmConfigured(false));
    // eslint-disable-next-line @eslint-react/exhaustive-deps -- global LLM settings; re-check only when switching tasks (id), not on node reference churn
  }, [node?.id]);

  useEffect(() => {
    if (!node) return;
    if (!sheetPath) {
      setContent("");
      setHydrated(true);
      return;
    }
    setLoading(true);
    setHydrated(false);
    fetchPlanningFile(sheetPath)
      .then((f) => {
        setContent(f.content);
        lastSaved.current = {
          ...lastSaved.current,
          path: sheetPath,
          content: f.content,
        };
      })
      .catch((e: unknown) => setErr(String(e)))
      .finally(() => {
        setLoading(false);
        setHydrated(true);
      });
    // eslint-disable-next-line @eslint-react/exhaustive-deps
  }, [sheetPath, node?.id]);

  useEffect(() => {
    if (!hydrated || !node || loading) return;
    if (readOnlyCheckout) return;
    if (titleConflict.hasConflict) return;
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
          if (e instanceof PmGuiConcurrencyError) {
            void onConcurrencyConflict();
            setErr(
              "Roadmap changed elsewhere; refreshed. Re-apply your title if needed.",
            );
            setPersistMsg(null);
            return;
          }
          setErr(String(e));
          setPersistMsg(null);
        });
    }, 500);
    return () => window.clearTimeout(t);
  }, [
    title,
    hydrated,
    node,
    loading,
    onPersisted,
    titleConflict.hasConflict,
    readOnlyCheckout,
    onConcurrencyConflict,
  ]);

  useEffect(() => {
    if (!hydrated || !node || loading || !sheetPath) return;
    if (readOnlyCheckout) return;
    if (
      content === lastSaved.current.content &&
      sheetPath === lastSaved.current.path
    ) {
      return;
    }
    setPersistMsg("Saving…");
    const t = window.setTimeout(() => {
      savePlanningFile(sheetPath, content)
        .then(() => {
          lastSaved.current = {
            ...lastSaved.current,
            content,
            path: sheetPath,
          };
          setPersistMsg("Saved.");
          onPersisted?.();
          window.setTimeout(() => setPersistMsg(null), 2000);
        })
        .catch((e: unknown) => {
          if (e instanceof PmGuiConcurrencyError) {
            void onConcurrencyConflict();
            setErr(
              "Roadmap changed elsewhere; refreshed. Re-apply your planning edits if needed.",
            );
            setPersistMsg(null);
            return;
          }
          setErr(String(e));
          setPersistMsg(null);
        });
    }, 600);
    return () => window.clearTimeout(t);
  }, [
    content,
    sheetPath,
    hydrated,
    node,
    loading,
    onPersisted,
    readOnlyCheckout,
    onConcurrencyConflict,
  ]);

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

  const rawProposedSourceId = useId();

  const diffOriginal = contentSnapshotAtReview ?? content;

  const pairedSectionCount = useMemo(() => {
    if (reviewReport == null || contentSnapshotAtReview == null) return 0;
    return Math.min(
      splitByH2(contentSnapshotAtReview).length,
      splitByH2(reviewReport).length,
    );
  }, [reviewReport, contentSnapshotAtReview]);

  const sectionCountMismatch = useMemo(() => {
    if (reviewReport == null || contentSnapshotAtReview == null) return false;
    return (
      splitByH2(contentSnapshotAtReview).length !==
      splitByH2(reviewReport).length
    );
  }, [reviewReport, contentSnapshotAtReview]);

  const canAcceptReviewMerge = useMemo(
    () =>
      pairedSectionCount > 0 &&
      contentSnapshotAtReview != null &&
      reviewReport != null,
    [pairedSectionCount, contentSnapshotAtReview, reviewReport],
  );

  const noopReviewMarkdown = useCallback(() => {}, []);

  if (!node) return null;

  const persistedRoadmapStatus =
    (node.status as string)?.trim() || "Not Started";
  const pmShownStatus =
    pmDisplayStatusResolved ??
    pmDisplayStatus(node, registryByNode?.[node.id]);
  const pmStatusDiffersFromRoadmap = pmShownStatus !== persistedRoadmapStatus;
  const codename = titleToCodename(title) || "—";
  const titleBarText = `Edit ${node.id} - ${codename} - ${persistedRoadmapStatus}`;

  const workLine = gitWorkSummary(
    node.id,
    registryByNode,
    gitEnrichment,
    prHints,
  );

  const runLlmReview = () => {
    if (!node || readOnlyCheckout) return;
    const sheetSnapshot = content;
    setReviewBusy(true);
    setReviewErr(null);
    void getSettings()
      .then((s) => {
        const llm = (s.llm as Record<string, unknown>) || {};
        return postLlmReview(node.id, llm, sheetSnapshot);
      })
      .then((report) => {
        const paired = Math.min(
          splitByH2(sheetSnapshot).length,
          splitByH2(report).length,
        );
        setContentSnapshotAtReview(sheetSnapshot);
        setSectionChoices(Array.from({ length: paired }, () => null));
        setShowRawCompare(false);
        setReviewReport(report);
      })
      .catch((e: unknown) => {
        setReviewErr(String(e));
        setReviewReport(null);
        setContentSnapshotAtReview(null);
        setSectionChoices([]);
        setShowRawCompare(false);
      })
      .finally(() => setReviewBusy(false));
  };

  const dismissReview = () => {
    setReviewReport(null);
    setReviewErr(null);
    setContentSnapshotAtReview(null);
    setShowRawCompare(false);
    setSectionChoices([]);
  };

  /** After merging, leave diff/preview mode so TipTap shows the updated sheet (autosave runs via content effect). */
  const exitReviewAfterMerge = () => {
    setReviewReport(null);
    setReviewErr(null);
    setContentSnapshotAtReview(null);
    setShowRawCompare(false);
    setSectionChoices([]);
  };

  const applyMergedSheet = () => {
    if (readOnlyCheckout) return;
    if (!contentSnapshotAtReview || reviewReport == null) return;
    if (pairedSectionCount === 0) return;
    const effectiveChoices = Array.from(
      { length: pairedSectionCount },
      (_, i) => sectionChoices[i] ?? "before",
    );
    const merged = mergeBySectionChoices(
      contentSnapshotAtReview,
      reviewReport,
      effectiveChoices,
    );
    setContent(merged);
    exitReviewAfterMerge();
  };

  const acceptAllProposed = () => {
    if (readOnlyCheckout) return;
    if (!contentSnapshotAtReview || reviewReport == null) return;
    if (pairedSectionCount === 0) return;
    const merged = mergeBySectionChoices(
      contentSnapshotAtReview,
      reviewReport,
      Array.from({ length: pairedSectionCount }, () => "proposed" as const),
    );
    setContent(merged);
    exitReviewAfterMerge();
  };

  const chooseSection = (sectionIndex: number, choice: "before" | "proposed") => {
    if (readOnlyCheckout) return;
    setSectionChoices((prev) => {
      const next = [...prev];
      next[sectionIndex] = choice;
      window.setTimeout(() => {
        let j = sectionIndex + 1;
        while (j < next.length && next[j] != null) j += 1;
        if (j < next.length) {
          sectionScrollRefs.current[j]?.scrollIntoView({
            behavior: "smooth",
            block: "nearest",
          });
        }
      }, 0);
      return next;
    });
  };

  const appendToDocument = (chunk: string) => {
    if (readOnlyCheckout) return;
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
    if (!node || readOnlyCheckout) return;
    setScaffolding(true);
    setErr(null);
    void scaffoldPlanning(node.id)
      .then(() => {
        onPersisted?.();
        return fetchPlanningArtifacts(node.id);
      })
      .then((a) => {
        const anc = (a.ancestor_planning_files || []).map((f) => ({
          path: f.path,
          exists: f.exists !== false,
        }));
        setAncestorFiles(anc);
        const leaf = a.files || [];
        const sheet = leaf.find((x) => x.role === "sheet") || leaf[0];
        const nt = node.title || "";
        if (sheet?.path) {
          setSheetPath(sheet.path);
          lastSaved.current = {
            title: nt,
            path: "",
            content: "",
          };
        } else {
          setSheetPath(null);
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
        if (e instanceof PmGuiConcurrencyError) {
          void onConcurrencyConflict();
          setErr(
            "Roadmap changed elsewhere; refreshed. Retry planning scaffold if needed.",
          );
          return;
        }
        setErr(String(e));
      })
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

  const llmReviewDisabled =
    !llmConfigured || reviewBusy || readOnlyCheckout;
  const llmReviewTitle = readOnlyCheckout
    ? "Editing is disabled while this task's registered branch is checked out"
    : llmConfigured
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
        <label
          className={
            titleConflict.hasConflict
              ? "modal-edit-title-wrap modal-edit-title-wrap--invalid"
              : "modal-edit-title-wrap"
          }
        >
          Title
          <input
            value={title}
            readOnly={readOnlyCheckout}
            onChange={(e) => setTitle(e.target.value)}
            autoComplete="off"
            aria-invalid={titleConflict.hasConflict}
            aria-describedby={
              titleConflict.hasConflict ? `${titleIdAttr}-title-err` : undefined
            }
          />
          {titleConflict.hasConflict ? (
            <p
              className="modal-edit-title-error"
              id={`${titleIdAttr}-title-err`}
              role="alert"
            >
              <strong>Title taken.</strong> Another item already uses
              {titleConflict.duplicateTitle && titleConflict.duplicateSlug
                ? " this exact title or the same codename slug"
                : titleConflict.duplicateTitle
                  ? " this exact title"
                  : " the same codename slug"}{" "}
              (see {titleConflict.peerIds.join(", ")}). Add a number, phase name,
              or short qualifier so items stay distinct.
            </p>
          ) : null}
        </label>
        {workLine ? (
          <p className="modal-edit-work-line" title={workLine}>
            {workLine}
          </p>
        ) : null}
        {pmStatusDiffersFromRoadmap ? (
          <p className="outline-meta">
            PM Gantt shows <strong>{pmShownStatus}</strong> in the outline while this node is
            registered in <code>roadmap/registry.yaml</code>; the saved roadmap status is{" "}
            <strong>{persistedRoadmapStatus}</strong>.
          </p>
        ) : null}
        {readOnlyCheckout ? (
          <p className="outline-meta" role="status">
            The title and planning sheet are read-only while this task is in active development
            (in progress, open or merged merge request, or this checkout matches the registered
            branch).
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
      {sheetPath != null ? (
        <section className="modal-edit-planning-section">
          <div className="modal-edit-planning-toolbar">
            <div className="modal-edit-planning-path-wrap">
              <span className="modal-edit-planning-file-text">Planning</span>
              <code className="modal-edit-planning-path" title={sheetPath}>
                {sheetPath}
              </code>
            </div>
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
          <p
            className="modal-edit-planning-roadmap-hint outline-meta"
            role="note"
          >
            {PLANNING_ROADMAP_DEPENDENCY_HINT}
          </p>
          {ancestorFiles.length > 0 ? (
            <p className="modal-edit-planning-ancestors outline-meta">
              <span className="modal-edit-planning-ancestors-label">
                Ancestor sheets
              </span>
              {ancestorFiles.map((f) => (
                <span key={f.path} className="modal-edit-planning-ancestor-item">
                  <code
                    className={
                      f.exists
                        ? "modal-edit-planning-ancestor-path"
                        : "modal-edit-planning-ancestor-path modal-edit-planning-ancestor-path--missing"
                    }
                    title={f.path}
                  >
                    {f.path}
                  </code>
                </span>
              ))}
            </p>
          ) : null}
          {reviewErr ? (
            <p className="modal-review-error modal-review-error--toolbar">
              {reviewErr}
            </p>
          ) : null}
          {reviewReport == null ? (
            <div className="modal-edit-review-split modal-edit-review-split--single">
              <div className="modal-edit-md-column">
                <MarkdownWorkspace
                  className="modal-markdown-fill constitution-md-workspace"
                  value={content}
                  onChange={setContent}
                  disabled={readOnlyCheckout}
                  spellCheck
                  editorLabel="Planning markdown"
                />
              </div>
            </div>
          ) : showRawCompare ? (
            <div className="modal-edit-review-split modal-edit-review-split--raw-compare">
              <div className="modal-edit-md-column">
                <MarkdownWorkspace
                  className="modal-markdown-fill constitution-md-workspace"
                  value={content}
                  onChange={setContent}
                  disabled={readOnlyCheckout}
                  spellCheck
                  editorLabel="Planning markdown"
                />
              </div>
              <div className="modal-edit-raw-proposed-panel">
                <p
                  className="modal-edit-planning-roadmap-hint modal-edit-planning-roadmap-hint--review outline-meta"
                  role="note"
                >
                  {PLANNING_ROADMAP_DEPENDENCY_HINT}
                </p>
                <div className="modal-edit-review-actions modal-edit-review-actions--raw">
                  <button
                    type="button"
                    onClick={() => setShowRawCompare(false)}
                  >
                    Back to diff
                  </button>
                  <button type="button" onClick={() => dismissReview()}>
                    Close LLM Review
                  </button>
                  <button
                    type="button"
                    onClick={() => appendSelectionFromReview()}
                    disabled={readOnlyCheckout || !hasReviewTextSelection}
                    title="Append selected text from the markdown source below"
                  >
                    Append selection
                  </button>
                  <button
                    type="button"
                    onClick={() => appendEntireReport()}
                    disabled={readOnlyCheckout}
                    title="Append the full proposed sheet to the planning document"
                  >
                    Append proposed sheet
                  </button>
                  <button
                    type="button"
                    onClick={() => applyMergedSheet()}
                    disabled={readOnlyCheckout || !canAcceptReviewMerge}
                    title={
                      canAcceptReviewMerge
                        ? "Merge paired sections: uses Proposed where you chose it; unmarked sections use the before (snapshot) text"
                        : "Nothing to merge"
                    }
                  >
                    Accept selections
                  </button>
                  <button
                    type="button"
                    onClick={() => acceptAllProposed()}
                    disabled={readOnlyCheckout || !canAcceptReviewMerge}
                    title={
                      canAcceptReviewMerge
                        ? "Use the proposed text for every paired section"
                        : "Nothing to merge"
                    }
                  >
                    Accept all (proposed)
                  </button>
                </div>
                <p className="modal-edit-raw-proposed-label">Proposed sheet</p>
                <MarkdownWorkspace
                  className="modal-edit-proposed-preview-md constitution-md-workspace"
                  value={reviewReport}
                  onChange={noopReviewMarkdown}
                  disabled
                  showToolbar={false}
                  editorLabel="Proposed sheet preview"
                />
                <details className="planning-review-source-details">
                  <summary>Markdown source (for precise selection)</summary>
                  <label
                    className="modal-edit-raw-proposed-label modal-edit-raw-proposed-label--source"
                    htmlFor={rawProposedSourceId}
                  >
                    Markdown source
                  </label>
                  <textarea
                    id={rawProposedSourceId}
                    ref={reviewTextareaRef}
                    className="planning-review-raw-textarea planning-review-raw-textarea--panel"
                    readOnly
                    value={reviewReport}
                    aria-label="Markdown source for proposed sheet"
                    onSelect={() => setReviewSelectionTick((n) => n + 1)}
                    onMouseUp={() => setReviewSelectionTick((n) => n + 1)}
                    onKeyUp={() => setReviewSelectionTick((n) => n + 1)}
                  />
                </details>
                <div className="modal-edit-review-actions modal-edit-review-actions--raw modal-edit-review-actions--diff-bottom">
                  <button
                    type="button"
                    onClick={() => setShowRawCompare(false)}
                  >
                    Back to diff
                  </button>
                  <button type="button" onClick={() => dismissReview()}>
                    Close LLM Review
                  </button>
                  <button
                    type="button"
                    onClick={() => appendSelectionFromReview()}
                    disabled={readOnlyCheckout || !hasReviewTextSelection}
                    title="Append selected text from the markdown source above"
                  >
                    Append selection
                  </button>
                  <button
                    type="button"
                    onClick={() => appendEntireReport()}
                    disabled={readOnlyCheckout}
                    title="Append the full proposed sheet to the planning document"
                  >
                    Append proposed sheet
                  </button>
                  <button
                    type="button"
                    onClick={() => applyMergedSheet()}
                    disabled={readOnlyCheckout || !canAcceptReviewMerge}
                    title={
                      canAcceptReviewMerge
                        ? "Merge paired sections: uses Proposed where you chose it; unmarked sections use the before (snapshot) text"
                        : "Nothing to merge"
                    }
                  >
                    Accept selections
                  </button>
                  <button
                    type="button"
                    onClick={() => acceptAllProposed()}
                    disabled={readOnlyCheckout || !canAcceptReviewMerge}
                    title={
                      canAcceptReviewMerge
                        ? "Use the proposed text for every paired section"
                        : "Nothing to merge"
                    }
                  >
                    Accept all (proposed)
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="modal-edit-review-diff-full">
              <p
                className="modal-edit-planning-roadmap-hint modal-edit-planning-roadmap-hint--review outline-meta"
                role="note"
              >
                {PLANNING_ROADMAP_DEPENDENCY_HINT}
              </p>
              <div className="modal-edit-review-actions modal-edit-review-actions--diff">
                <button type="button" onClick={() => dismissReview()}>
                  Close LLM Review
                </button>
                <button
                  type="button"
                  onClick={() => setShowRawCompare(true)}
                  title="Side-by-side editor and rendered proposed sheet"
                >
                  Proposed preview
                </button>
                <button
                  type="button"
                  onClick={() => applyMergedSheet()}
                  disabled={readOnlyCheckout || !canAcceptReviewMerge}
                  title={
                    canAcceptReviewMerge
                      ? "Merge paired sections: uses Proposed where you chose it; unmarked sections use the before (snapshot) text"
                      : "Nothing to merge"
                  }
                >
                  Accept selections
                </button>
                <button
                  type="button"
                  onClick={() => acceptAllProposed()}
                  disabled={readOnlyCheckout || !canAcceptReviewMerge}
                  title={
                    canAcceptReviewMerge
                      ? "Use the proposed text for every paired section"
                      : "Nothing to merge"
                  }
                >
                  Accept all (proposed)
                </button>
              </div>
              {sectionCountMismatch ? (
                <p
                  className="modal-review-section-mismatch"
                  role="status"
                >
                  This sheet and the proposal have different numbers of{" "}
                  <code>##</code> sections. Only the first {pairedSectionCount}{" "}
                  paired sections are merged; unpaired trailing content stays
                  visible in the diff but is omitted from the merged result—use
                  proposed preview if you need to copy it.
                </p>
              ) : null}
              <PlanningSheetDiffPane
                originalMarkdown={diffOriginal}
                proposedMarkdown={reviewReport}
                pairedSectionCount={pairedSectionCount}
                sectionChoices={sectionChoices}
                onSectionChoice={chooseSection}
                sectionScrollRefs={sectionScrollRefs}
              />
              <div className="modal-edit-review-actions modal-edit-review-actions--diff modal-edit-review-actions--diff-bottom">
                <button type="button" onClick={() => dismissReview()}>
                  Close LLM Review
                </button>
                <button
                  type="button"
                  onClick={() => setShowRawCompare(true)}
                  title="Side-by-side editor and rendered proposed sheet"
                >
                  Proposed preview
                </button>
                <button
                  type="button"
                  onClick={() => applyMergedSheet()}
                  disabled={readOnlyCheckout || !canAcceptReviewMerge}
                  title={
                    canAcceptReviewMerge
                      ? "Merge paired sections: uses Proposed where you chose it; unmarked sections use the before (snapshot) text"
                      : "Nothing to merge"
                  }
                >
                  Accept selections
                </button>
                <button
                  type="button"
                  onClick={() => acceptAllProposed()}
                  disabled={readOnlyCheckout || !canAcceptReviewMerge}
                  title={
                    canAcceptReviewMerge
                      ? "Use the proposed text for every paired section"
                      : "Nothing to merge"
                  }
                >
                  Accept all (proposed)
                </button>
              </div>
            </div>
          )}
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
              disabled={scaffolding || readOnlyCheckout}
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
