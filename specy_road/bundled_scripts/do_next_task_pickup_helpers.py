"""Pickup-time helpers for do_next_task: brief, register, finalize, prompt.

These are the steps that run after the leaf has been chosen and before the
PM-facing footer is printed. Kept separate to keep do_next_task.py under the
file-line constraint.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from specy_road.bundled_scripts.do_next_prompt import write_agent_prompt
from specy_road.bundled_scripts.do_next_task_self_heal import (
    attempt_self_cleanup,
    emit_stale_claim_warning,
)
from specy_road.bundled_scripts.generate_brief import index as make_index, render_brief
from specy_road.git_subprocess import commits_behind, local_branch_exists
from specy_road.on_complete_session import (
    on_complete_session_path,
    write_on_complete_session,
)
from specy_road.registry_yaml import write_registry


def write_brief(work_dir: Path, node: dict, nodes: list[dict]) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    node_id = node["id"]
    path = work_dir / f"brief-{node_id}.md"
    path.write_text(render_brief(node_id, make_index(nodes)), encoding="utf-8")
    return path


def assert_not_already_claimed(reg: dict, node: dict) -> None:
    """Refuse to write a second row for a node or codename already registered.

    Selection filters claimed nodes by ``node_id`` while every release path —
    finish, abort, self-heal — removes rows by ``codename``. Checking both here
    means the two spellings cannot drift into a registry holding one node twice,
    which reads as two lanes owning the same leaf.
    """
    node_id = node.get("id")
    codename = node.get("codename")
    for entry in reg.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("node_id") == node_id:
            field, value = "node_id", node_id
        elif entry.get("codename") == codename:
            field, value = "codename", codename
        else:
            continue
        raise SystemExit(
            f"error: roadmap/registry.yaml already has a row with {field} "
            f"{value!r} (branch {entry.get('branch') or '?'}). Registering "
            "again would claim one leaf twice.\n"
            "  If that claim is yours and finished, land its branch.\n"
            "  If it is stale, remove the row, commit and push the integration "
            "branch, then retry."
        )


def register_and_commit(
    *,
    registry_path: Path,
    git_runner,
    node: dict,
    branch: str,
    reg: dict,
    commit_message: str,
    impl_review_gate: bool,
) -> None:
    """Append a registry entry and commit the registry file.

    F-009: touch_zones are optional; the brief / agent prompt instructs the
    coding agent to discover them via codebase scan when missing.
    """
    assert_not_already_claimed(reg, node)
    codename = node["codename"]
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
    write_registry(registry_path, reg)
    git_runner("add", str(registry_path))
    git_runner("commit", "-m", commit_message)


def announce_resumed_branch(repo_root: Path, branch: str, base: str) -> None:
    """Say plainly that this pickup adopted a branch rather than creating one."""
    print(f"branch {branch} already exists — checking it out instead of creating it")
    behind = commits_behind(repo_root, branch, base)
    if behind:
        print(
            f"  note: it is {behind} commit(s) behind {base}; "
            f"`git merge {base}` before implementing if that matters."
        )


def push_and_branch_with_self_heal(
    *,
    repo_root: Path,
    registry_path: Path,
    git_runner,
    push_integration_branch_fn,
    checkout_new_branch_fn,
    checkout_existing_branch_fn,
    push_registry: bool,
    base: str,
    remote: str,
    branch: str,
    node_id: str,
    codename: str,
    branch_exists=None,
) -> None:
    """F-014: push integration, then reach the feature branch; roll back on failure.

    An **existing** feature branch is checked out rather than created, and that
    is the opposite of the previous behaviour rather than a refinement of it.
    ``git checkout -b`` failing with "a branch named … already exists" used to
    raise into the rollback path, which strips the claim this pickup just
    registered — so the node became available again, the branch was still there,
    and the next pickup failed the same way. The loop had no exit.

    The branch survives its claim whenever a claim is released without deleting
    it: a crashed finish, a hand-edited registry, an interrupted run. In each of
    those the branch is the work, and the claim is the thing that went missing.

    Rollback is unchanged for every other failure. A push that fails, or a
    checkout blocked by a dirty tree, still means the pickup did not complete,
    and leaving the claim behind would strand the node.
    """
    branch_ready = False
    resuming = (branch_exists or local_branch_exists)(repo_root, branch)
    try:
        if push_registry:
            print(f"-> git push {remote} {base}")
            push_integration_branch_fn(remote, base)
        if resuming:
            announce_resumed_branch(repo_root, branch, base)
            checkout_existing_branch_fn(branch)
        else:
            checkout_new_branch_fn(branch)
        branch_ready = True
    except BaseException:
        if not branch_ready:
            ok = attempt_self_cleanup(
                repo_root=repo_root,
                registry_path=registry_path,
                node_id=node_id,
                codename=codename,
                base=base,
                remote=remote,
                git_runner=git_runner,
            )
            if not ok:
                emit_stale_claim_warning(node_id, codename)
        raise


def write_session_and_prompt(
    *,
    work_dir: Path,
    repo_root: Path,
    node: dict,
    nodes: list[dict],
    brief_path: Path,
    on_complete: str,
    write_agent_prompt_fn=write_agent_prompt,
) -> Path:
    node_id = node["id"]
    sess_path = on_complete_session_path(work_dir, node_id)
    write_on_complete_session(
        sess_path,
        node_id=node_id,
        codename=node["codename"],
        on_complete=on_complete,
    )
    return write_agent_prompt_fn(
        node, nodes, brief_path,
        repo_root=repo_root, work_dir=work_dir, on_complete=on_complete,
    )
