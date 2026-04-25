import {
  Suspense,
  lazy,
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
  fetchPublishStatus,
  fetchRoadmap,
  fetchRoadmapFingerprint,
  indentNode,
  outdentNode,
  patchNode,
  PmGuiConcurrencyError,
  postPublish,
  setPmGuiFingerprintGetter,
} from "./api";
import {
  computeSpawnRect,
  computeTileRects,
  sortOpenIdsByDependencyOrder,
} from "./editModalLayout";
import type { ModalRect } from "./modalRect";
import type {
  PublishStatusPayload,
  RoadmapNode,
  RoadmapResponse,
} from "./types";
import {
  pmOutlineDisplayStatus,
  pmPlanningTitleReadOnlyFromRow,
} from "./pmDisplayStatus";
import {
  buildDisplayStatusWithPhaseRollup,
  computeEffectiveDisplayForAllNodes,
} from "./parentStatusRollup";
import { rowMatchesRegisteredBranch } from "./rowMatchesRegisteredBranch";
import { transitiveEffectivePrereqIds } from "./depChain";
import { minDependencyDepth } from "./ganttDepthOffset";
import { GitWorkflowStatusLabel } from "./components/GitWorkflowStatusLabel";
import { GanttPane } from "./components/GanttPane";
import { OutlineTable } from "./components/OutlineTable";
import { PublishRoadmapModal } from "./components/PublishRoadmapModal";
import type { ThemeMode } from "./components/SettingsDrawer";
import {
  IconGear,
  IconIndent,
  IconOutdent,
  IconPencil,
  IconPublish,
  IconRowAbove,
  IconRowBelow,
  IconTrash,
} from "./toolbarIcons";
import {
  BROWSER_PREF_KEYS,
  readBrowserPref,
  readLegacyBrowserPref,
  writeBrowserPref,
} from "./repoBrowserPrefs";
import { PmGuiHandlersProvider } from "./pmGuiContext";
import { useRoadmapActionQueue } from "./roadmapSync";
import { runMutationWithAutoffRetry } from "./runMutationWithAutoffRetry";
import { PendingMutationsProvider } from "./pendingMutations";
import { usePendingMutationsState } from "./usePendingMutationsState";
import { isRowLocked } from "./pendingMutationsContext";
import {
  nextPendingToken,
  type PendingKind,
} from "./pendingMutationsCore";
import {
  applyOptimistic,
  buildAddPlaceholder,
  isPendingPlaceholderId,
  type OptimisticOp,
} from "./optimisticOutline";

const EditModal = lazy(() =>
  import("./components/EditModal").then((m) => ({ default: m.EditModal })),
);
const ConstitutionDrawer = lazy(() =>
  import("./components/ConstitutionDrawer").then((m) => ({
    default: m.ConstitutionDrawer,
  })),
);
const SettingsDrawer = lazy(() =>
  import("./components/SettingsDrawer").then((m) => ({
    default: m.SettingsDrawer,
  })),
);
const SharedDocsDrawer = lazy(() =>
  import("./components/SharedDocsDrawer").then((m) => ({
    default: m.SharedDocsDrawer,
  })),
);
const SharedDocEditModal = lazy(() =>
  import("./components/SharedDocEditModal").then((m) => ({
    default: m.SharedDocEditModal,
  })),
);
const VisionDrawer = lazy(() =>
  import("./components/VisionDrawer").then((m) => ({ default: m.VisionDrawer })),
);
const WorkNotesDrawer = lazy(() =>
  import("./components/WorkNotesDrawer").then((m) => ({
    default: m.WorkNotesDrawer,
  })),
);

function readLegacyThemeMode(): ThemeMode {
  const s = readLegacyBrowserPref(BROWSER_PREF_KEYS.themeMode);
  if (s === "light" || s === "dark" || s === "system") return s;
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
  /** Stable id for this GUI process (matches gui-settings.json project keys); drives namespaced localStorage. */
  const [repoId, setRepoId] = useState<string | null>(null);
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
  const preTileRectsRef = useRef<Record<string, ModalRect>>({});
  const headerRef = useRef<HTMLElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [constitutionOpen, setConstitutionOpen] = useState(false);
  const [visionOpen, setVisionOpen] = useState(false);
  const [sharedDocsOpen, setSharedDocsOpen] = useState(false);
  /** Repo-relative `shared/...` path for the TipTap editor modal, or null when closed. */
  const [sharedDocEditPath, setSharedDocEditPath] = useState<string | null>(
    null,
  );
  const [workNotesOpen, setWorkNotesOpen] = useState(false);
  /** When set, Vision / Constitution need human content beyond blank or starter templates. */
  const [govCompletion, setGovCompletion] = useState<{
    vision: boolean;
    constitution: boolean;
  } | null>(null);

  const [publishOpen, setPublishOpen] = useState(false);
  const [publishStatus, setPublishStatus] = useState<PublishStatusPayload | null>(
    null,
  );

  const [refreshSec, setRefreshSec] = useState(() => {
    const s = readLegacyBrowserPref(BROWSER_PREF_KEYS.refreshSec);
    if (s !== null) {
      const n = parseInt(s, 10);
      if (!Number.isNaN(n) && n >= 0 && n <= 120) return n;
    }
    return 5;
  });

  // Fingerprint is a string end-to-end (server emits base-10 strings to
  // dodge JS Number precision loss for values > 2**53).
  const lastFingerprintRef = useRef<string | null>(null);

  const [splitPct, setSplitPct] = useState(() => {
    const s = readLegacyBrowserPref(BROWSER_PREF_KEYS.splitPct);
    if (s) {
      const n = Number(s);
      if (!Number.isNaN(n) && n >= 15 && n <= 85) return n;
    }
    return 42;
  });

  /** Dashed edges = deps inherited from ancestors; hidden by default to reduce clutter. */
  const [showInheritedDeps, setShowInheritedDeps] = useState(() => {
    const s = readLegacyBrowserPref(BROWSER_PREF_KEYS.showInheritedDeps);
    if (s === "1") return true;
    if (s === "0") return false;
    return false;
  });

  /** Gantt: band + bar tint for every preceding (transitive effective) dependency of the selection. */
  const [highlightDepChain, setHighlightDepChain] = useState(() => {
    const s = readLegacyBrowserPref(BROWSER_PREF_KEYS.highlightDepChain);
    if (s === "0") return false;
    return true;
  });

  /** When true, omit rows whose effective rolled-up status is Complete (see computeEffectiveDisplayForAllNodes). */
  const [hideCompleteActive, setHideCompleteActive] = useState(false);

  const [themeMode, setThemeMode] = useState<ThemeMode>(readLegacyThemeMode);

  /** After `/api/repo` returns, apply namespaced (or migrated) browser prefs for this project. */
  /* eslint-disable @eslint-react/set-state-in-effect -- sync localStorage prefs into React state when repo id resolves */
  useLayoutEffect(() => {
    if (!repoId) return;
    const tm = readBrowserPref(BROWSER_PREF_KEYS.themeMode, repoId);
    if (tm === "light" || tm === "dark" || tm === "system") {
      setThemeMode(tm);
    }
    const rs = readBrowserPref(BROWSER_PREF_KEYS.refreshSec, repoId);
    if (rs !== null) {
      const n = parseInt(rs, 10);
      if (!Number.isNaN(n) && n >= 0 && n <= 120) setRefreshSec(n);
    }
    const sp = readBrowserPref(BROWSER_PREF_KEYS.splitPct, repoId);
    if (sp) {
      const n = Number(sp);
      if (!Number.isNaN(n) && n >= 15 && n <= 85) setSplitPct(n);
    }
    const inh = readBrowserPref(BROWSER_PREF_KEYS.showInheritedDeps, repoId);
    setShowInheritedDeps(inh === "1");
    const hi = readBrowserPref(BROWSER_PREF_KEYS.highlightDepChain, repoId);
    setHighlightDepChain(hi !== "0");
  }, [repoId]);
  /* eslint-enable @eslint-react/set-state-in-effect */

  /** Node id whose explicit dependencies are being edited; draft keys are node_key UUIDs. */
  const [depEditId, setDepEditId] = useState<string | null>(null);
  const [depDraftKeys, setDepDraftKeys] = useState<Set<string>>(new Set());

  const splitRef = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  /** Matches outline thead + first gap row height for Gantt grid alignment. */
  const [ganttStackHeaderPx, setGanttStackHeaderPx] = useState(52);
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
  useLayoutEffect(() => {
    document.documentElement.setAttribute("data-theme", themeMode);
  }, [themeMode]);

  useEffect(() => {
    writeBrowserPref(BROWSER_PREF_KEYS.themeMode, repoId, themeMode);
  }, [themeMode, repoId]);

  const measureGanttStackHeader = useCallback(() => {
    const wrap = leftRef.current;
    if (!wrap) return;
    const thead = wrap.querySelector("thead");
    const gapTr = wrap.querySelector("tbody tr.outline-gap-tr");
    const th = thead?.getBoundingClientRect().height ?? 0;
    const gh = gapTr?.getBoundingClientRect().height;
    const gapPx = typeof gh === "number" && gh > 0 ? gh : 8;
    const sum = th + gapPx;
    if (sum > 0) setGanttStackHeaderPx(Math.round(sum * 10) / 10);
  }, []);

  useLayoutEffect(() => {
    if (!data) return;
    const wrap = leftRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => {
      measureGanttStackHeader();
    });
    ro.observe(wrap);
    const thead = wrap.querySelector("thead");
    const tbody = wrap.querySelector("tbody");
    if (thead) ro.observe(thead);
    if (tbody) ro.observe(tbody);
    const raf = requestAnimationFrame(() => {
      measureGanttStackHeader();
    });
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [data, measureGanttStackHeader]);

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

  const refreshPublishStatus = useCallback(async () => {
    try {
      setPublishStatus(await fetchPublishStatus());
    } catch {
      setPublishStatus(null);
    }
  }, []);

  const loadSnapshot = useCallback(async () => {
    setErr(null);
    try {
      const [r, repoRes] = await Promise.all([
        fetchRoadmap(),
        fetch("/api/repo").then((x) => x.json()),
      ]);
      setData(r);
      lastFingerprintRef.current = r.fingerprint;
      const rr = repoRes as { repo_root?: string; repo_id?: string };
      setRepo(rr.repo_root || "");
      setRepoId(typeof rr.repo_id === "string" ? rr.repo_id : null);
      setSelectedId((cur) => {
        if (cur && r.ordered_ids.includes(cur)) return cur;
        return r.ordered_ids[0] ?? null;
      });
      try {
        const fp = await fetchRoadmapFingerprint();
        lastFingerprintRef.current = fp;
      } catch {
        /* polling endpoint optional when roadmap payload has fingerprint */
      }
      void refreshGovernanceCompletion();
      void refreshPublishStatus();
    } catch (e: unknown) {
      setErr(String(e));
    }
  }, [refreshGovernanceCompletion, refreshPublishStatus]);

  const handlePublishRoadmap = useCallback(async (message: string) => {
    try {
      await postPublish(message);
    } catch (e: unknown) {
      if (e instanceof PmGuiConcurrencyError) {
        await loadSnapshot();
      }
      throw e;
    }
    await loadSnapshot();
  }, [loadSnapshot]);

  const {
    busy: roadmapBusy,
    busyDepth,
    busyLabel,
    queueOverloaded,
    runRoadmapAction,
  } = useRoadmapActionQueue();

  /**
   * One-shot informational suffix shown after ``busyLabel`` when the
   * user attempts an action that's blocked because the row's previous
   * mutation hasn't settled yet, or because the queue is overloaded.
   * Cleared automatically when the queue empties or after 2 seconds —
   * whichever comes first.
   */
  const [lockReason, setLockReason] = useState<string | null>(null);
  const lockReasonTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const triggerWaitMessage = useCallback((reason: string) => {
    setLockReason(reason);
    if (lockReasonTimerRef.current != null) {
      clearTimeout(lockReasonTimerRef.current);
    }
    lockReasonTimerRef.current = setTimeout(() => {
      setLockReason(null);
      lockReasonTimerRef.current = null;
    }, 2000);
  }, []);
  // Clear the wait-message immediately the moment the queue empties,
  // even if the 2 s timer hasn't fired yet — the warning is stale.
  useEffect(() => {
    if (!roadmapBusy && lockReason != null) setLockReason(null);
  }, [roadmapBusy, lockReason]);

  // Pending-row state machine (drives the blue pulse on rows whose
  // mutations are in flight). See pendingMutations.tsx.
  const pendingMutations = usePendingMutationsState();

  /** True if ``id`` is mid-mutation (placeholder ids count too). */
  const isLockedTarget = useCallback(
    (id: string | null | undefined): boolean => {
      if (id == null) return false;
      if (isPendingPlaceholderId(id)) return true;
      return isRowLocked(pendingMutations, id);
    },
    [pendingMutations],
  );

  /** Wait-message text appended after the busy label when blocked. */
  const WAIT_MESSAGE = "saves pending - please wait.";

  /**
   * Run ``fn`` only if neither the queue is overloaded nor ``id`` is
   * mid-mutation. Otherwise fire the inline wait message and bail.
   * Used in click handlers for buttons that target a specific row.
   */
  const guardRowAction = useCallback(
    (id: string | null | undefined, fn: () => void): void => {
      if (queueOverloaded) {
        triggerWaitMessage(WAIT_MESSAGE);
        return;
      }
      if (isLockedTarget(id)) {
        triggerWaitMessage(WAIT_MESSAGE);
        return;
      }
      fn();
    },
    [queueOverloaded, isLockedTarget, triggerWaitMessage],
  );

  // Optimistic-op registry. The render path applies these on top of
  // the server-truth `data` so OutlineTable / GanttPane see the
  // post-mutation tree immediately, before the server's ack arrives.
  // Refs (vs state) so writes are synchronous; ``optimisticTick``
  // forces a re-render after every mutation.
  const optimisticOpsRef = useRef<Map<string, OptimisticOp>>(new Map());
  const [optimisticTick, setOptimisticTick] = useState(0);
  const bumpOptimistic = useCallback(
    () => setOptimisticTick((t) => (t + 1) | 0),
    [],
  );

  const performRoadmapMutation = useCallback(
    (label: string, mutation: () => Promise<void>) =>
      runRoadmapAction(label, async () => {
        const outcome = await runMutationWithAutoffRetry(mutation, loadSnapshot);
        if (outcome === "conflict") {
          setErr(
            "Roadmap or workspace changed elsewhere; the view was refreshed. Retry if needed.",
          );
          return;
        }
        await loadSnapshot();
      }),
    [runRoadmapAction, loadSnapshot],
  );

  /**
   * Like {@link performRoadmapMutation} but also registers an
   * optimistic-UI overlay so the affected row(s) snap to their new
   * position immediately and pulse blue while the network call
   * completes. On success the pulse fades out; on failure the row
   * reverts and a brief red flash plays.
   *
   * Pass ``op = null`` for mutations that don't change tree shape
   * (e.g. title / status edits) — only the pending-pulse hint runs.
   */
  /**
   * Server-truth + optimistic overlay merged into the snapshot the UI
   * actually renders. ``data`` remains the canonical post-loadSnapshot
   * value (writes ``lastFingerprintRef`` etc.); everything in the
   * render path reads from ``displayData`` instead.
   */
  const displayData = useMemo(() => {
    if (!data) return data;
    if (optimisticOpsRef.current.size === 0) return data;
    void optimisticTick; // dependency: re-run when ops change
    return applyOptimistic(data, [...optimisticOpsRef.current.values()]);
  }, [data, optimisticTick]);

  const performOptimisticMutation = useCallback(
    (
      label: string,
      op: OptimisticOp | null,
      ids: string[],
      kind: PendingKind,
      mutation: () => Promise<void>,
    ) => {
      const token = nextPendingToken();
      pendingMutations.begin(token, ids, kind);
      if (op) {
        optimisticOpsRef.current.set(token, op);
        bumpOptimistic();
      }
      const cleanup = (success: boolean) => {
        if (optimisticOpsRef.current.delete(token)) bumpOptimistic();
        if (success) pendingMutations.end(token);
        else pendingMutations.fail(token);
      };
      return runRoadmapAction(label, async () => {
        try {
          const outcome = await runMutationWithAutoffRetry(
            mutation,
            loadSnapshot,
          );
          if (outcome === "conflict") {
            setErr(
              "Roadmap or workspace changed elsewhere; the view was refreshed. Retry if needed.",
            );
            cleanup(false);
            return;
          }
          await loadSnapshot();
          cleanup(true);
        } catch (e) {
          cleanup(false);
          throw e;
        }
      });
    },
    [runRoadmapAction, loadSnapshot, pendingMutations, bumpOptimistic],
  );

  const pmGuiHandlers = useMemo(
    () => ({ onConcurrencyConflict: loadSnapshot }),
    [loadSnapshot],
  );

  /** Convenience wrappers used by indent/outdent buttons + keyboard. */
  const triggerIndent = useCallback(
    (nodeId: string) =>
      performOptimisticMutation(
        "Updating outline…",
        { kind: "indent", nodeId },
        [nodeId],
        "indent",
        async () => {
          await indentNode(nodeId);
        },
      ).catch((e: unknown) => setErr(String(e))),
    [performOptimisticMutation],
  );
  const triggerOutdent = useCallback(
    (nodeId: string) =>
      performOptimisticMutation(
        "Updating outline…",
        { kind: "outdent", nodeId },
        [nodeId],
        "outdent",
        async () => {
          await outdentNode(nodeId);
        },
      ).catch((e: unknown) => setErr(String(e))),
    [performOptimisticMutation],
  );

  useEffect(() => {
    setPmGuiFingerprintGetter(() => lastFingerprintRef.current);
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void refreshPublishStatus();
    }, 12000);
    return () => window.clearInterval(id);
  }, [refreshPublishStatus]);

  useEffect(() => {
    writeBrowserPref(
      BROWSER_PREF_KEYS.splitPct,
      repoId,
      String(splitPct),
    );
  }, [splitPct, repoId]);

  useEffect(() => {
    writeBrowserPref(
      BROWSER_PREF_KEYS.showInheritedDeps,
      repoId,
      showInheritedDeps ? "1" : "0",
    );
  }, [showInheritedDeps, repoId]);

  useEffect(() => {
    writeBrowserPref(
      BROWSER_PREF_KEYS.highlightDepChain,
      repoId,
      highlightDepChain ? "1" : "0",
    );
  }, [highlightDepChain, repoId]);

  useEffect(() => {
    writeBrowserPref(
      BROWSER_PREF_KEYS.refreshSec,
      repoId,
      String(refreshSec),
    );
  }, [refreshSec, repoId]);

  useEffect(() => {
    if (refreshSec <= 0) return;
    const id = window.setInterval(() => {
      void (async () => {
        try {
          const fp = await fetchRoadmapFingerprint();
          const prev = lastFingerprintRef.current;
          if (prev !== null && fp !== prev) {
            await runRoadmapAction("Checking for updates…", () => loadSnapshot());
          } else {
            lastFingerprintRef.current = fp;
          }
        } catch {
          /* ignore */
        }
      })();
    }, refreshSec * 1000);
    return () => window.clearInterval(id);
  }, [refreshSec, runRoadmapAction, loadSnapshot]);

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
    const draft = [...depDraftKeysRef.current];
    const val = [...draft].sort().join(" ");
    try {
      setErr(null);
      await performOptimisticMutation(
        "Saving dependencies…",
        { kind: "dep", nodeId: nid, explicitNodeKeys: draft },
        [nid],
        "dep",
        async () => {
          await patchNode(nid, [{ key: "dependencies", value: val }]);
          cancelDepEdit();
        },
      );
    } catch (e: unknown) {
      setErr(String(e));
    }
  }, [performOptimisticMutation, cancelDepEdit]);

  const repoFolderLabel = useMemo(
    () => repoRootFolderDisplayName(repo),
    [repo],
  );

  const byId = useMemo(
    () => (displayData ? nodesByIdFrom(displayData.nodes) : {}),
    [displayData],
  );

  /** Gates must be under vision/phase; root-level rows have no parent_id. */
  const gateInsertDisabled = useMemo(() => {
    if (!selectedId) return true;
    const p = byId[selectedId]?.parent_id;
    return p == null || p === "";
  }, [selectedId, byId]);

  const displayStatusById = useMemo(() => {
    if (!displayData?.ordered_ids) return {} as Record<string, string>;
    return buildDisplayStatusWithPhaseRollup(
      displayData.ordered_ids,
      byId,
      displayData.registry_by_node,
    );
  }, [displayData, byId]);

  /** Full bottom-up effective status (for hiding complete subtrees). */
  const effectiveDisplayById = useMemo(() => {
    if (!displayData?.ordered_ids) return {} as Record<string, string>;
    return computeEffectiveDisplayForAllNodes(
      displayData.ordered_ids,
      byId,
      displayData.registry_by_node,
    );
  }, [displayData, byId]);

  const visibleOrderedIds = useMemo(() => {
    if (!displayData?.ordered_ids) return [] as string[];
    if (!hideCompleteActive) return displayData.ordered_ids;
    return displayData.ordered_ids.filter(
      (id) =>
        (effectiveDisplayById[id] ?? "").trim().toLowerCase() !== "complete",
    );
  }, [displayData?.ordered_ids, hideCompleteActive, effectiveDisplayById]);

  const visibleRowDepths = useMemo(() => {
    if (!displayData?.ordered_ids || !displayData.row_depths) return [] as number[];
    if (!hideCompleteActive) return displayData.row_depths;
    const out: number[] = [];
    for (let i = 0; i < displayData.ordered_ids.length; i++) {
      const id = displayData.ordered_ids[i];
      if (
        (effectiveDisplayById[id] ?? "").trim().toLowerCase() !== "complete"
      ) {
        out.push(displayData.row_depths[i] ?? 0);
      }
    }
    return out;
  }, [displayData?.ordered_ids, displayData?.row_depths, hideCompleteActive, effectiveDisplayById]);

  /** Crop leading empty chart columns when hiding complete (min step among visible rows). */
  const ganttDepthOffset = useMemo(() => {
    if (!hideCompleteActive || !displayData?.dependency_depths) return 0;
    return minDependencyDepth(visibleOrderedIds, displayData.dependency_depths);
  }, [hideCompleteActive, displayData?.dependency_depths, visibleOrderedIds]);

  /** When hiding complete rows, move selection off hidden ids and exit dependency edit if its row is hidden. */
  /* eslint-disable @eslint-react/set-state-in-effect -- derive selection / dep-edit from filtered outline */
  useEffect(() => {
    if (!hideCompleteActive || !displayData?.ordered_ids?.length) return;
    const hidden = (id: string) =>
      (effectiveDisplayById[id] ?? "").trim().toLowerCase() === "complete";
    setSelectedId((cur) => {
      if (cur && !hidden(cur)) return cur;
      return displayData.ordered_ids.find((id) => !hidden(id)) ?? null;
    });
  }, [hideCompleteActive, displayData?.ordered_ids, effectiveDisplayById]);

  useEffect(() => {
    if (!hideCompleteActive || !depEditId) return;
    if ((effectiveDisplayById[depEditId] ?? "").trim().toLowerCase() === "complete") {
      cancelDepEdit();
    }
  }, [hideCompleteActive, depEditId, effectiveDisplayById, cancelDepEdit]);
  /* eslint-enable @eslint-react/set-state-in-effect */

  const outlineStatusById = useMemo(() => {
    if (!displayData?.ordered_ids) return {} as Record<string, string>;
    const reg = displayData.registry_by_node ?? {};
    const enr = displayData.git_enrichment ?? {};
    const out: Record<string, string> = {};
    for (const id of displayData.ordered_ids) {
      out[id] = pmOutlineDisplayStatus(
        byId[id],
        reg[id],
        enr[id],
        displayStatusById[id],
      );
    }
    return out;
  }, [displayData, byId, displayStatusById]);

  const gitCheckoutById = useMemo(() => {
    if (!displayData?.ordered_ids) return {} as Record<string, boolean>;
    const reg = displayData.registry_by_node ?? {};
    const cur = displayData.git_workflow?.resolved?.git_branch_current ?? null;
    const out: Record<string, boolean> = {};
    for (const id of displayData.ordered_ids) {
      out[id] = rowMatchesRegisteredBranch(id, reg, cur);
    }
    return out;
  }, [data]);

  const selectedPlanningReadOnly = useMemo(() => {
    if (!selectedId) return false;
    const persisted =
      (byId[selectedId]?.status as string)?.trim() || "Not Started";
    const base = displayStatusById[selectedId] ?? persisted;
    const outline = outlineStatusById[selectedId] ?? base;
    return pmPlanningTitleReadOnlyFromRow(
      Boolean(gitCheckoutById[selectedId]),
      base,
      outline,
    );
  }, [
    selectedId,
    byId,
    displayStatusById,
    outlineStatusById,
    gitCheckoutById,
  ]);

  const keyToDisplayId = useMemo(() => {
    if (!displayData?.nodes) return {} as Record<string, string>;
    return Object.fromEntries(
      displayData.nodes.map((n) => [n.node_key, n.id] as const),
    );
  }, [data]);

  const highlightDepRowIds = useMemo(() => {
    if (!highlightDepChain || !selectedId) return null;
    return transitiveEffectivePrereqIds(selectedId, byId, keyToDisplayId);
  }, [highlightDepChain, selectedId, byId, keyToDisplayId]);

  const startDepEdit = useCallback(
    (nodeId: string) => {
      const node = displayData?.nodes.find((n) => n.id === nodeId);
      if (!node) return;
      setDepEditId(nodeId);
      setDepDraftKeys(new Set(node.dependencies ?? []));
    },
    [displayData?.nodes],
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
      const next = { ...s };
      delete next[nodeId];
      return next;
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
        const spawn = computeSpawnRect(anchorRect, 0);
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
      const next = { ...s };
      delete next[id];
      return next;
    });
  }, []);

  const toggleTileLayout = useCallback(() => {
    if (!displayData || editOpenIds.length === 0) return;
    if (!editTileMode) {
      preTileRectsRef.current = { ...editRectsRef.current };
      const sorted = sortOpenIdsByDependencyOrder(
        editOpenIds,
        byId,
        displayData.ordered_ids,
      );
      setTileRects(computeTileRects(sorted));
      setEditTileMode(true);
    } else {
      setResumeAfterUntile({ ...preTileRectsRef.current });
      setEditTileMode(false);
      setTileRects(null);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setResumeAfterUntile(null));
      });
    }
  }, [displayData, editOpenIds, byId, editTileMode]);

  /* eslint-disable @eslint-react/set-state-in-effect -- sync focused dialog when open stack changes */
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
  /* eslint-enable @eslint-react/set-state-in-effect */

  /* eslint-disable @eslint-react/set-state-in-effect -- exit tile mode when last dialog closes */
  useEffect(() => {
    if (editOpenIds.length === 0 && editTileMode) {
      setEditTileMode(false);
      setTileRects(null);
    }
  }, [editOpenIds.length, editTileMode]);
  /* eslint-enable @eslint-react/set-state-in-effect */

  /* eslint-disable @eslint-react/set-state-in-effect -- recompute tiled window positions from graph order */
  useEffect(() => {
    if (!editTileMode || !displayData || editOpenIds.length === 0) return;
    const sorted = sortOpenIdsByDependencyOrder(
      editOpenIds,
      byId,
      displayData.ordered_ids,
    );
    setTileRects(computeTileRects(sorted));
  }, [editTileMode, displayData, editOpenIds, byId]);
  /* eslint-enable @eslint-react/set-state-in-effect */

  const indentDisabled =
    !selectedId ||
    (displayData?.outline_actions != null &&
      selectedId != null &&
      displayData.outline_actions[selectedId]?.can_indent === false);
  const outdentDisabled =
    !selectedId ||
    (displayData?.outline_actions != null &&
      selectedId != null &&
      displayData.outline_actions[selectedId]?.can_outdent === false);

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
          if (!outdentDisabled) void triggerOutdent(selectedId);
        } else if (!indentDisabled) {
          void triggerIndent(selectedId);
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
    triggerIndent,
    triggerOutdent,
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

  /** Optimistic add-task: insert a placeholder row immediately, swap to
   *  real id after the server returns and ``loadSnapshot`` re-fetches. */
  const triggerAddNode = useCallback(
    (
      referenceNodeId: string,
      position: "above" | "below",
      title: string,
      type: string,
      label: string,
    ) => {
      const refNode = byId[referenceNodeId];
      const parentId = refNode?.parent_id ?? null;
      const token = nextPendingToken();
      const placeholder = buildAddPlaceholder({
        token,
        title,
        type,
        parentId,
      });
      void performOptimisticMutation(
        label,
        {
          kind: "add",
          placeholder,
          referenceNodeId,
          position,
        },
        [placeholder.id],
        "add",
        async () => {
          await addNode(referenceNodeId, position, title, type);
        },
      ).catch((e) => setErr(String(e)));
    },
    [byId, performOptimisticMutation],
  );

  const addAbove = () => {
    if (!selectedId) return;
    const t = promptNewTaskTitle();
    if (!t) return;
    triggerAddNode(selectedId, "above", t, "task", "Adding task…");
  };

  const addBelow = () => {
    if (!selectedId) return;
    const t = promptNewTaskTitle();
    if (!t) return;
    triggerAddNode(selectedId, "below", t, "task", "Adding task…");
  };

  const insertGateAtSelection = () => {
    if (!selectedId) return;
    const t = promptNewTaskTitle();
    if (!t) return;
    triggerAddNode(selectedId, "above", t, "gate", "Inserting gate…");
  };

  const onGapInsert = (referenceNodeId: string) => {
    const t = promptNewTaskTitle();
    if (!t) return;
    triggerAddNode(referenceNodeId, "above", t, "task", "Adding task…");
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
    void performOptimisticMutation(
      "Removing task…",
      { kind: "delete", nodeId: selectedId },
      [selectedId],
      "delete",
      async () => {
        await deleteNode(selectedId);
      },
    ).catch((e) => setErr(String(e)));
  };

  const publishReady =
    Boolean(
      publishStatus?.scope_dirty &&
        !publishStatus?.blocked &&
        !roadmapBusy,
    );

  return (
    <PmGuiHandlersProvider value={pmGuiHandlers}>
    <PendingMutationsProvider api={pendingMutations}>
    <div className="app-shell">
      <div
        className="app-chrome"
        aria-busy={roadmapBusy}
        // Sticky overload lock: only inert the whole chrome when we're
        // backed up. Below the threshold the user can keep working;
        // individual buttons gate themselves per-row.
        inert={queueOverloaded ? true : undefined}
      >
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
            {roadmapBusy ? (
              <div
                className="roadmap-sync-banner roadmap-sync-banner--inline"
                role="status"
                aria-live="polite"
                aria-label={busyLabel ?? "Working"}
              >
                <span
                  className="roadmap-sync-spinner"
                  aria-hidden="true"
                />
                <span className="roadmap-sync-label">
                  {/* "Saving N changes — …" once the queue is overloaded;
                      otherwise the per-action label as before. */}
                  {queueOverloaded
                    ? `Saving ${busyDepth} changes…`
                    : busyLabel ?? "Working…"}
                  {lockReason ? ` — ${lockReason}` : ""}
                </span>
              </div>
            ) : null}
            <GitWorkflowStatusLabel
              gitWorkflow={displayData?.git_workflow}
              integrationBranchAutoFf={displayData?.integration_branch_auto_ff}
              registryRemoteOverlay={
                displayData?.registry_overlay?.enabled === true
              }
            />
            <button
              type="button"
              className="app-header-icon-btn app-header-tile-btn"
              aria-pressed={hideCompleteActive}
              disabled={queueOverloaded}
              title={
                hideCompleteActive
                  ? "Show all roadmap rows, including completed work"
                  : "Hide rows whose subtree is effectively complete"
              }
              aria-label={
                hideCompleteActive ? "Show completed work" : "Hide completed work"
              }
              onClick={() => setHideCompleteActive((v) => !v)}
            >
              {hideCompleteActive ? "Show Complete" : "Hide Complete"}
            </button>
            <button
              type="button"
              className="app-header-icon-btn"
              aria-label="Settings"
              title="Settings"
              disabled={queueOverloaded}
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
                className={
                  publishReady
                    ? "toolbar-icon-btn toolbar-icon-btn--publish-ready"
                    : "toolbar-icon-btn"
                }
                disabled={roadmapBusy}
                title={
                  publishStatus?.blocked
                    ? "Publish blocked — see dialog for details"
                    : publishReady
                      ? "Publish roadmap changes (ready to share)"
                      : "Publish roadmap changes to the remote repository"
                }
                aria-label="Publish roadmap changes"
                onClick={() => {
                  setPublishOpen(true);
                  void refreshPublishStatus();
                }}
              >
                <IconPublish />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={queueOverloaded || !selectedId || selectedPlanningReadOnly}
                title={
                  selectedPlanningReadOnly
                    ? "Editing is disabled while this task is in active development (in progress, MR state, or checkout matches the registered branch)"
                    : "Edit selected task"
                }
                aria-label="Edit selected task"
                onClick={() =>
                  guardRowAction(selectedId, () => {
                    if (selectedId) openEditNode(selectedId);
                  })
                }
              >
                <IconPencil />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={queueOverloaded || indentDisabled}
                title="Indent"
                aria-label="Indent"
                onClick={() =>
                  guardRowAction(selectedId, () => {
                    if (selectedId) void triggerIndent(selectedId);
                  })
                }
              >
                <IconIndent />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={queueOverloaded || outdentDisabled}
                title="Outdent"
                aria-label="Outdent"
                onClick={() =>
                  guardRowAction(selectedId, () => {
                    if (selectedId) void triggerOutdent(selectedId);
                  })
                }
              >
                <IconOutdent />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={queueOverloaded || !selectedId}
                title="Add task above selection"
                aria-label="Add task above selection"
                onClick={() => guardRowAction(selectedId, addAbove)}
              >
                <IconRowAbove />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={queueOverloaded || !selectedId}
                title="Add task below selection"
                aria-label="Add task below selection"
                onClick={() => guardRowAction(selectedId, addBelow)}
              >
                <IconRowBelow />
              </button>
              <button
                type="button"
                className="toolbar-icon-btn"
                disabled={queueOverloaded || !selectedId || gateInsertDisabled}
                title={
                  !selectedId
                    ? "Select a row first"
                    : gateInsertDisabled
                      ? "Gate rows must sit under a vision or phase — select an indented row"
                      : "Insert gate at selection (above this row); display ids renumber. PM hold, not dev pickup"
                }
                aria-label="Insert gate at selection"
                onClick={() => guardRowAction(selectedId, insertGateAtSelection)}
              >
                <span className="toolbar-gate-icon" aria-hidden="true">
                  G
                </span>
              </button>
              <button
                type="button"
                className="toolbar-icon-btn toolbar-icon-btn-danger"
                disabled={queueOverloaded || !selectedId}
                title="Delete selected row"
                aria-label="Delete selected row"
                onClick={() => guardRowAction(selectedId, onDeleteSelected)}
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
      {displayData ? (
        <div className="split" ref={splitRef}>
          <div
            className="outline-wrap"
            ref={leftRef}
            style={{ flex: `0 0 ${splitPct}%`, width: `${splitPct}%` }}
            onScroll={() => syncScroll("left")}
          >
            <OutlineTable
              orderedIds={visibleOrderedIds}
              nodesById={byId}
              displayStatusById={displayStatusById}
              outlineStatusById={outlineStatusById}
              rowDepths={visibleRowDepths}
              reorderLocked={hideCompleteActive}
              interactionLocked={queueOverloaded}
              selectedId={selectedId}
              prHints={displayData.pr_hints}
              gitEnrichment={displayData.git_enrichment}
              dependencyInheritance={displayData.dependency_inheritance}
              registryByNode={displayData.registry_by_node}
              gitBranchCurrent={
                displayData.git_workflow?.resolved?.git_branch_current ?? null
              }
              gitUserName={
                displayData.git_workflow?.resolved?.git_user_name ?? null
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
              performRoadmapMutation={performRoadmapMutation}
              performOptimisticMutation={performOptimisticMutation}
              onMutationError={(msg) => setErr(msg)}
              onWaitMessage={triggerWaitMessage}
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
              orderedIds={visibleOrderedIds}
              nodesById={byId}
              displayStatusById={displayStatusById}
              gitCheckoutById={gitCheckoutById}
              registryByNode={displayData.registry_by_node}
              gitEnrichment={displayData.git_enrichment}
              stackHeaderPx={ganttStackHeaderPx}
              depthOffset={ganttDepthOffset}
              depths={displayData.dependency_depths}
              spans={displayData.dependency_spans}
              edges={displayData.edges}
              showInheritedEdges={showInheritedDeps}
              selectedId={selectedId}
              highlightRowIds={highlightDepRowIds}
              onSelect={setSelectedId}
              onBarDoubleClick={(id) => {
                setSelectedId(id);
                openEditNode(id);
              }}
              onChartBackgroundMouseDown={
                depEditId ? () => void applyDepEdit() : undefined
              }
            />
          </div>
        </div>
      ) : (
        <p style={{ padding: "1rem" }}>Loading roadmap…</p>
      )}
      <Suspense fallback={null}>
        {displayData
          ? editOpenIds.map((nodeId, index) => {
              const emNode = byId[nodeId];
              if (!emNode) return null;
              const persisted =
                (emNode.status as string)?.trim() || "Not Started";
              const emBaseStatus = displayStatusById[nodeId] ?? persisted;
              const emOutlineStatus =
                outlineStatusById[nodeId] ?? emBaseStatus;
              const modalPlanningReadOnly = pmPlanningTitleReadOnlyFromRow(
                Boolean(gitCheckoutById[nodeId]),
                emBaseStatus,
                emOutlineStatus,
              );
              const passThrough = editOpenIds.length > 1;
              return (
                <EditModal
                  key={nodeId}
                  node={emNode}
                  pmDisplayStatusResolved={displayStatusById[nodeId]}
                  allNodes={displayData.nodes}
                  modalStorageKey={nodeId}
                  stackZIndex={50 + index}
                  backdropPassThrough={passThrough}
                  closeOnEscape={index === editOpenIds.length - 1}
                  headerMinTop={0}
                  spawnInitialRect={spawnRects[nodeId]}
                  editTileMode={editTileMode}
                  tileRect={tileRects?.[nodeId] ?? null}
                  resumeFreeRect={resumeAfterUntile?.[nodeId] ?? null}
                  titleBarActive={focusedEditNodeId === nodeId}
                  onActivate={() => focusEditNode(nodeId)}
                  onRectCommit={(r) => handleEditRectCommit(nodeId, r)}
                  onTileToggle={toggleTileLayout}
                  tileMode={editTileMode}
                  tileToggleDisabled={queueOverloaded}
                  dependencyInheritance={displayData.dependency_inheritance?.[nodeId]}
                  registryByNode={displayData.registry_by_node}
                  gitEnrichment={displayData.git_enrichment}
                  prHints={displayData.pr_hints}
                  onClose={() => closeEditNode(nodeId)}
                  onOpenNode={openEditNode}
                  onPersisted={() =>
                    void runRoadmapAction("Saving task…", loadSnapshot).catch(
                      (e: unknown) => setErr(String(e)),
                    )
                  }
                  readOnlyCheckout={modalPlanningReadOnly}
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
          onOpenSharedMarkdown={(path) => setSharedDocEditPath(path)}
        />
        <SharedDocEditModal
          open={sharedDocEditPath != null}
          filePath={sharedDocEditPath}
          onClose={() => setSharedDocEditPath(null)}
          minTop={0}
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
        <PublishRoadmapModal
          open={publishOpen}
          onClose={() => setPublishOpen(false)}
          status={publishStatus}
          onRefreshStatus={refreshPublishStatus}
          onPublish={handlePublishRoadmap}
          headerMinTop={0}
        />
      </Suspense>
      </div>
    </div>
    </PendingMutationsProvider>
    </PmGuiHandlersProvider>
  );
}
