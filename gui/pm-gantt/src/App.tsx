import { useCallback, useEffect, useRef, useState } from "react";
import {
  addNode,
  fetchRoadmap,
  indentNode,
  outdentNode,
} from "./api";
import type { RoadmapNode, RoadmapResponse } from "./types";
import { GanttPane } from "./components/GanttPane";
import { OutlineTable } from "./components/OutlineTable";
import { EditModal } from "./components/EditModal";
import { SettingsDrawer } from "./components/SettingsDrawer";

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

  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncLock = useRef(false);

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

  const byId = data ? nodesByIdFrom(data.nodes) : {};
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
        <div className="split">
          <div
            className="outline-wrap"
            ref={leftRef}
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
              onSelect={setSelectedId}
              onDoubleClick={(id) => {
                setSelectedId(id);
                setModalOpen(true);
              }}
              onReordered={load}
            />
          </div>
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
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  );
}
