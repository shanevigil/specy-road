#!/usr/bin/env python3
"""Pick the next actionable leaf, sync integration branch, brief, register on trunk, branch, prompt."""

from __future__ import annotations

import datetime
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
from do_next_prompt import write_agent_prompt
from do_next_task_args import parse_do_next_task_args
from do_next_task_interactive import pick_interactive as _pick_interactive
from do_next_task_leaf_guards import (
    assert_leaf_target as _assert_leaf_target,
    exit_no_actionable_leaves as _exit_no_actionable_leaves,
)
from generate_brief import index as make_index, render_brief
from registration_pickup_commit import registration_commit_message
from roadmap_load import load_roadmap
from do_next_task_virtual_complete import (
    virtual_complete_from_registry as _virtual_complete_from_registry,
)
from specy_road.git_workflow_config import (
    merge_request_requires_manual_approval,
    require_implementation_review_before_finish,
    resolve_integration_defaults,
)
from specy_road.on_complete_pickup import print_pickup_footer, prompt_on_complete
from specy_road.on_complete_session import (
    write_on_complete_session,
    on_complete_session_path,
)
from specy_road.runtime_paths import default_user_repo_root

ROOT = Path.cwd()
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"
WORK_DIR = ROOT / "work"


# ---------------------------------------------------------------------------
# Roadmap queries
# ---------------------------------------------------------------------------


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
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


def _working_tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return not r.stdout.strip()


def _assert_working_tree_clean() -> None:
    if not _working_tree_clean():
        print(
            "error: working tree is not clean (commit, stash, or discard changes first).",
            file=sys.stderr,
        )
        print(
            "  Integration-branch sync and creating a new feature branch need a clean tree.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _assert_current_branch_equals(base: str) -> None:
    cur = _current_branch()
    if cur == "HEAD":
        print(
            "error: detached HEAD — check out the integration branch before picking a task.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if cur != base:
        print(
            f"error: expected integration branch {base!r}, but HEAD is {cur!r}.",
            file=sys.stderr,
        )
        print(
            f"  git checkout {base}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _sync_integration_branch(base: str, remote: str) -> None:
    """
    Fetch, check out the integration branch, and fast-forward to remote.
    Requires a clean working tree.
    """
    _assert_working_tree_clean()
    _git("fetch", remote)
    _git("checkout", base)
    try:
        _git("merge", "--ff-only", f"{remote}/{base}")
    except subprocess.CalledProcessError:
        print(
            f"error: could not fast-forward local '{base}' to {remote}/{base}.",
            file=sys.stderr,
        )
        print(
            "  Resolve your local integration branch (e.g. pull with rebase, or reset "
            "after team agreement), then retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _checkout_new_branch(branch: str) -> None:
    _git("checkout", "-b", branch)


def _validate_touch_zones(node: dict) -> None:
    tz = node.get("touch_zones") or []
    if not tz:
        print(
            f"error: node {node.get('id')!r} has empty touch_zones; "
            "registry requires at least one touch zone.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _register_and_commit(
    node: dict,
    branch: str,
    reg: dict,
    commit_message: str,
    *,
    impl_review_gate: bool,
) -> None:
    codename = node["codename"]
    _validate_touch_zones(node)
    entry: dict = {
        "codename": codename,
        "node_id": node["id"],
        "branch": branch,
        "touch_zones": list(node.get("touch_zones") or []),
        "started": datetime.date.today().isoformat(),
    }
    if impl_review_gate:
        entry["implementation_review"] = "pending"
    reg.setdefault("entries", []).append(entry)
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(reg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _git("add", str(REGISTRY_PATH))
    _git("commit", "-m", commit_message)


def _push_integration_branch(remote: str, base: str) -> None:
    _git("push", remote, base)


# ---------------------------------------------------------------------------
# Brief output
# ---------------------------------------------------------------------------


def _write_brief(node: dict, nodes: list[dict]) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    node_id = node["id"]
    path = WORK_DIR / f"brief-{node_id}.md"
    path.write_text(render_brief(node_id, make_index(nodes)), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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
    print(f"\n[{node_id}] {node.get('title', '')}")
    print(f"implementation branch: {branch}\n")

    brief_path = _write_brief(node, nodes)
    reg = _load_registry()
    commit_msg = registration_commit_message(
        node["codename"],
        include_ci_skip=include_ci_skip,
    )
    _register_and_commit(
        node,
        branch,
        reg,
        commit_msg,
        impl_review_gate=require_implementation_review_before_finish(ROOT),
    )
    print("registered in roadmap/registry.yaml on integration branch (committed)")

    if push_registry:
        print(f"-> git push {remote} {base}")
        _push_integration_branch(remote, base)

    _checkout_new_branch(branch)
    sess_path = on_complete_session_path(WORK_DIR, node_id)
    write_on_complete_session(
        sess_path,
        node_id=node_id,
        codename=node["codename"],
        on_complete=on_complete,
    )
    prompt_path = write_agent_prompt(
        node,
        nodes,
        brief_path,
        repo_root=ROOT,
        work_dir=WORK_DIR,
        on_complete=on_complete,
    )
    mr_manual = merge_request_requires_manual_approval(ROOT)
    impl_gate = require_implementation_review_before_finish(ROOT)
    print_pickup_footer(
        root=ROOT,
        work_dir=WORK_DIR,
        brief_path=brief_path,
        prompt_path=prompt_path,
        push_registry=push_registry,
        remote=remote,
        base=base,
        mr_manual=mr_manual,
        impl_review_gate=impl_gate,
        on_complete=on_complete,
        node_id=node_id,
    )


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

    nodes = load_roadmap(ROOT)["nodes"]
    reg = _load_registry()
    enrich = _load_branch_enrichment(ROOT)
    available = _available(nodes, reg, enrich)

    if not available:
        _exit_no_actionable_leaves(nodes, reg, after_sync=False)

    _sync_integration_branch(base, remote)
    reg = _load_registry()
    nodes = load_roadmap(ROOT)["nodes"]
    enrich = _load_branch_enrichment(ROOT)
    integration_statuses = _statuses_by_node_key(nodes)
    virtual_keys, virtual_logs = _virtual_complete_from_registry(
        reg,
        repo_root=ROOT,
        remote=remote,
    )
    for line in virtual_logs:
        print(line)
    status_overrides = {nk: "complete" for nk in virtual_keys}
    available = _available(
        nodes,
        reg,
        enrich,
        status_overrides=status_overrides or None,
        virtual_complete_keys=virtual_keys or None,
    )
    if not available:
        _exit_no_actionable_leaves(nodes, reg, after_sync=True)

    _assert_current_branch_equals(base)

    if args.interactive:
        blocked = interactive_deps_blocked_entries(
            nodes,
            reg,
            integration_statuses=integration_statuses,
            ready_ids={n["id"] for n in available},
        )
        node = _pick_interactive(available, nodes, blocked_entries=blocked)
    else:
        node = available[0]
    _assert_leaf_target(node, nodes)
    branch = f"feature/rm-{node['codename']}"
    on_complete = prompt_on_complete(ROOT, args.on_complete)
    _finalize_pickup(
        node,
        nodes,
        branch,
        base=base,
        remote=remote,
        push_registry=True,
        include_ci_skip=include_ci_skip,
        on_complete=on_complete,
    )


if __name__ == "__main__":
    main()
