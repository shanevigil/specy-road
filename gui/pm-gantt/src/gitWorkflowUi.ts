import type {
  GitWorkflowPayload,
  IntegrationBranchAutoFfPayload,
} from "./types";

export type GitWorkflowTone = "red" | "yellow" | "green";

export type GitWorkflowPresentation = {
  tone: GitWorkflowTone;
  /** Short status line next to the gear icon */
  label: string;
  /** First paragraph in the tooltip (explains color / state) */
  tooltipIntro: string;
};

/** Map API payload to label color and copy. */
export function computeGitWorkflowPresentation(
  gw: GitWorkflowPayload,
): GitWorkflowPresentation {
  const codes = new Set(gw.issues.map((i) => i.code));
  const { resolved, config } = gw;
  const ib = config?.integration_branch ?? resolved.integration_branch;
  const rm = config?.remote ?? resolved.remote;

  if (codes.has("missing_config_file")) {
    return {
      tone: "red",
      label: "No git-workflow.yaml",
      tooltipIntro:
        "Red means the tracked contract file roadmap/git-workflow.yaml is missing. Add it from the specy-road init project template (version, integration_branch, remote) so CLI defaults and this status match your team.",
    };
  }
  if (codes.has("invalid_config")) {
    return {
      tone: "red",
      label: "Invalid git-workflow.yaml",
      tooltipIntro:
        "Red means the file exists but failed schema or YAML validation. Fix the file to match schemas/git-workflow.schema.json, then reload.",
    };
  }
  if (codes.has("not_git_repo")) {
    return {
      tone: "yellow",
      label: "Git not connected",
      tooltipIntro:
        "Yellow means this directory is not a git worktree, so branch names and trunk refs cannot be checked. Open the project from a clone or set SPECY_ROAD_REPO_ROOT to the repository root.",
    };
  }
  if (codes.has("integration_ref_missing")) {
    return {
      tone: "yellow",
      label: `Fetch ${rm}/${ib}`,
      tooltipIntro:
        `Yellow means the contract is valid and git is connected, but there is no local ref for the integration branch yet (${rm}/${ib}). Run: git fetch ${rm}, or create/checkout that branch locally.`,
    };
  }

  const cur = resolved.git_branch_current;
  const sha = resolved.git_head_short;
  const label =
    cur != null && cur.length > 0
      ? `${ib} · ${rm} · ${cur}`
      : `${ib} · ${rm}${sha ? ` · ${sha}` : ""}`;

  return {
    tone: "green",
    label,
    tooltipIntro:
      "Green means roadmap/git-workflow.yaml is valid, this tree is a git checkout, and the integration branch ref exists locally. CLI defaults and PM features use these values.",
  };
}

/** Adjust label/tooltip when integration-branch auto fast-forward is enabled but skipped or diverged. */
export function applyIntegrationBranchAutoFfPresentation(
  base: GitWorkflowPresentation,
  ibaff: IntegrationBranchAutoFfPayload | undefined,
  registryRemoteOverlay: boolean,
): GitWorkflowPresentation {
  if (ibaff === undefined || ibaff.enabled !== true) {
    return base;
  }
  const { skipped_reason, sync_state, integration_branch, remote } = ibaff;
  const ib = integration_branch;
  const rm = remote;
  let tone = base.tone;
  let label = base.label;
  let tooltipIntro = base.tooltipIntro;

  const registryNote =
    registryRemoteOverlay &&
    (skipped_reason === "dirty_working_tree" ||
      skipped_reason === "not_on_integration_branch")
      ? ` Merged registry in the PM view can still include claims from ${rm}/${ib} after git fetch (remote overlay).`
      : "";

  if (skipped_reason === "dirty_working_tree") {
    if (tone === "green") tone = "yellow";
    label = `${label} · FF skipped (dirty tree)`;
    tooltipIntro = `${tooltipIntro}\n\nAuto fast-forward of ${ib} is skipped because the working tree is not clean. Commit, stash, or discard changes to allow periodic merge --ff-only, or pull ${ib} manually.${registryNote}`;
  } else if (skipped_reason === "not_on_integration_branch") {
    if (tone === "green") tone = "yellow";
    label = `${label} · FF skipped (branch)`;
    tooltipIntro = `${tooltipIntro}\n\nAuto fast-forward runs only when the current branch is the integration branch (${ib}).${registryNote}`;
  } else if (skipped_reason === "not_git_repo") {
    if (tone === "green") tone = "yellow";
    label = `${label} · FF skipped`;
    tooltipIntro = `${tooltipIntro}\n\nAuto fast-forward requires a git worktree.`;
  } else if (skipped_reason === "integration_ref_unavailable") {
    if (tone === "green") tone = "yellow";
    label = `${label} · no ${rm}/${ib} ref`;
    tooltipIntro = `${tooltipIntro}\n\nRun git fetch ${rm} so refs/remotes/${rm}/${ib} exists.`;
  } else if (sync_state === "diverged") {
    if (tone === "green") tone = "yellow";
    label = `${label} · diverged`;
    tooltipIntro = `${tooltipIntro}\n\nLocal ${ib} and ${rm}/${ib} have diverged; fast-forward is not possible. Resolve with merge/rebase, then pull.`;
  } else if (sync_state === "ahead_of_remote") {
    if (tone === "green") tone = "yellow";
    label = `${label} · ahead of ${rm}`;
    tooltipIntro = `${tooltipIntro}\n\nThis branch is ahead of ${rm}/${ib}; push or reset before others can fast-forward.`;
  }

  return { tone, label, tooltipIntro };
}
