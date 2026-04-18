#!/usr/bin/env python3
"""Pick the next actionable leaf, sync integration branch, brief, register on trunk, branch, prompt."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from do_next_available import (
    _available,
    _load_branch_enrichment,
    _statuses_by_node_key,
    interactive_deps_blocked_entries,
)
from do_next_prompt import write_agent_prompt  # noqa: F401  (re-exported for tests)
from do_next_task_args import parse_do_next_task_args
from do_next_task_interactive import pick_interactive as _pick_interactive
from do_next_task_self_heal import (
    warn_about_stale_claims_before_pickup as _warn_about_stale_claims_before_pickup,
)
from do_next_task_pickup_helpers import (
    push_and_branch_with_self_heal as _do_push_and_branch,
    register_and_commit as _do_register_and_commit,
    write_brief as _do_write_brief,
    write_session_and_prompt as _do_write_session_and_prompt,
)
from do_next_task_leaf_guards import (
    assert_leaf_target as _assert_leaf_target,
    exit_no_actionable_leaves as _exit_no_actionable_leaves,
)
from registration_pickup_commit import registration_commit_message
from work_dir_stash import (
    restore_work_dir_changes as _restore_work,
    stash_work_dir_changes as _stash_work,
)
from roadmap_load import load_roadmap
from do_next_task_virtual_complete import (
    virtual_complete_from_registry as _virtual_complete_from_registry,
)
from specy_road.do_next_milestone_pickup import (
    exit_no_leaves_under_parent as _exit_no_leaves_under_parent,
    resolve_milestone_parent_filter as _resolve_milestone_parent_filter,
)
from specy_road.git_workflow_config import (
    merge_request_requires_manual_approval,
    on_complete_from_git_workflow,
    require_implementation_review_before_finish,
    resolve_integration_defaults,
)
from specy_road.milestone_subtree import filter_available_under_parent
from specy_road.on_complete_pickup import print_pickup_footer, prompt_on_complete
from specy_road.runtime_paths import default_user_repo_root
from validate_roadmap import validate_at

ROOT = Path.cwd()
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
WORK_DIR = ROOT / "work"


# ---------------------------------------------------------------------------
# Roadmap queries
# ---------------------------------------------------------------------------


def _virtual_keys_for_mode(reg: dict, remote: str) -> tuple[set[str], list[str]]:
    """Apply F-007 PR-gating to the virtual-complete computation."""
    on_complete_mode = on_complete_from_git_workflow(ROOT)
    if on_complete_mode == "pr":
        logs: list[str] = []
        if reg.get("entries"):
            logs.append(
                "[info] on_complete=pr: downstream tasks blocked until "
                "upstream PRs merge (per F-007 PR-gating)."
            )
        return set(), logs
    return _virtual_complete_from_registry(reg, repo_root=ROOT, remote=remote)


def _resync_and_select(
    base: str,
    remote: str,
    parent_filter,
) -> tuple[list[dict], dict, list[dict], dict[str, str]]:
    """Sync integration branch, recompute availability, exit if empty."""
    _sync_integration_branch(base, remote)
    reg = _load_registry()
    nodes = load_roadmap(ROOT)["nodes"]
    enrich = _load_branch_enrichment(ROOT)
    integration_statuses = _statuses_by_node_key(nodes)
    virtual_keys, virtual_logs = _virtual_keys_for_mode(reg, remote)
    for line in virtual_logs:
        print(line)
    status_overrides = {nk: "complete" for nk in virtual_keys}
    available = _available(
        nodes, reg, enrich,
        status_overrides=status_overrides or None,
        virtual_complete_keys=virtual_keys or None,
    )
    if parent_filter:
        available = filter_available_under_parent(available, parent_filter, nodes)
    if not available:
        if parent_filter:
            _exit_no_leaves_under_parent(parent_filter, after_sync=True)
        _exit_no_actionable_leaves(nodes, reg, after_sync=True)
    return nodes, reg, available, integration_statuses


def _validate_or_exit() -> None:
    """F-006/F-008: run self-healing validate before pickup."""
    # Skip in test scenarios where load_roadmap is monkeypatched and there's
    # no real manifest on disk under ROOT.
    if not (ROOT / "roadmap" / "manifest.json").is_file():
        return
    try:
        validate_at(ROOT, no_overlap_warn=True, require_registry=True)
    except SystemExit as e:
        if e.code not in (0, None):
            print(
                "error: roadmap validation failed; fix the issues above, "
                "then re-run specy-road do-next-available-task.",
                file=sys.stderr,
            )
            raise


def _load_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        return {"version": 1, "entries": []}
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


# ---------------------------------------------------------------------------
# Git + registry operations
# ---------------------------------------------------------------------------


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


def _current_branch() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _working_tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return not r.stdout.strip()


def _assert_working_tree_clean() -> None:
    if not _working_tree_clean():
        print(
            "error: working tree is not clean (commit, stash, or discard "
            "changes first).\n  Integration-branch sync and creating a new "
            "feature branch need a clean tree.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _assert_current_branch_equals(base: str) -> None:
    cur = _current_branch()
    if cur == "HEAD":
        print(
            "error: detached HEAD — check out the integration branch before "
            "picking a task.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if cur != base:
        print(
            f"error: expected integration branch {base!r}, but HEAD is "
            f"{cur!r}.\n  git checkout {base}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _stash_work_dir_changes() -> bool:
    return _stash_work(ROOT, "registry commit")


def _restore_work_dir_changes(stashed: bool) -> None:
    _restore_work(ROOT, stashed)


def _sync_integration_branch(base: str, remote: str) -> None:
    """Fetch, checkout, fast-forward integration branch via _git."""
    _assert_working_tree_clean()
    _git("fetch", remote)
    _git("checkout", base)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local '{base}' to {remote}/{base}."
            "\n  Resolve your local integration branch (e.g. pull with "
            "rebase, or reset after team agreement), then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _checkout_new_branch(branch: str) -> None:
    _git("checkout", "-b", branch)


def _register_and_commit(
    node: dict,
    branch: str,
    reg: dict,
    commit_message: str,
    *,
    impl_review_gate: bool,
) -> None:
    _do_register_and_commit(
        registry_path=REGISTRY_PATH,
        git_runner=_git,
        node=node,
        branch=branch,
        reg=reg,
        commit_message=commit_message,
        impl_review_gate=impl_review_gate,
    )


def _push_integration_branch(remote: str, base: str) -> None:
    _git("push", remote, base)


# ---------------------------------------------------------------------------
# Brief output
# ---------------------------------------------------------------------------


def _write_brief(node: dict, nodes: list[dict]) -> Path:
    return _do_write_brief(WORK_DIR, node, nodes)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _push_and_branch_with_self_heal(**kwargs) -> None:
    _do_push_and_branch(
        repo_root=ROOT,
        registry_path=REGISTRY_PATH,
        git_runner=_git,
        push_integration_branch_fn=_push_integration_branch,
        checkout_new_branch_fn=_checkout_new_branch,
        **kwargs,
    )


def _write_session_and_prompt(**kwargs) -> Path:
    # Resolve write_agent_prompt at call time so monkeypatch of
    # dnt.write_agent_prompt in tests is honored.
    import sys as _sys
    fn = _sys.modules[__name__].write_agent_prompt
    return _do_write_session_and_prompt(
        work_dir=WORK_DIR, repo_root=ROOT,
        write_agent_prompt_fn=fn,
        **kwargs,
    )


def _finalize_pickup(
    node: dict,
    nodes: list[dict],
    branch: str,
    *,
    base: str,
    remote: str,
    push_registry: bool,
    include_ci_skip: bool,
    on_complete: str,
) -> None:
    node_id = node["id"]
    codename = node["codename"]
    print(f"\n[{node_id}] {node.get('title', '')}")
    print(f"implementation branch: {branch}\n")

    brief_path = _write_brief(node, nodes)
    reg = _load_registry()
    commit_msg = registration_commit_message(
        codename,
        include_ci_skip=include_ci_skip,
    )
    _register_and_commit(
        node, branch, reg, commit_msg,
        impl_review_gate=require_implementation_review_before_finish(ROOT),
    )
    print("registered in roadmap/registry.yaml on integration branch (committed)")

    _push_and_branch_with_self_heal(
        push_registry=push_registry, base=base, remote=remote,
        branch=branch, node_id=node_id, codename=codename,
    )
    prompt_path = _write_session_and_prompt(
        node=node, nodes=nodes, brief_path=brief_path, on_complete=on_complete,
    )

    print_pickup_footer(
        root=ROOT,
        work_dir=WORK_DIR,
        brief_path=brief_path,
        prompt_path=prompt_path,
        push_registry=push_registry,
        remote=remote,
        base=base,
        mr_manual=merge_request_requires_manual_approval(ROOT),
        impl_review_gate=require_implementation_review_before_finish(ROOT),
        on_complete=on_complete,
        node_id=node_id,
    )


def _check_pre_sync_availability(remote: str, parent_filter) -> None:
    """Pre-sync availability sanity check: exit if no actionable leaf locally."""
    nodes = load_roadmap(ROOT)["nodes"]
    reg = _load_registry()
    # F-014: surface stale registry claims to the next user immediately.
    _warn_about_stale_claims_before_pickup(repo_root=ROOT, reg=reg, remote=remote)
    enrich = _load_branch_enrichment(ROOT)
    available = _available(nodes, reg, enrich)
    if parent_filter:
        available = filter_available_under_parent(available, parent_filter, nodes)
    if not available:
        if parent_filter:
            _exit_no_leaves_under_parent(parent_filter, after_sync=False)
        _exit_no_actionable_leaves(nodes, reg, after_sync=False)


def _pick_node(args, nodes, reg, available, integration_statuses) -> dict:
    """Choose a leaf — interactive or first; assert leaf target."""
    if args.interactive:
        blocked = interactive_deps_blocked_entries(
            nodes, reg,
            integration_statuses=integration_statuses,
            ready_ids={n["id"] for n in available},
        )
        node = _pick_interactive(available, nodes, blocked_entries=blocked)
    else:
        node = available[0]
    _assert_leaf_target(node, nodes)
    return node


def main(argv: list[str] | None = None) -> None:
    global ROOT, REGISTRY_PATH, WORK_DIR
    args = parse_do_next_task_args(argv)
    include_ci_skip = not args.no_ci_skip_in_message
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
    WORK_DIR = ROOT / "work"
    base, remote, gw_warns = resolve_integration_defaults(
        ROOT,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    parent_filter = _resolve_milestone_parent_filter(WORK_DIR, args)
    _validate_or_exit()
    _check_pre_sync_availability(remote, parent_filter)
    # F-011: stash any in-progress work/ changes so the integration-branch
    # registry commit is clean; restore onto the new feature branch.
    stashed = _stash_work_dir_changes()
    try:
        nodes, reg, available, integration_statuses = _resync_and_select(
            base, remote, parent_filter
        )
        _assert_current_branch_equals(base)
        node = _pick_node(args, nodes, reg, available, integration_statuses)
        branch = f"feature/rm-{node['codename']}"
        on_complete = prompt_on_complete(ROOT, args.on_complete)
        _finalize_pickup(
            node, nodes, branch,
            base=base, remote=remote, push_registry=True,
            include_ci_skip=include_ci_skip, on_complete=on_complete,
        )
    finally:
        _restore_work_dir_changes(stashed)


if __name__ == "__main__":
    main()
