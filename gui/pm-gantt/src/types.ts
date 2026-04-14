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

export type GitWorkflowIssue = {
  code: string;
  message: string;
  detail: string;
};

export type GitWorkflowResolved = {
  integration_branch: string;
  remote: string;
  git_branch_current: string | null;
  git_head_short: string | null;
};

export type GitWorkflowPayload = {
  ok: boolean;
  config: {
    version: number;
    integration_branch: string;
    remote: string;
  } | null;
  issues: GitWorkflowIssue[];
  resolved: GitWorkflowResolved;
};

/** PM Gantt: when registry.yaml on HEAD may not list in-flight feature-branch work. */
export type RegistryVisibilityPayload = {
  on_integration_branch: boolean;
  local_registry_entry_count: number;
  remote_feature_rm_ref_count: number;
};

export type RoadmapResponse = {
  version: number;
  nodes: RoadmapNode[];
  registry: Record<string, unknown>;
  /** Registry entry keyed by display node id (when present). */
  registry_by_node?: Record<string, Record<string, unknown>>;
  tree: { id: string; outline_depth: number; row_index: number }[];
  /** 0-based dependency step index where the bar starts (finish-to-start + rollup). */
  dependency_depths: Record<string, number>;
  /** Number of dependency steps spanned (≥ 1); parents extend over children. */
  dependency_spans: Record<string, number>;
  edges: DependencyEdge[];
  ordered_ids: string[];
  row_depths: number[];
  pr_hints: Record<string, string>;
  git_enrichment: Record<string, Record<string, unknown>>;
  dependency_inheritance?: Record<string, DependencyInheritanceEntry>;
  outline_actions?: Record<string, OutlineActionsEntry>;
  git_workflow?: GitWorkflowPayload;
  registry_visibility?: RegistryVisibilityPayload;
};
