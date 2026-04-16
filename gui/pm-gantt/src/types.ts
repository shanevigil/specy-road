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
  /** Local ``git config user.name``; used for Dev column when HEAD matches ``registry.branch``. */
  git_user_name?: string | null;
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

/** Present when ``SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY`` merged remote registry rows. */
export type RegistryOverlayPayload = {
  enabled: boolean;
  remote: string;
  remote_refs_scanned: number;
  merged_remote_entries: number;
  merged_integration_branch_entries?: number;
  skipped_refs: number;
  integration_branch_ref?: string | null;
};

/** Present when ``pm_gui.integration_branch_auto_ff`` is on (``GET /api/roadmap``). */
export type IntegrationBranchAutoFfPayload = {
  enabled: true;
  integration_branch: string;
  remote: string;
  skipped_reason?:
    | "not_git_repo"
    | "not_on_integration_branch"
    | "dirty_working_tree"
    | "integration_ref_unavailable";
  sync_state?:
    | "up_to_date"
    | "behind_ff_possible"
    | "ahead_of_remote"
    | "diverged";
};

/** ``GET /api/publish/status`` — git scope for Publish roadmap control. */
export type PublishStatusPayload = {
  can_publish: boolean;
  scope_dirty: boolean;
  blocked: boolean;
  blocked_reason: string | null;
  detail: string | null;
  current_branch: string | null;
  upstream: string | null;
  scope_paths: string[];
  out_of_scope_paths: string[];
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
  registry_overlay?: RegistryOverlayPayload;
  integration_branch_auto_ff?: IntegrationBranchAutoFfPayload;
};
