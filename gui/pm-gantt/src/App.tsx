import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addNode,
  fetchRoadmap,
  fetchRoadmapFingerprint,
  indentNode,
  outdentNode,
  patchNode,
} from "./api";
import type { RoadmapNode, RoadmapResponse } from "./types";
import { GanttPane } from "./components/GanttPane";
import { OutlineTable } from "./components/OutlineTable";
import { EditModal } from "./components/EditModal";
import { ConstitutionDrawer } from "./components/ConstitutionDrawer";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { VisionDrawer } from "./components/VisionDrawer";

const SPLIT_STORAGE_KEY = "pmGanttSplitPct";
const REFRESH_STORAGE_KEY = "pmGanttRefreshSec";

function nodesByIdFrom(nodes: RoadmapNode[]): Record<string, RoadmapNode> {
  return Object.fromEntries(nodes.map((n) => [n.id, n]));
}

export default function App() {
  const [data, setData] = useState<RoadmapResponse | null>(null);
  const [repo, setRepo] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [constitutionOpen, setConstitutionOpen] = useState(false);
  const [visionOpen, setVisionOpen] = useState(false);

  const [highlightDepRowId, setHighlightDepRowId] = useState<string | null>(
    null,
  );
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
    return 0;
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
    } catch (e: unknown) {
      setErr(String(e));
    }
  }, []);

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

  useEffect(() => {
    setHighlightDepRowId(null);
  }, [selectedId]);

  const cancelDepEdit = useCallback(() => {
    setDepEditId(null);
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

  useEffect(() => {
    if (!depEditId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelDepEdit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [depEditId, cancelDepEdit]);

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

  const explicitDepRowIds = useMemo(() => {
    if (!selectedId) return [] as string[];
    const node = byId[selectedId];
    if (!node) return [];
    const keys = (node.dependencies ?? []) as string[];
    return keys.map((k) => keyToDisplayId[k] ?? k).filter(Boolean);
  }, [selectedId, byId, keyToDisplayId]);

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

  const sel = selectedId ? byId[selectedId] : null;

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

  const toolbar = (
    <div className="toolbar">
      <button
        type="button"
        disabled={indentDisabled}
        onClick={() => selectedId && void indentNode(selectedId).then(load)}
      >
        Indent
      </button>
      <button
        type="button"
        disabled={outdentDisabled}
        onClick={() => selectedId && void outdentNode(selectedId).then(load)}
      >
        Outdent
      </button>
      <button
        type="button"
        disabled={!selectedId}
        onClick={() => {
          if (!selectedId) return;
          const t = window.prompt("Title for new feature");
          if (!t?.trim()) return;
          void addNode(selectedId, "above", t.trim(), "task")
            .then(load)
            .catch((e) => setErr(String(e)));
        }}
      >
        Add above
      </button>
      <button
        type="button"
        disabled={!selectedId}
        onClick={() => {
          if (!selectedId) return;
          const t = window.prompt("Title for new feature");
          if (!t?.trim()) return;
          void addNode(selectedId, "below", t.trim(), "task")
            .then(load)
            .catch((e) => setErr(String(e)));
        }}
      >
        Add below
      </button>
      {depEditId ? (
        <span
          className="toolbar-dep-mode"
          title="Click another task row to add or remove it as a prerequisite. Clear all removes every prerequisite from the draft; Save deps writes to the roadmap."
        >
          <span className="toolbar-dep-label">
            Editing dependencies for <strong>{byId[depEditId]?.id}</strong>
            <span className="toolbar-dep-hint">
              {" "}
              — Click rows to toggle ·{" "}
            </span>
          </span>
          <button
            type="button"
            disabled={depDraftKeys.size === 0}
            onClick={() => setDepDraftKeys(new Set())}
          >
            Clear all
          </button>
          <button type="button" onClick={() => void applyDepEdit()}>
            Save deps
          </button>
          <button type="button" onClick={cancelDepEdit}>
            Cancel
          </button>
        </span>
      ) : null}
      <button type="button" onClick={() => setConstitutionOpen(true)}>
        Constitution
      </button>
      <button type="button" onClick={() => setVisionOpen(true)}>
        Vision
      </button>
      <button type="button" onClick={() => setSettingsOpen(true)}>
        Settings
      </button>
      <label className="toolbar-inline">
        Highlight dep row
        <select
          value={highlightDepRowId ?? ""}
          onChange={(e) =>
            setHighlightDepRowId(e.target.value || null)
          }
          disabled={!selectedId || explicitDepRowIds.length === 0}
          title="Emphasize a row that is an explicit prerequisite of the selection"
        >
          <option value="">— None —</option>
          {explicitDepRowIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </label>
      <label className="toolbar-inline">
        Auto-refresh
        <select
          value={refreshSec}
          onChange={(e) => setRefreshSec(Number(e.target.value))}
          title="Poll roadmap files; reload when the fingerprint changes"
        >
          <option value={0}>Off</option>
          <option value={5}>5 s</option>
          <option value={10}>10 s</option>
          <option value={15}>15 s</option>
          <option value={30}>30 s</option>
          <option value={60}>60 s</option>
          <option value={120}>120 s</option>
        </select>
      </label>
      <button type="button" onClick={() => void load()}>
        Refresh
      </button>
    </div>
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>specy-road — PM Gantt</h1>
        {toolbar}
        {repo ? <span className="repo-path">{repo}</span> : null}
      </header>
      {err ? <p style={{ padding: "0 0.75rem", color: "crimson" }}>{err}</p> : null}
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
              depEditId={depEditId}
              depDraftKeys={depDraftKeys}
              onToggleDepCandidate={toggleDepCandidate}
              onDepCellActivate={onDepCellActivate}
              onSelect={setSelectedId}
              onDoubleClick={(id) => {
                setSelectedId(id);
                setModalOpen(true);
              }}
              onReordered={load}
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
              edges={data.edges}
              selectedId={selectedId}
              highlightRowId={highlightDepRowId}
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
      {modalOpen && sel ? (
        <EditModal
          node={sel}
          dependencyInheritance={data?.dependency_inheritance?.[sel.id]}
          registryByNode={data?.registry_by_node}
          gitEnrichment={data?.git_enrichment}
          prHints={data?.pr_hints}
          onClose={() => setModalOpen(false)}
          onPersisted={() => void load()}
        />
      ) : null}
      <ConstitutionDrawer
        open={constitutionOpen}
        onClose={() => setConstitutionOpen(false)}
      />
      <VisionDrawer
        open={visionOpen}
        onClose={() => setVisionOpen(false)}
      />
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  );
}
