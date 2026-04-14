import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  addNode,
  deleteNode,
  fetchGovernanceCompletion,
  fetchRoadmap,
  fetchRoadmapFingerprint,
  indentNode,
  outdentNode,
  patchNode,
} from "./api";
import {
  computeSpawnRect,
  computeTileRects,
  sortOpenIdsByDependencyOrder,
} from "./editModalLayout";
import type { ModalRect } from "./modalRect";
import type { RoadmapNode, RoadmapResponse } from "./types";
import { transitiveEffectivePrereqIds } from "./depChain";
import { GitWorkflowStatusLabel } from "./components/GitWorkflowStatusLabel";
import { GanttPane } from "./components/GanttPane";
import { OutlineTable } from "./components/OutlineTable";
import { EditModal } from "./components/EditModal";
import { ConstitutionDrawer } from "./components/ConstitutionDrawer";
import { SettingsDrawer, type ThemeMode } from "./components/SettingsDrawer";
import { SharedDocsDrawer } from "./components/SharedDocsDrawer";
import { VisionDrawer } from "./components/VisionDrawer";
import { WorkNotesDrawer } from "./components/WorkNotesDrawer";
import {
  IconGear,
  IconIndent,
  IconOutdent,
  IconPencil,
  IconRowAbove,
  IconRowBelow,
  IconTrash,
} from "./toolbarIcons";

const SPLIT_STORAGE_KEY = "pmGanttSplitPct";
const REFRESH_STORAGE_KEY = "pmGanttRefreshSec";
const INHERITED_DEPS_STORAGE_KEY = "pmGanttShowInheritedDeps";
const HIGHLIGHT_DEP_CHAIN_KEY = "pmGanttHighlightDepChain";
const THEME_MODE_STORAGE_KEY = "pmGanttThemeMode";

function readStoredThemeMode(): ThemeMode {
  try {
    const s = localStorage.getItem(THEME_MODE_STORAGE_KEY);
    if (s === "light" || s === "dark" || s === "system") return s;
  } catch {
    /* ignore */
  }
  return "system";
}

function nodesByIdFrom(nodes: RoadmapNode[]): Record<string, RoadmapNode> {
  return Object.fromEntries(nodes.map((n) => [n.id, n]));
}

function promptNewTaskTitle(): string | null {
  const t = window.prompt("Title for new feature");
  return t?.trim() || null;
}

/** Last path segment of repo root (e.g. `.../specy-road/playground` → `playground`). */
function repoRootFolderDisplayName(repoRoot: string): string {
  const t = repoRoot.trim().replace(/[/\\]+$/, "");
  if (!t) return "";
  const parts = t.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] ?? t;
}

export default function App() {
  const [data, setData] = useState<RoadmapResponse | null>(null);
  const [repo, setRepo] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  /** Node ids with an open edit dialog (order = stack; last is topmost). */
  const [editOpenIds, setEditOpenIds] = useState<string[]>([]);
  /** Which task dialog is focused (accent title bar, receives new-dialog offset anchor). */
  const [focusedEditNodeId, setFocusedEditNodeId] = useState<string | null>(
    null,
  );
  /** One-time initial rect for a newly opened dialog (stacked offset). */
  const [spawnRects, setSpawnRects] = useState<Record<string, ModalRect>>({});
  /** Tile open task dialogs left-to-right by dependency order. */
  const [editTileMode, setEditTileMode] = useState(false);
  const [tileRects, setTileRects] = useState<Record<string, ModalRect> | null>(
    null,
  );
  const [resumeAfterUntile, setResumeAfterUntile] = useState<Record<
    string,
    ModalRect
  > | null>(null);
  const editRectsRef = useRef<Record<string, ModalRect>>({});
  const focusedEditNodeIdRef = useRef<string | null>(null);
  const headerBottomRef = useRef(0);
  const preTileRectsRef = useRef<Record<string, ModalRect>>({});
  const headerRef = useRef<HTMLElement>(null);
  const [headerBottomPx, setHeaderBottomPx] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [constitutionOpen, setConstitutionOpen] = useState(false);
  const [visionOpen, setVisionOpen] = useState(false);
  const [sharedDocsOpen, setSharedDocsOpen] = useState(false);
  const [workNotesOpen, setWorkNotesOpen] = useState(false);
  /** When set, Vision / Constitution need human content beyond blank or starter templates. */
  const [govCompletion, setGovCompletion] = useState<{
    vision: boolean;
    constitution: boolean;
  } | null>(null);

  const [refreshSec, setRefreshSec] = useState(() => {
    try {
      const s = localStorage.getItem(REFRESH_STORAGE_KEY);
      if (s !== null) {
        const n = parseInt(s, 10);
        if (!Number.isNaN(n) && n >= 0 && n <= 120) return n;
      }
    } catch {
      /* ignore */
    }
    return 5;
  });

  const lastFingerprintRef = useRef<number | null>(null);

  const [splitPct, setSplitPct] = useState(() => {
    try {
      const s = localStorage.getItem(SPLIT_STORAGE_KEY);
      if (s) {
        const n = Number(s);
        if (!Number.isNaN(n) && n >= 15 && n <= 85) return n;
      }
    } catch {
      /* ignore */
    }
    return 42;
  });

  /** Dashed edges = deps inherited from ancestors; hidden by default to reduce clutter. */
  const [showInheritedDeps, setShowInheritedDeps] = useState(() => {
    try {
      const s = localStorage.getItem(INHERITED_DEPS_STORAGE_KEY);
      if (s === "1") return true;
      if (s === "0") return false;
    } catch {
      /* ignore */
    }
    return false;
  });

  /** Gantt: band + bar tint for every preceding (transitive effective) dependency of the selection. */
  const [highlightDepChain, setHighlightDepChain] = useState(() => {
    try {
      const s = localStorage.getItem(HIGHLIGHT_DEP_CHAIN_KEY);
      if (s === "0") return false;
    } catch {
      /* ignore */
    }
    return true;
  });

  const [themeMode, setThemeMode] = useState<ThemeMode>(readStoredThemeMode);

  /** Node id whose explicit dependencies are being edited; draft keys are node_key UUIDs. */
  const [depEditId, setDepEditId] = useState<string | null>(null);
  const [depDraftKeys, setDepDraftKeys] = useState<Set<string>>(new Set());

  const splitRef = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncLock = useRef(false);
  const resizing = useRef(false);

  /** Latest draft keys for save — avoids stale closure when applying deps after toggles. */
  const depDraftKeysRef = useRef<Set<string>>(new Set());
  const depEditIdRef = useRef<string | null>(null);
  useEffect(() => {
    depDraftKeysRef.current = depDraftKeys;
  }, [depDraftKeys]);
  useEffect(() => {
    depEditIdRef.current = depEditId;
  }, [depEditId]);
  useEffect(() => {
    focusedEditNodeIdRef.current = focusedEditNodeId;
  }, [focusedEditNodeId]);
  useEffect(() => {
    headerBottomRef.current = headerBottomPx;
  }, [headerBottomPx]);

  useLayoutEffect(() => {
    document.documentElement.setAttribute("data-theme", themeMode);
  }, [themeMode]);

  useEffect(() => {
    try {
      localStorage.setItem(THEME_MODE_STORAGE_KEY, themeMode);
    } catch {
      /* ignore */
    }
  }, [themeMode]);

  useLayoutEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const measure = () => setHeaderBottomPx(el.getBoundingClientRect().bottom);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const refreshGovernanceCompletion = useCallback(async () => {
    try {
      const r = await fetchGovernanceCompletion();
      setGovCompletion({
        vision: r.vision_needs_completion,
        constitution: r.constitution_needs_completion,
      });
    } catch {
      setGovCompletion(null);
    }
  }, []);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [r, repoRes] = await Promise.all([
        fetchRoadmap(),
        fetch("/api/repo").then((x) => x.json()),
      ]);
      setData(r);
      setRepo((repoRes as { repo_root?: string }).repo_root || "");
      setSelectedId((cur) => {
        if (cur && r.ordered_ids.includes(cur)) return cur;
        return r.ordered_ids[0] ?? null;
      });
      try {
        const fp = await fetchRoadmapFingerprint();
        lastFingerprintRef.current = fp;
      } catch {
        /* fingerprint is optional for sync */
      }
      void refreshGovernanceCompletion();
    } catch (e: unknown) {
      setErr(String(e));
    }
  }, [refreshGovernanceCompletion]);

  useEffect(() => {
    /* eslint-disable-next-line react-hooks/set-state-in-effect -- fetch roadmap on mount / when load changes */
    void load();
  }, [load]);

  useEffect(() => {
    try {
      localStorage.setItem(SPLIT_STORAGE_KEY, String(splitPct));
    } catch {
      /* ignore */
    }
  }, [splitPct]);

  useEffect(() => {
    try {
      localStorage.setItem(
        INHERITED_DEPS_STORAGE_KEY,
        showInheritedDeps ? "1" : "0",
      );
    } catch {
      /* ignore */
    }
  }, [showInheritedDeps]);

  useEffect(() => {
    try {
      localStorage.setItem(
        HIGHLIGHT_DEP_CHAIN_KEY,
        highlightDepChain ? "1" : "0",
      );
    } catch {
      /* ignore */
    }
  }, [highlightDepChain]);

  useEffect(() => {
    try {
      localStorage.setItem(REFRESH_STORAGE_KEY, String(refreshSec));
    } catch {
      /* ignore */
    }
  }, [refreshSec]);

  useEffect(() => {
    if (refreshSec <= 0) return;
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const fp = await fetchRoadmapFingerprint();
          const prev = lastFingerprintRef.current;
          if (prev !== null && fp !== prev) {
            await load();
          } else {
            lastFingerprintRef.current = fp;
          }
        } catch {
          /* ignore */
        }
      })();
    }, refreshSec * 1000);
    return () => window.clearInterval(id);
  }, [refreshSec, load]);

  const cancelDepEdit = useCallback(() => {
    setDepEditId(null);
    setDepDraftKeys(new Set());
  }, []);

  const clearDepDraft = useCallback(() => {
    setDepDraftKeys(new Set());
  }, []);

  const applyDepEdit = useCallback(async () => {
    const nid = depEditIdRef.current;
    if (!nid) return;
    const val = [...depDraftKeysRef.current].sort().join(" ");
    try {
      setErr(null);
      await patchNode(nid, [{ key: "dependencies", value: val }]);
      cancelDepEdit();
      await load();
    } catch (e: unknown) {
      setErr(String(e));
    }
  }, [load, cancelDepEdit]);

  const repoFolderLabel = useMemo(
    () => repoRootFolderDisplayName(repo),
    [repo],
  );

  const byId = useMemo(
    () => (data ? nodesByIdFrom(data.nodes) : {}),
    [data],
  );

  const keyToDisplayId = useMemo(() => {
    if (!data?.nodes) return {} as Record<string, string>;
    return Object.fromEntries(
      data.nodes.map((n) => [n.node_key, n.id] as const),
    );
  }, [data?.nodes]);

  const highlightDepRowIds = useMemo(() => {
    if (!highlightDepChain || !selectedId) return null;
    return transitiveEffectivePrereqIds(selectedId, byId, keyToDisplayId);
  }, [highlightDepChain, selectedId, byId, keyToDisplayId]);

  const startDepEdit = useCallback(
    (nodeId: string) => {
      const node = data?.nodes.find((n) => n.id === nodeId);
      if (!node) return;
      setDepEditId(nodeId);
      setDepDraftKeys(new Set(node.dependencies ?? []));
    },
    [data?.nodes],
  );

  const onDepCellActivate = useCallback(
    (nodeId: string) => {
      if (depEditId === nodeId) {
        void applyDepEdit();
        return;
      }
      startDepEdit(nodeId);
    },
    [depEditId, applyDepEdit, startDepEdit],
  );

  /** Toggle whether ``candidateId`` is an explicit dependency of ``depEditId`` (by node_key). */
  const toggleDepCandidate = useCallback(
    (candidateId: string) => {
      if (!depEditId) return;
      const selfKey = byId[depEditId]?.node_key;
      const nk = byId[candidateId]?.node_key;
      if (!selfKey || !nk || nk === selfKey) return;
      setDepDraftKeys((prev) => {
        const next = new Set(prev);
        if (next.has(nk)) next.delete(nk);
        else next.add(nk);
        return next;
      });
    },
    [depEditId, byId],
  );

  const handleEditRectCommit = useCallback((nodeId: string, r: ModalRect) => {
    editRectsRef.current[nodeId] = r;
    setSpawnRects((s) => {
      if (!(nodeId in s)) return s;
      const { [nodeId]: _removed, ...rest } = s;
      return rest;
    });
  }, []);

  const openEditNode = useCallback((id: string) => {
    setEditOpenIds((prev) => {
      const wasNew = !prev.includes(id);
      const next = prev.includes(id)
        ? [...prev.filter((x) => x !== id), id]
        : [...prev, id];
      if (wasNew) {
        const anchorId =
          focusedEditNodeIdRef.current ?? prev[prev.length - 1] ?? null;
        const anchorRect = anchorId
          ? editRectsRef.current[anchorId]
          : undefined;
        const spawn = computeSpawnRect(anchorRect, headerBottomRef.current);
        setSpawnRects((s) => ({ ...s, [id]: spawn }));
      }
      return next;
    });
    setFocusedEditNodeId(id);
  }, []);

  const focusEditNode = useCallback((id: string) => {
    setFocusedEditNodeId(id);
    setEditOpenIds((prev) =>
      prev.includes(id) ? [...prev.filter((x) => x !== id), id] : prev,
    );
  }, []);

  const closeEditNode = useCallback((id: string) => {
    setEditOpenIds((prev) => prev.filter((x) => x !== id));
    delete editRectsRef.current[id];
    setSpawnRects((s) => {
      if (!(id in s)) return s;
      const { [id]: _r, ...rest } = s;
      return rest;
    });
  }, []);

  const toggleTileLayout = useCallback(() => {
    if (!data || editOpenIds.length === 0) return;
    if (!editTileMode) {
      preTileRectsRef.current = { ...editRectsRef.current };
      const sorted = sortOpenIdsByDependencyOrder(
        editOpenIds,
        byId,
        data.ordered_ids,
      );
      setTileRects(computeTileRects(sorted, headerBottomPx));
      setEditTileMode(true);
    } else {
      setResumeAfterUntile({ ...preTileRectsRef.current });
      setEditTileMode(false);
      setTileRects(null);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setResumeAfterUntile(null));
      });
    }
  }, [data, editOpenIds, byId, editTileMode, headerBottomPx]);

  useEffect(() => {
    if (
      focusedEditNodeId != null &&
      !editOpenIds.includes(focusedEditNodeId)
    ) {
      setFocusedEditNodeId(
        editOpenIds.length ? editOpenIds[editOpenIds.length - 1]! : null,
      );
    }
  }, [editOpenIds, focusedEditNodeId]);

  useEffect(() => {
    if (editOpenIds.length === 0 && editTileMode) {
      setEditTileMode(false);
      setTileRects(null);
    }
  }, [editOpenIds.length, editTileMode]);

  useEffect(() => {
    if (!editTileMode || !data || editOpenIds.length === 0) return;
    const sorted = sortOpenIdsByDependencyOrder(
      editOpenIds,
      byId,
      data.ordered_ids,
    );
    setTileRects(computeTileRects(sorted, headerBottomPx));
  }, [editTileMode, data, editOpenIds, byId, headerBottomPx]);

  const indentDisabled =
    !selectedId ||
    (data?.outline_actions != null &&
      selectedId != null &&
      data.outline_actions[selectedId]?.can_indent === false);
  const outdentDisabled =
    !selectedId ||
    (data?.outline_actions != null &&
      selectedId != null &&
      data.outline_actions[selectedId]?.can_outdent === false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editOpenIds.length > 0) return;
      if (settingsOpen || constitutionOpen || visionOpen) return;
      const target = e.target;
      if (target instanceof HTMLElement) {
        if (target.isContentEditable) return;
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
          return;
        }
      }
      if (e.key === "Escape" && depEditId) {
        e.preventDefault();
        cancelDepEdit();
        return;
      }
      if (e.key === "Enter" && depEditId) {
        if (target instanceof HTMLElement) {
          const tag = target.tagName;
          if (tag === "BUTTON" || tag === "TEXTAREA" || tag === "A") {
            return;
          }
        }
        e.preventDefault();
        void applyDepEdit();
        return;
      }
      if (e.key === "Tab" && selectedId && !depEditId) {
        if (target instanceof HTMLElement && target.closest(".app-header")) {
          return;
        }
        e.preventDefault();
        if (e.shiftKey) {
          if (!outdentDisabled) {
            void outdentNode(selectedId).then(load);
          }
        } else if (!indentDisabled) {
          void indentNode(selectedId).then(load);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    editOpenIds.length,
    settingsOpen,
    constitutionOpen,
    visionOpen,
    depEditId,
    selectedId,
    indentDisabled,
    outdentDisabled,
    load,
    cancelDepEdit,
    applyDepEdit,
  ]);

  const syncScroll = (from: "left" | "right") => {
    const L = leftRef.current;
    const R = rightRef.current;
    if (!L || !R || syncLock.current) return;
    syncLock.current = true;
    if (from === "left") R.scrollTop = L.scrollTop;
    else L.scrollTop = R.scrollTop;
    requestAnimationFrame(() => {
      syncLock.current = false;
    });
  };

  const onResizePointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    resizing.current = true;
    const el = splitRef.current;
    if (!el) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);

    const onMove = (ev: PointerEvent) => {
      if (!resizing.current) return;
      const r = el.getBoundingClientRect();
      const x = ev.clientX - r.left;
      const pct = (x / r.width) * 100;
      setSplitPct(Math.min(85, Math.max(15, pct)));
    };
    const onUp = (ev: PointerEvent) => {
      resizing.current = false;
      (e.target as HTMLElement).releasePointerCapture(ev.pointerId);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const addAbove = () => {
    if (!selectedId) return;
    const t = promptNewTaskTitle();
    if (!t) return;
    void addNode(selectedId, "above", t, "task")
      .then(load)
      .catch((e) => setErr(String(e)));
  };

  const addBelow = () => {
    if (!selectedId) return;
    const t = promptNewTaskTitle();
    if (!t) return;
    void addNode(selectedId, "below", t, "task")
      .then(load)
      .catch((e) => setErr(String(e)));
  };

  const onGapInsert = (referenceNodeId: string) => {
    const t = promptNewTaskTitle();
    if (!t) return;
    void addNode(referenceNodeId, "above", t, "task")
      .then(load)
      .catch((e) => setErr(String(e)));
  };

  const onDeleteSelected = () => {
    if (!selectedId) return;
    const label = byId[selectedId]?.id ?? selectedId;
    if (
      !window.confirm(
        `Remove task "${label}" from the roadmap? This cannot be undone.`,
      )
    ) {
      return;
    }
    setErr(null);
    void deleteNode(selectedId)
      .then(() => load())
      .catch((e) => setErr(String(e)));
  };

  return (
    <div className="app-shell">
      <header ref={headerRef} className="app-header">
        <div className="app-header-row1">
          <div className="app-header-row1-left">
            <h1 className="app-title-line">
              <span className="app-title-core">specy-road — PM Gantt</span>
              {repoFolderLabel ? (
                <>
                  <span className="repo-root-sep" aria-hidden="true">
                    {" "}
                    -{" "}
                  </span>
                  <span
                    className="repo-root-folder"
                    title={repo}
                    aria-label={`Repository root: ${repo}`}
                  >
                    {repoFolderLabel}
                  </span>
                </>
              ) : null}
            </h1>
          </div>
          <div className="app-header-row1-actions">
            <GitWorkflowStatusLabel gitWorkflow={data?.git_workflow} />
            {editOpenIds.length > 0 ? (
              <button
                type="button"
                className="app-header-icon-btn app-header-tile-btn"
                aria-pressed={editTileMode}
                title={
                  editTileMode
                    ? "Restore task dialogs to their positions before tiling"
                    : "Tile open task dialogs by dependency, left to right"
                }
                aria-label={
                  editTileMode ? "Untile task dialogs" : "Tile task dialogs"
                }
                onClick={() => toggleTileLayout()}
              >
                Tile
              </button>
            ) : null}
            <button
              type="button"
              className="app-header-icon-btn"
              aria-label="Settings"
              title="Settings"
              onClick={() => setSettingsOpen(true)}
            >
              <IconGear />
            </button>
          </div>
        </div>
        <div className="app-header-row2">
          <div className="app-header-row2-inner">
            <div className="app-header-toolbar">
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={!selectedId}
                title="Edit selected task"
                aria-label="Edit selected task"
                onClick={() => {
                  if (!selectedId) return;
                  openEditNode(selectedId);
                }}
              >
                <IconPencil />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={indentDisabled}
                title="Indent"
                aria-label="Indent"
                onClick={() =>
                  selectedId && void indentNode(selectedId).then(load)
                }
              >
                <IconIndent />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={outdentDisabled}
                title="Outdent"
                aria-label="Outdent"
                onClick={() =>
                  selectedId && void outdentNode(selectedId).then(load)
                }
              >
                <IconOutdent />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={!selectedId}
                title="Add task above selection"
                aria-label="Add task above selection"
                onClick={addAbove}
              >
                <IconRowAbove />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={!selectedId}
                title="Add task below selection"
                aria-label="Add task below selection"
                onClick={addBelow}
              >
                <IconRowBelow />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn toolbar-icon-btn-danger"
                disabled={!selectedId}
                title="Delete selected row"
                aria-label="Delete selected row"
                onClick={onDeleteSelected}
              >
                <IconTrash />
              </button>
            </div>
            <div className="app-header-docs-row">
              <div className="app-header-doc-slot">
                <div
                  className={
                    govCompletion?.vision
                      ? "app-header-doc-tooltip app-header-doc-tooltip--incomplete"
                      : "app-header-doc-tooltip"
                  }
                >
                  <button
                    type="button"
                    className={
                      govCompletion?.vision
                        ? "app-header-doc-btn app-header-doc-btn--incomplete"
                        : "app-header-doc-btn"
                    }
                    aria-describedby={
                      govCompletion?.vision ? "gov-tip-vision" : undefined
                    }
                    onClick={() => setVisionOpen(true)}
                  >
                    Vision
                  </button>
                  {govCompletion?.vision ? (
                    <div
                      id="gov-tip-vision"
                      role="tooltip"
                      className="app-header-doc-tip"
                    >
                      Needs completion — replace the starter text in{" "}
                      <code>vision.md</code> with your product vision.
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="app-header-doc-slot">
                <div
                  className={
                    govCompletion?.constitution
                      ? "app-header-doc-tooltip app-header-doc-tooltip--incomplete"
                      : "app-header-doc-tooltip"
                  }
                >
                  <button
                    type="button"
                    className={
                      govCompletion?.constitution
                        ? "app-header-doc-btn app-header-doc-btn--incomplete"
                        : "app-header-doc-btn"
                    }
                    aria-describedby={
                      govCompletion?.constitution
                        ? "gov-tip-constitution"
                        : undefined
                    }
                    onClick={() => setConstitutionOpen(true)}
                  >
                    Constitution
                  </button>
                  {govCompletion?.constitution ? (
                    <div
                      id="gov-tip-constitution"
                      role="tooltip"
                      className="app-header-doc-tip"
                    >
                      Needs completion — customize{" "}
                      <code>purpose.md</code> and <code>principles.md</code>{" "}
                      beyond the scaffold templates.
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="app-header-doc-slot">
                <button
                  type="button"
                  className="app-header-doc-btn"
                  onClick={() => setSharedDocsOpen(true)}
                >
                  Shared docs
                </button>
              </div>
              <div className="app-header-doc-slot">
                <button
                  type="button"
                  className="app-header-doc-btn"
                  onClick={() => setWorkNotesOpen(true)}
                >
                  Session notes
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>
      {err ? (
        <p style={{ padding: "0 0.75rem", color: "crimson" }}>{err}</p>
      ) : null}
      {data ? (
        <div className="split" ref={splitRef}>
          <div
            className="outline-wrap"
            ref={leftRef}
            style={{ flex: `0 0 ${splitPct}%`, width: `${splitPct}%` }}
            onScroll={() => syncScroll("left")}
          >
            <OutlineTable
              orderedIds={data.ordered_ids}
              nodesById={byId}
              rowDepths={data.row_depths}
              selectedId={selectedId}
              prHints={data.pr_hints}
              gitEnrichment={data.git_enrichment}
              dependencyInheritance={data.dependency_inheritance}
              registryByNode={data.registry_by_node}
              gitBranchCurrent={
                data.git_workflow?.resolved?.git_branch_current ?? null
              }
              depEditId={depEditId}
              depDraftKeys={depDraftKeys}
              onToggleDepCandidate={toggleDepCandidate}
              onDepCellActivate={onDepCellActivate}
              onApplyDepEdit={() => void applyDepEdit()}
              onCancelDepEdit={cancelDepEdit}
              onClearDepDraft={clearDepDraft}
              onSelect={setSelectedId}
              onDoubleClick={(id) => {
                setSelectedId(id);
                openEditNode(id);
              }}
              onReordered={load}
              onGapInsert={onGapInsert}
            />
          </div>
          <div
            className="split-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize feature list and chart"
            onPointerDown={onResizePointerDown}
          />
          <div
            className="gantt-wrap"
            ref={rightRef}
            onScroll={() => syncScroll("right")}
          >
            <GanttPane
              orderedIds={data.ordered_ids}
              nodesById={byId}
              depths={data.dependency_depths}
              spans={data.dependency_spans}
              edges={data.edges}
              showInheritedEdges={showInheritedDeps}
              selectedId={selectedId}
              highlightRowIds={highlightDepRowIds}
              onSelect={setSelectedId}
              onChartBackgroundMouseDown={
                depEditId ? () => void applyDepEdit() : undefined
              }
            />
          </div>
        </div>
      ) : (
        <p style={{ padding: "1rem" }}>Loading roadmap…</p>
      )}
      {data
        ? editOpenIds.map((nodeId, index) => {
            const emNode = byId[nodeId];
            if (!emNode) return null;
            const passThrough = editOpenIds.length > 1;
            return (
              <EditModal
                key={nodeId}
                node={emNode}
                allNodes={data.nodes}
                modalStorageKey={nodeId}
                stackZIndex={50 + index}
                backdropPassThrough={passThrough}
                closeOnEscape={index === editOpenIds.length - 1}
                headerMinTop={headerBottomPx}
                spawnInitialRect={spawnRects[nodeId]}
                editTileMode={editTileMode}
                tileRect={tileRects?.[nodeId] ?? null}
                resumeFreeRect={resumeAfterUntile?.[nodeId] ?? null}
                titleBarActive={focusedEditNodeId === nodeId}
                onActivate={() => focusEditNode(nodeId)}
                onRectCommit={(r) => handleEditRectCommit(nodeId, r)}
                dependencyInheritance={data.dependency_inheritance?.[nodeId]}
                registryByNode={data.registry_by_node}
                gitEnrichment={data.git_enrichment}
                prHints={data.pr_hints}
                onClose={() => closeEditNode(nodeId)}
                onOpenNode={openEditNode}
                onPersisted={() => void load()}
              />
            );
          })
        : null}
      <ConstitutionDrawer
        open={constitutionOpen}
        onClose={() => {
          setConstitutionOpen(false);
          void refreshGovernanceCompletion();
        }}
      />
      <VisionDrawer
        open={visionOpen}
        onClose={() => {
          setVisionOpen(false);
          void refreshGovernanceCompletion();
        }}
      />
      <SharedDocsDrawer
        open={sharedDocsOpen}
        onClose={() => setSharedDocsOpen(false)}
      />
      <WorkNotesDrawer
        open={workNotesOpen}
        onClose={() => setWorkNotesOpen(false)}
      />
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        themeMode={themeMode}
        onThemeModeChange={setThemeMode}
        highlightDepChain={highlightDepChain}
        onHighlightDepChainChange={setHighlightDepChain}
        showInheritedDeps={showInheritedDeps}
        onShowInheritedDepsChange={setShowInheritedDeps}
        refreshSec={refreshSec}
        onRefreshSecChange={setRefreshSec}
      />
    </div>
  );
}
