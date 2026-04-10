import { useCallback, useEffect, useRef, useState } from "react";
import {
  addNode,
  fetchRoadmap,
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

const SPLIT_STORAGE_KEY = "pmGanttSplitPct";

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
  const depDraftKeysRef = useRef(depDraftKeys);
  depDraftKeysRef.current = depDraftKeys;
  const depEditIdRef = useRef(depEditId);
  depEditIdRef.current = depEditId;

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
    } catch (e: unknown) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    try {
      localStorage.setItem(SPLIT_STORAGE_KEY, String(splitPct));
    } catch {
      /* ignore */
    }
  }, [splitPct]);

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

  const byId = data ? nodesByIdFrom(data.nodes) : {};

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
        <span className="toolbar-dep-mode">
          <span className="toolbar-dep-label">
            Editing dependencies for <strong>{byId[depEditId]?.id}</strong>
          </span>
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
      <button type="button" onClick={() => setSettingsOpen(true)}>
        Settings
      </button>
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
          onClose={() => setModalOpen(false)}
          onSaved={() => {
            void load();
            setModalOpen(false);
          }}
        />
      ) : null}
      <ConstitutionDrawer
        open={constitutionOpen}
        onClose={() => setConstitutionOpen(false)}
      />
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  );
}
