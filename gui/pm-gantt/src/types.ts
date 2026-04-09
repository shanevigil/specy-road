export type RoadmapNode = {
  id: string;
  node_key: string;
  type: string;
  title: string;
  status?: string;
  parent_id?: string | null;
  dependencies?: string[];
  sibling_order?: number;
  planning_dir?: string | null;
  [key: string]: unknown;
};

export type DependencyInheritanceEntry = {
  explicit: string[];
  inherited: string[];
};

export type OutlineActionsEntry = {
  can_indent: boolean;
  can_outdent: boolean;
};

export type DependencyEdge = {
  from: string;
  to: string;
  kind?: "explicit" | "inherited";
};

export type RoadmapResponse = {
  version: number;
  nodes: RoadmapNode[];
  registry: Record<string, unknown>;
  /** Registry entry keyed by display node id (when present). */
  registry_by_node?: Record<string, Record<string, unknown>>;
  tree: { id: string; outline_depth: number; row_index: number }[];
  dependency_depths: Record<string, number>;
  edges: DependencyEdge[];
  ordered_ids: string[];
  row_depths: number[];
  pr_hints: Record<string, string>;
  git_enrichment: Record<string, Record<string, unknown>>;
  dependency_inheritance?: Record<string, DependencyInheritanceEntry>;
  outline_actions?: Record<string, OutlineActionsEntry>;
};
