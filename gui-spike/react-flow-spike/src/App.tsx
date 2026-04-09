import { useCallback, useEffect, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import {
  type MergedRoadmap,
  roadmapToFlowElements,
} from "./roadmapLayout";

async function loadSampleRoadmap(): Promise<MergedRoadmap> {
  const res = await fetch(`${import.meta.env.BASE_URL}sample-merged-roadmap.json`);
  if (!res.ok) throw new Error(`Failed to load sample: ${res.status}`);
  return res.json() as Promise<MergedRoadmap>;
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadSampleRoadmap()
      .then((data) => {
        if (cancelled) return;
        const { nodes: n, edges: e } = roadmapToFlowElements(data);
        setNodes(n);
        setEdges(e);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [setEdges, setNodes]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <div className="spike-banner">
        PM GUI spike: merged roadmap JSON → React Flow (read-only sample). Drag nodes to
        try layout; new edges are local-only (no API).
        {error ? ` — Error: ${error}` : ""}
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={1.5}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}
