#!/usr/bin/env python3
"""Pick the next actionable leaf, sync the integration branch, brief, register, branch, prompt.

Before pickup changes anything it validates the roadmap and refuses a second claim in a
checkout that already holds one (exit 6); while selecting, it skips leaves whose planning
sheet is unwritten and reports why the queue is empty when nothing is left.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from functools import partial
from pathlib import Path

from specy_road.brief_acceptance import acceptance_ids
from specy_road.bundled_scripts.do_next_available import (
    _available,
    _leaf_diagnostics,
    _load_branch_enrichment,
    _statuses_by_node_key,
    interactive_deps_blocked_entries,
    run_baseline_gate,
)
from specy_road.bundled_scripts.do_next_finished_unmerged import (
    finished_unmerged_ids,
    node_complete_on_ref,
)
from specy_road.bundled_scripts.do_next_prompt import (
    print_pickup_header,
    write_agent_prompt,
)
from specy_road.bundled_scripts.do_next_task_args import build_parser, parse_do_next_task_args
from specy_road.bundled_scripts.do_next_task_interactive import (
    pick_interactive as _pick_interactive,
)
from specy_road.bundled_scripts.do_next_task_pickup_helpers import (
    branch_fns,
    leaf_worktree_path,
    push_and_branch_with_self_heal as _do_push_and_branch,
    refuse_linked_worktree,
    worktree_work_dir,
    write_brief as _do_write_brief,
    write_session_and_prompt as _do_write_session_and_prompt,
)
from specy_road.bundled_scripts.do_next_task_register import register_claim
from specy_road.bundled_scripts.do_next_task_self_heal import (
    warn_about_stale_claims_before_pickup as _warn_about_stale_claims_before_pickup,
)
from specy_road.bundled_scripts.grind_session_events import EXIT_IN_FLIGHT
from specy_road.bundled_scripts.grind_session_in_flight import (
    InFlightClaim,
    own_in_flight_claims,
)
from specy_road.cli_entry import integration_defaults, run_reporting
from specy_road.do_next_milestone_pickup import (
    exit_no_leaves_under_parent as _exit_no_leaves_under_parent,
    print_integration_branch_hint,
    resolve_milestone_parent_filter as _resolve_milestone_parent_filter,
)
from specy_road.git_subprocess import git_ok, git_root, git_run, local_branch_exists
from specy_road.git_workflow_config import (
    git_config_user_name,
    merge_request_requires_manual_approval,
    on_complete_from_git_workflow,
    require_implementation_review_before_finish,
    resolve_prefer_agentic,
)
from specy_road.milestone_subtree import filter_available_under_parent, structural_leaf_ids
from specy_road.nested_repos import announce_nested_worktrees
from specy_road.on_complete_pickup import print_pickup_footer, prompt_on_complete
from specy_road.planning_scaffold_check import scaffold_sheet, warn_scaffold_at_pickup
from specy_road.planning_sheet_bootstrap import placeholder_sheet
from specy_road.registration_pickup_commit import registration_commit_message
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.repo_lock import pickup_finish_lock
from specy_road.repo_ops import assert_working_tree_clean, current_branch, sync_integration_branch
from specy_road.review_policy_pin import pinned_message
from specy_road.roadmap_load import load_roadmap
from specy_road.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.runtime_paths import resolve_repo_root
from specy_road.validate_roadmap_runner import validate_at

# ---------------------------------------------------------------------------
# Roadmap queries
# ---------------------------------------------------------------------------


def _virtual_complete_from_registry(
    reg: dict,
    *,
    repo_root: Path,
    remote: str,
) -> tuple[set[str], list[str]]:
    """node_keys Complete on feature-branch tips but not yet on integration (dep eval only)."""
    virtual: set[str] = set()
    log_lines: list[str] = []
    entries = reg.get("entries") or []
    for e in entries:
        if not isinstance(e, dict):
            continue
        branch = e.get("branch")
        node_id = e.get("node_id")
        if not isinstance(branch, str) or not branch.strip():
            continue
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        ref = f"{remote}/{branch.strip()}"
        nodes_at = load_roadmap_nodes_at_ref(repo_root, ref)
        if nodes_at is None:
            continue
        matched = next((n for n in nodes_at if n.get("id") == node_id), None)
        if matched is None:
            continue
        if (matched.get("status") or "").lower() != "complete":
            continue
        nk = matched.get("node_key")
        if not isinstance(nk, str) or not nk:
            continue
        virtual.add(nk)
        codename = e.get("codename", "") or ""
        log_lines.append(
            f"[info] Treating node {node_id} ({codename}) as Complete for dependency "
            f"evaluation — {ref} shows Complete; integration branch may not have merged "
            f"the PR yet."
        )
    return virtual, log_lines


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


# ---------------------------------------------------------------------------
# Leaf-only pickup guards and empty-queue diagnostics
# ---------------------------------------------------------------------------


def _fmt_ids(ids: Iterable[str], *, cap: int = 6) -> str:
    vals = list(ids)
    if not vals:
        return "none"
    if len(vals) <= cap:
        return ", ".join(vals)
    return ", ".join(vals[:cap]) + f", ... (+{len(vals) - cap} more)"


def _assert_leaf_target(node: dict, nodes: list[dict]) -> None:
    if node["id"] in structural_leaf_ids(nodes):
        return
    print(
        f"error: selected node {node['id']!r} is not a leaf; "
        "default pickup can only claim leaves.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def drop_unauthored(
    root: Path,
    available: list[dict],
    *,
    allow_unauthored: bool,
    allow_scaffold_planning: bool = False,
) -> list[dict]:
    """Remove leaves pickup refuses until their planning sheet is written.

    No ``acceptance`` and a placeholder sheet: skipped unless ``allow_unauthored``.
    ``acceptance`` set but ``## Intent`` / ``## Approach`` still scaffold or promote
    placeholders: skipped unless ``allow_scaffold_planning``.
    """
    kept: list[dict] = []
    for n in available:
        placeholder_reason = placeholder_sheet(root, n)
        if placeholder_reason and not allow_unauthored:
            print(
                f"skipping {n['id']}: {placeholder_reason}. Write the sheet or set acceptance "
                f"(specy-road edit-node {n['id']} --set acceptance=...), or pass "
                "--allow-unauthored to pick it anyway.",
                file=sys.stderr,
            )
            continue
        scaffold_reason = scaffold_sheet(root, n)
        if scaffold_reason and acceptance_ids(n) and not allow_scaffold_planning:
            print(
                f"skipping {n['id']}: {scaffold_reason}. Write its ## Intent and ## Approach "
                "and commit the sheet on this branch, or pass --allow-scaffold-planning "
                "to pick it anyway.",
                file=sys.stderr,
            )
            continue
        kept.append(n)
    return kept


def _exit_no_actionable_leaves(
    nodes: list[dict], reg: dict, *, after_sync: bool,
    integration_branch: str | None = None,
) -> None:
    diag = _leaf_diagnostics(nodes, reg)
    phase = "after sync" if after_sync else "before sync"
    print(f"No actionable leaf tasks available ({phase}).", file=sys.stderr)
    print(
        "  Canonical model requires selecting an actionable leaf only.",
        file=sys.stderr,
    )
    print(
        "  leaf nodes: "
        f"{diag['leaf_nodes']} / total nodes: {diag['total_nodes']}",
        file=sys.stderr,
    )
    print(
        "  blocked by unmet dependencies: "
        f"{_fmt_ids(diag['deps_blocked_leaf_ids'])}",
        file=sys.stderr,
    )
    print(
        "  already claimed leaves: "
        f"{_fmt_ids(diag['claimed_leaf_ids'])}",
        file=sys.stderr,
    )
    print(
        "  open leaves (dependency-satisfied, unclaimed): "
        f"{_fmt_ids(diag['open_leaf_ids'])}",
        file=sys.stderr,
    )
    print(
        "  closed leaves (Complete/Cancelled): "
        f"{_fmt_ids(diag['closed_leaf_ids'])}",
        file=sys.stderr,
    )
    if diag["non_agentic_leaf_ids"]:
        print(
            "  non-agentic leaves: "
            f"{_fmt_ids(diag['non_agentic_leaf_ids'])}",
            file=sys.stderr,
        )
    if diag["missing_codename_leaf_ids"]:
        print(
            "  missing-codename leaves: "
            f"{_fmt_ids(diag['missing_codename_leaf_ids'])}",
            file=sys.stderr,
        )
    # Last, not first: the counts above explain the queue when they can, and
    # this covers the case they cannot show — a node that is not on the trunk
    # yet does not appear in any of them.
    print_integration_branch_hint(integration_branch)
    raise SystemExit(1)


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
    # The review policy is pinned at claim, in the registration commit's trailer.
    commit_msg = pinned_message(root, registration_commit_message(
        codename,
        include_ci_skip=include_ci_skip,
    ))
    register_claim(
        root, node, branch, reg, commit_msg,
        git_runner=lambda *a: git_run(root, *a),
        impl_review_gate=require_implementation_review_before_finish(root),
        owner=owner,
    )
    print(
        "registered in roadmap/registry.yaml on integration branch "
        "(committed with the regenerated digest)"
    )

    _push_and_branch_with_self_heal(
        root, worktree, base, push_registry=push_registry, remote=remote,
        branch=branch, node_id=node_id, codename=codename,
    )
    leaf_root, work_dir = root, root / "work"
    # The leaf's agent runs in the worktree, so its brief, prompt and session go there.
    if worktree:
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


# ---------------------------------------------------------------------------
# Checks that refuse before pickup changes anything
# ---------------------------------------------------------------------------
#
# Pickup used to register, push and switch to a second leaf while the first was
# still checked out, so one checkout silently owned two leaves. grind-session
# already refused that case with exit 6; refuse_second_claim applies the same test,
# :func:`~specy_road.bundled_scripts.grind_session_in_flight.own_in_flight_claims`,
# before pickup changes anything.
#
# A claim is this checkout's when the registry names its branch *and* that branch
# is present locally, minus branches another worktree has checked out: a
# coordinator that hands leaves out with ``--worktree`` keeps every leaf's branch
# in the same repository, and each of those belongs to its own worktree. A claim
# whose branch is gone is not held here (another clone's, or a dead row for
# ``registry-prune``), so it never blocks a pickup. Nor does a claim whose leaf
# is already Complete on its branch: in ``on_complete: pr`` mode finish releases
# the row only on the feature branch, so the integration branch keeps it until
# the PR merges, and the next pickup must not be told to abort finished work.


def validate_or_exit(repo_root: Path) -> None:
    """F-006/F-008: run self-healing validate before pickup."""
    # Skipped when tests monkeypatch load_roadmap and ROOT has no manifest on disk.
    if not (repo_root / "roadmap" / "manifest.json").is_file():
        return
    try:
        validate_at(repo_root, no_overlap_warn=True, require_registry=True)
    except SystemExit as e:
        if e.code not in (0, None):
            print(
                "error: roadmap validation failed; fix the issues above, "
                "then re-run specy-road do-next-available-task.",
                file=sys.stderr,
            )
            raise


def branches_in_other_worktrees(repo_root: Path) -> set[str]:
    """Local branches checked out in a worktree other than this one."""
    here = git_root(repo_root)
    ok, out = git_ok(["worktree", "list", "--porcelain"], repo_root)
    if not ok:
        return set()
    branches: set[str] = set()
    path: Path | None = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line.startswith("branch refs/heads/") and path is not None and path.resolve() != here:
            branches.add(line[len("branch refs/heads/"):])
    return branches


def held_claims(repo_root: Path, reg: dict) -> list[InFlightClaim]:
    """Registry claims held here: the branch exists locally, no other worktree has it checked
    out, and the leaf is not finished on it."""
    elsewhere = branches_in_other_worktrees(repo_root)
    node_ids = dict.fromkeys(e.get("node_id") for e in reg.get("entries") or [] if e.get("node_id"))

    def held_here(root: Path, branch: str) -> bool:
        # Looked up at call time so a test patching local_branch_exists here is honoured.
        return branch not in elsewhere and local_branch_exists(root, branch)

    claims = own_in_flight_claims(repo_root, reg, list(node_ids), branch_exists=held_here)
    return [c for c in claims if not node_complete_on_ref(repo_root, c.branch, c.node_id)]


def refuse_second_claim(repo_root: Path, *, allow: bool) -> None:
    """Exit 6 naming the held claim(s), unless ``allow`` (``--allow-second-claim``)."""
    if allow:
        return
    claims = held_claims(repo_root, read_registry(registry_path(repo_root)))
    if not claims:
        return
    first = claims[0]
    lines = [
        f"error: this checkout already holds a claim on {first.node_id} ({first.branch}); "
        "pickup would register a second leaf here."
    ]
    if claims[1:]:
        lines.append(f"  also claimed here: {', '.join(c.node_id for c in claims[1:])}")
    lines.append(
        "  Finish it (specy-road finish-this-task) or release it "
        "(specy-road abort-task-pickup), then re-run; or pass --allow-second-claim "
        "to claim another leaf anyway."
    )
    print("\n".join(lines), file=sys.stderr)
    raise SystemExit(EXIT_IN_FLIGHT)


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
