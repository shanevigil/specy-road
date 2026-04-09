export type RoadmapNode = {
  id: string;
  type: string;
  title: string;
  status?: string;
  parent_id?: string | null;
  dependencies?: string[];
  sibling_order?: number;
  planning_dir?: string | null;
  [key: string]: unknown;
};

export type RoadmapResponse = {
  version: number;
  nodes: RoadmapNode[];
  registry: Record<string, unknown>;
  tree: { id: string; outline_depth: number; row_index: number }[];
  dependency_depths: Record<string, number>;
  edges: { from: string; to: string }[];
  ordered_ids: string[];
  row_depths: number[];
  pr_hints: Record<string, string>;
  git_enrichment: Record<string, Record<string, unknown>>;
};
