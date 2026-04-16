#!/usr/bin/env python3
"""Pick the next agentic task, sync integration branch, brief, register on trunk, branch, prompt."""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

import yaml
from do_next_available import _available, _load_branch_enrichment
from do_next_prompt import write_agent_prompt
from do_next_task_interactive import pick_interactive as _pick_interactive
from generate_brief import index as make_index, render_brief
from registration_pickup_commit import registration_commit_message
from roadmap_load import load_roadmap
from specy_road.git_workflow_config import (
    merge_request_requires_manual_approval,
    resolve_integration_defaults,
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
            f"  Run with sync enabled, or: git checkout {base}",
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


def _register_and_commit(node: dict, branch: str, reg: dict, commit_message: str) -> None:
    codename = node["codename"]
    _validate_touch_zones(node)
    reg.setdefault("entries", []).append({
        "codename": codename,
        "node_id": node["id"],
        "branch": branch,
        "touch_zones": list(node.get("touch_zones") or []),
        "started": datetime.date.today().isoformat(),
    })
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


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Pick the next agentic task: sync integration branch, write brief, "
            "register on integration branch, create feature/rm-*, write prompt."
        ),
    )
    p.add_argument(
        "--base",
        default=None,
        metavar="BRANCH",
        help=(
            "Integration branch to sync before registering and branching "
            "(default: roadmap/git-workflow.yaml, else main)."
        ),
    )
    p.add_argument(
        "--remote",
        default=None,
        metavar="NAME",
        help=(
            "Git remote to fetch and merge from "
            "(default: roadmap/git-workflow.yaml, else origin)."
        ),
    )
    p.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip fetch/checkout/ff-merge of the integration branch (offline/CI).",
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Choose a task from a numbered list instead of auto-picking the first.",
    )
    p.add_argument(
        "--no-push-registry",
        action="store_true",
        help=(
            "Skip git push after registering on the integration branch "
            "(offline/CI; default is to push so others see the claim)."
        ),
    )
    p.add_argument(
        "--push-registry",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--no-ci-skip-in-message",
        action="store_true",
        help=(
            "Omit CI skip tokens from the registration commit message "
            "(default appends common [skip ci] / [ci skip] / ***NO_CI*** markers)."
        ),
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    return p.parse_args(argv)


def _print_pickup_footer(
    *,
    brief_path: Path,
    prompt_path: Path,
    push_registry: bool,
    remote: str,
    base: str,
    mr_manual: bool,
) -> None:
    print(f"brief:  {brief_path.relative_to(ROOT)}")
    print(f"prompt: {prompt_path.relative_to(ROOT)}")
    print()
    if not push_registry:
        print("Push the integration branch so PMs see the registry update:")
        print(f"  git push {remote} {base}")
        print()
    if mr_manual:
        print(
            "Merge requests require manual approval in this repo "
            "(roadmap/git-workflow.yaml). Open the MR after push and wait for review.",
        )
        print()
    print("-" * 60)
    print(f"Open {prompt_path.relative_to(ROOT)} in your agent to begin.")
    print("When done: specy-road finish-this-task")
    print("-" * 60)


def _finalize_pickup(
    node: dict,
    nodes: list[dict],
    branch: str,
    *,
    base: str,
    remote: str,
    push_registry: bool,
    include_ci_skip: bool,
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
    _register_and_commit(node, branch, reg, commit_msg)
    print("registered in roadmap/registry.yaml on integration branch (committed)")

    if push_registry:
        print(f"-> git push {remote} {base}")
        _push_integration_branch(remote, base)

    _checkout_new_branch(branch)
    prompt_path = write_agent_prompt(
        node,
        nodes,
        brief_path,
        repo_root=ROOT,
        work_dir=WORK_DIR,
    )
    mr_manual = merge_request_requires_manual_approval(ROOT)
    _print_pickup_footer(
        brief_path=brief_path,
        prompt_path=prompt_path,
        push_registry=push_registry,
        remote=remote,
        base=base,
        mr_manual=mr_manual,
    )


def main(argv: list[str] | None = None) -> None:
    global ROOT, REGISTRY_PATH, WORK_DIR
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    push_registry = not args.no_push_registry
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
        print(
            "No available agentic tasks — none pass execution gates with met dependencies, "
            "all are claimed or skipped (complete/in-progress/cancelled), "
            "or the unblock/retry queue is empty.",
        )
        raise SystemExit(0)

    if not args.no_sync:
        _sync_integration_branch(base, remote)
        reg = _load_registry()
        nodes = load_roadmap(ROOT)["nodes"]
        enrich = _load_branch_enrichment(ROOT)
        available = _available(nodes, reg, enrich)
        if not available:
            print(
                "No available agentic tasks after sync — another teammate may have "
                "claimed work, or the graph changed on the integration branch.",
            )
            raise SystemExit(0)
    else:
        _assert_working_tree_clean()

    _assert_current_branch_equals(base)

    node = _pick_interactive(available, nodes) if args.interactive else available[0]
    branch = f"feature/rm-{node['codename']}"
    _finalize_pickup(
        node,
        nodes,
        branch,
        base=base,
        remote=remote,
        push_registry=push_registry,
        include_ci_skip=include_ci_skip,
    )


if __name__ == "__main__":
    main()
