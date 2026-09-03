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
  /**
   * Optimistic concurrency token; must be sent verbatim as
   * X-PM-Gui-Fingerprint on mutating requests. **String** because the
   * raw integer routinely exceeds 2**53 and would lose precision when
   * round-tripped through ``Number`` (IEEE 754 float64). The server
   * accepts string-formatted base-10 integers.
   */
  fingerprint: string;
  /**
   * Broader change-detection token used by the polling refresh hook to
   * notice "something changed elsewhere; refresh the view." Never sent
   * back to the server. Same string-encoding rationale as ``fingerprint``.
   */
  view_fingerprint?: string;
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
  git_enrichment: Record<string, Record<string, unknown>>;
  dependency_inheritance?: Record<string, DependencyInheritanceEntry>;
  outline_actions?: Record<string, OutlineActionsEntry>;
  git_workflow?: GitWorkflowPayload;
  registry_overlay?: RegistryOverlayPayload;
  integration_branch_auto_ff?: IntegrationBranchAutoFfPayload;
  /** Set when the server scheduled deferred ``git fetch`` / integration FF (non-blocking). */
  sync?: { scheduled?: boolean };
  /**
   * Last-worked-on per node, keyed by ``node_key``. Derived from git history
   * server-side and memoized on HEAD, so polling does not re-walk.
   */
  activity?: Record<string, ActivityEntry>;
};

/** One archived subtree, as recorded in `roadmap/archive/index.json`. */
export type ArchiveRecord = {
  archive_id: string;
  /** `shallow`: nodes browsable as JSON. `deep`: folded into one capsule. */
  depth: "shallow" | "deep";
  root_node_id: string;
  root_node_key: string;
  archived_at: string;
  node_keys: string[];
  nodes_summary: {
    id: string;
    node_key: string;
    title: string;
    type: string;
    status?: string;
  }[];
  chunk?: string | null;
  planning?: { origin: string; stored: string }[];
  bundle?: { path: string; sha256: string } | null;
  /** Best-effort; every field may be null (no rollup history, deleted branch, no tags). */
  git?: {
    rollup_branch?: string | null;
    integration_branch?: string | null;
    rollup_tip?: string | null;
    merge_commit?: string | null;
    nearest_tag?: string | null;
    closed_at?: string | null;
  } | null;
};

export type ArchivesResponse = {
  records: ArchiveRecord[];
  /** Subtrees the server would accept an archive for (rollup Complete, unlocked). */
  eligible: { node_id: string; title: string }[];
  /**
   * Auto-archive suggestions from the saved `pm_gui` preferences. Only
   * populated when `auto_archive_completed` is on; archiving moves files, so
   * these are offered for one click, never applied on their own.
   */
  auto?: {
    enabled: boolean;
    older_than_days: number;
    candidates: { node_id: string; completed_at: string }[];
  };
};

/**
 * When a node was last worked on. Keyed by `node_key`, not display id.
 *
 * Derived from git history on the server, never stored: there is no sidecar
 * file, so an existing repo is populated on first load with nothing to seed.
 * `source` says which commit answered — the node's own planning sheet
 * (precise) or, only when that was never committed, its roadmap chunk.
 */
export type ActivityEntry = {
  at: string;
  source: "planning" | "chunk";
};
