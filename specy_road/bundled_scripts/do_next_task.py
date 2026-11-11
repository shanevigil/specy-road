#!/usr/bin/env python3
"""Pick the next actionable leaf, sync integration branch, brief, register on trunk, branch, prompt."""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from specy_road.bundled_scripts.do_next_available import (
    _available,
    _load_branch_enrichment,
    _statuses_by_node_key,
    interactive_deps_blocked_entries,
    run_baseline_gate,
)
from specy_road.bundled_scripts.do_next_prompt import (
    print_pickup_header,
    write_agent_prompt,
)
from specy_road.bundled_scripts.do_next_task_args import build_parser, parse_do_next_task_args
from specy_road.cli_entry import run_reporting
from specy_road.bundled_scripts.do_next_task_interactive import pick_interactive as _pick_interactive
from specy_road.bundled_scripts.do_next_task_self_heal import (
    warn_about_stale_claims_before_pickup as _warn_about_stale_claims_before_pickup,
)
from specy_road.bundled_scripts.do_next_task_pickup_helpers import (
    leaf_worktree_path,
    push_and_branch_with_self_heal as _do_push_and_branch,
    refuse_linked_worktree,
    branch_fns,
    worktree_work_dir,
    write_brief as _do_write_brief,
    write_session_and_prompt as _do_write_session_and_prompt,
)
from specy_road.bundled_scripts.do_next_task_leaf_guards import (
    assert_leaf_target as _assert_leaf_target,
    drop_unauthored,
    exit_no_actionable_leaves as _exit_no_actionable_leaves,
)
from specy_road.bundled_scripts.do_next_task_register import register_claim
from specy_road.registration_pickup_commit import registration_commit_message
from specy_road.roadmap_load import load_roadmap
from specy_road.bundled_scripts.do_next_task_virtual_complete import (
    virtual_complete_from_registry as _virtual_complete_from_registry,
)
from specy_road.bundled_scripts.do_next_finished_unmerged import finished_unmerged_ids
from specy_road.bundled_scripts.do_next_task_held_claim import refuse_second_claim, validate_or_exit
from specy_road.git_subprocess import git_run
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.review_policy_pin import pinned_message
from specy_road.do_next_milestone_pickup import (
    exit_no_leaves_under_parent as _exit_no_leaves_under_parent,
    resolve_milestone_parent_filter as _resolve_milestone_parent_filter,
)
from specy_road.git_workflow_config import (
    git_config_user_name,
    merge_request_requires_manual_approval,
    on_complete_from_git_workflow,
    require_implementation_review_before_finish,
    resolve_prefer_agentic,
)
from specy_road.milestone_subtree import filter_available_under_parent
from specy_road.nested_repos import announce_nested_worktrees
from specy_road.on_complete_pickup import print_pickup_footer, prompt_on_complete
from specy_road.planning_scaffold_check import warn_scaffold_at_pickup
from specy_road.cli_entry import integration_defaults
from specy_road.runtime_paths import resolve_repo_root
from specy_road.repo_ops import assert_working_tree_clean, current_branch, sync_integration_branch
from specy_road.repo_lock import pickup_finish_lock

# ---------------------------------------------------------------------------
# Roadmap queries
# ---------------------------------------------------------------------------


def _virtual_keys_for_mode(root: Path, reg: dict, remote: str) -> tuple[set[str], list[str]]:
    """Apply F-007 PR-gating to the virtual-complete computation."""
    on_complete_mode = on_complete_from_git_workflow(root)
    if on_complete_mode == "pr":
        logs: list[str] = []
        if reg.get("entries"):
            logs.append(
                "[info] on_complete=pr: downstream tasks blocked until "
                "upstream PRs merge (per F-007 PR-gating)."
            )
        return set(), logs
    return _virtual_complete_from_registry(reg, repo_root=root, remote=remote)


def _drop_finished_unmerged(
    root: Path, available: list[dict], base: str, remote: str
) -> list[dict]:
    """Remove leaves a feature branch already finished but ``base`` has not merged.

    The registry row is the only other thing standing between a finished leaf
    and a second claim, and every release path — abort, self-heal, hand edit —
    removes the row while leaving the branch. See
    :mod:`specy_road.bundled_scripts.do_next_finished_unmerged`.
    """
    finished, logs = finished_unmerged_ids(
        available, repo_root=root, remote=remote, integration_branch=base
    )
    for line in logs:
        print(line)
    if not finished:
        return available
    return [n for n in available if n.get("id") not in finished]


def _resync_and_select(
    root: Path,
    base: str,
    remote: str,
    parent_filter,
    *,
    sync: bool = True,
    allow_unauthored: bool = False,
    allow_scaffold_planning: bool = False,
    prefer_agentic_cli: bool | None = None,
) -> tuple[list[dict], dict, list[dict], dict[str, str]]:
    """Sync integration branch, recompute availability, exit if empty.

    ``sync=False`` (``--local``) skips only the fetch and merge. Unauthored
    leaves are dropped here, after sync, because the sync may bring their sheet;
    ``prefer_agentic_pick_order`` is read after it for the same reason.
    """
    if sync:
        sync_integration_branch(
            root,
            base,
            remote,
            retry_hint="retry do-next-available-task",
            clean_tree_detail=(
                "Integration-branch sync and creating a new feature branch need a clean tree "
                "outside work/."
            ),
            except_work=True,
        )
    else:
        assert_working_tree_clean(
            root, "A local pickup still commits the claim on the integration branch.",
            except_work=True,
        )
    reg = read_registry(registry_path(root))
    nodes = load_roadmap(root)["nodes"]
    enrich = _load_branch_enrichment(root)
    integration_statuses = _statuses_by_node_key(nodes)
    virtual_keys, virtual_logs = _virtual_keys_for_mode(root, reg, remote)
    for line in virtual_logs:
        print(line)
    status_overrides = {nk: "complete" for nk in virtual_keys}
    available = _available(
        nodes, reg, enrich,
        status_overrides=status_overrides or None,
        virtual_complete_keys=virtual_keys or None,
        prefer_agentic=resolve_prefer_agentic(root, cli=prefer_agentic_cli),
    )
    available = _drop_finished_unmerged(root, available, base, remote)
    if parent_filter:
        available = filter_available_under_parent(available, parent_filter, nodes)
    available = drop_unauthored(
        root,
        available,
        allow_unauthored=allow_unauthored,
        allow_scaffold_planning=allow_scaffold_planning,
    )
    if not available:
        if parent_filter:
            _exit_no_leaves_under_parent(parent_filter, after_sync=True, integration_branch=base)
        _exit_no_actionable_leaves(nodes, reg, after_sync=True, integration_branch=base)
    return nodes, reg, available, integration_statuses


def _assert_current_branch_equals(root: Path, base: str) -> None:
    cur = current_branch(root)
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


def _push_integration_branch(root: Path, remote: str, base: str) -> None:
    git_run(root, "push", remote, base)


def _write_brief(root: Path, node: dict, nodes: list[dict]) -> Path:
    return _do_write_brief(root / "work", node, nodes)


def _push_and_branch_with_self_heal(root: Path, worktree: Path | None, base: str, **kwargs) -> None:
    create, adopt = branch_fns(lambda *a: git_run(root, *a), base, worktree)
    _do_push_and_branch(
        repo_root=root,
        registry_path=registry_path(root),
        git_runner=lambda *a: git_run(root, *a),
        push_integration_branch_fn=partial(_push_integration_branch, root),
        checkout_new_branch_fn=create,
        checkout_existing_branch_fn=adopt,
        base=base,
        **kwargs,
    )


def _write_session_and_prompt(**kwargs) -> Path:
    # A plain global reference is already resolved at call time, so a test
    # patching dnt.write_agent_prompt is honoured without going through
    # sys.modules to fetch the same binding.
    return _do_write_session_and_prompt(write_agent_prompt_fn=write_agent_prompt, **kwargs)


def _finalize_pickup(
    root: Path,
    node: dict,
    nodes: list[dict],
    branch: str,
    *,
    base: str,
    remote: str,
    push_registry: bool,
    include_ci_skip: bool,
    on_complete: str,
    owner: str | None = None,
    worktree: Path | None = None,
) -> None:
    node_id = node["id"]
    codename = node["codename"]
    print_pickup_header(node, branch, root)

    brief_path = _write_brief(root, node, nodes)
    reg = read_registry(registry_path(root))
    commit_msg = pinned_message(root, registration_commit_message(   # review policy pinned at claim (M21.30)
        codename,
        include_ci_skip=include_ci_skip,
    ))
    register_claim(
        root, node, branch, reg, commit_msg,
        git_runner=lambda *a: git_run(root, *a),
        impl_review_gate=require_implementation_review_before_finish(root),
        owner=owner,
    )
    print("registered in roadmap/registry.yaml on integration branch (committed with the regenerated digest)")

    _push_and_branch_with_self_heal(
        root, worktree, base, push_registry=push_registry, remote=remote,
        branch=branch, node_id=node_id, codename=codename,
    )
    leaf_root, work_dir = root, root / "work"
    if worktree:   # the leaf's agent runs in the worktree, so its brief, prompt and session go there
        leaf_root, work_dir = worktree_work_dir(root, worktree, brief_path)
        announce_nested_worktrees(root, leaf_root, branch, node.get("touch_zones"))   # nested_repos
        brief_path = work_dir / brief_path.name
        print(f"worktree: {worktree} has {branch}; this checkout stays on {base}")
    prompt_path = _write_session_and_prompt(
        work_dir=work_dir, repo_root=leaf_root,
        node=node, nodes=nodes, brief_path=brief_path, on_complete=on_complete,
    )

    print_pickup_footer(
        root=root,
        work_dir=work_dir,
        brief_path=brief_path,
        prompt_path=prompt_path,
        push_registry=push_registry,
        remote=remote,
        base=base,
        mr_manual=merge_request_requires_manual_approval(root),
        impl_review_gate=require_implementation_review_before_finish(root),
        on_complete=on_complete,
        node_id=node_id,
    )


def _check_pre_sync_availability(root: Path, base: str, remote: str, parent_filter) -> None:
    """Pre-sync availability sanity check: exit if no actionable leaf locally."""
    nodes = load_roadmap(root)["nodes"]
    reg = read_registry(registry_path(root))
    # F-014: surface stale registry claims to the next user immediately.
    _warn_about_stale_claims_before_pickup(repo_root=root, reg=reg, remote=remote)
    enrich = _load_branch_enrichment(root)
    available = _available(nodes, reg, enrich)
    if parent_filter:
        available = filter_available_under_parent(available, parent_filter, nodes)
    if not available:
        if parent_filter:
            _exit_no_leaves_under_parent(parent_filter, after_sync=False, integration_branch=base)
        _exit_no_actionable_leaves(nodes, reg, after_sync=False, integration_branch=base)


def _pick_node(root: Path, args, nodes, reg, available, integration_statuses) -> dict:
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
    if args.allow_scaffold_planning:
        warn_scaffold_at_pickup(root, node)
    return node


def main(argv: list[str] | None = None) -> None:
    """Pick up the next leaf. A command error is printed once and becomes its exit code."""
    run_reporting(lambda: _pickup(argv))


def _pickup(argv: list[str] | None) -> None:
    args = parse_do_next_task_args(argv)
    include_ci_skip = not args.no_ci_skip_in_message
    root = resolve_repo_root(args)
    with pickup_finish_lock(root, operation="do-next-available-task"):
        _run_pickup(root, args, include_ci_skip=include_ci_skip)


def _run_pickup(root: Path, args, *, include_ci_skip: bool) -> None:
    refuse_linked_worktree(root, local=args.local, worktree=args.worktree)
    base, remote = integration_defaults(root, args)

    parent_filter = _resolve_milestone_parent_filter(root / "work", args)
    validate_or_exit(root)
    refuse_second_claim(root, allow=args.allow_second_claim)
    if args.local:
        print("local pickup: no fetch, no push (see the footer)", file=sys.stderr)
    else:
        _check_pre_sync_availability(root, base, remote, parent_filter)
    # work/ is never stashed: the stash stack is shared by every session in the
    # checkout, and files another session wrote mid-pickup were stranded in it.
    # Untracked work/ files ride the branch switches; the registry commit names
    # its one path, so nothing else in the index goes with it.
    nodes, reg, available, integration_statuses = _resync_and_select(
        root, base, remote, parent_filter, sync=not args.local,
        allow_unauthored=args.allow_unauthored,
        allow_scaffold_planning=args.allow_scaffold_planning,
        prefer_agentic_cli=args.prefer_agentic,
    )
    _assert_current_branch_equals(root, base)
    run_baseline_gate(root, base, cli=args.baseline_cmd, warn_only=args.baseline_warn)
    node = _pick_node(root, args, nodes, reg, available, integration_statuses)
    branch = f"feature/rm-{node['codename']}"
    worktree = leaf_worktree_path(root, node["codename"]) if args.worktree else None
    on_complete = prompt_on_complete(root, args.on_complete)
    _finalize_pickup(
        root, node, nodes, branch,
        base=base, remote=remote, push_registry=not args.local,
        include_ci_skip=include_ci_skip, on_complete=on_complete,
        owner=args.owner or git_config_user_name(root), worktree=worktree,
    )


if __name__ == "__main__":
    main()
