"""Pickup-time helpers for do_next_task: brief, register, finalize, prompt.

These are the steps that run after the leaf has been chosen and before the
PM-facing footer is printed. Kept separate to keep do_next_task.py under the
file-line constraint.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from do_next_prompt import write_agent_prompt
from do_next_task_self_heal import (
    attempt_self_cleanup,
    emit_stale_claim_warning,
)
from generate_brief import index as make_index, render_brief
from specy_road.on_complete_session import (
    on_complete_session_path,
    write_on_complete_session,
)


def write_brief(work_dir: Path, node: dict, nodes: list[dict]) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    node_id = node["id"]
    path = work_dir / f"brief-{node_id}.md"
    path.write_text(render_brief(node_id, make_index(nodes)), encoding="utf-8")
    return path


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
    with registry_path.open("w", encoding="utf-8") as f:
        yaml.dump(reg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    git_runner("add", str(registry_path))
    git_runner("commit", "-m", commit_message)


def push_and_branch_with_self_heal(
    *,
    repo_root: Path,
    registry_path: Path,
    git_runner,
    push_integration_branch_fn,
    checkout_new_branch_fn,
    push_registry: bool,
    base: str,
    remote: str,
    branch: str,
    node_id: str,
    codename: str,
) -> None:
    """F-014: push integration, create feature branch; self-heal on failure."""
    branch_created = False
    try:
        if push_registry:
            print(f"-> git push {remote} {base}")
            push_integration_branch_fn(remote, base)
        checkout_new_branch_fn(branch)
        branch_created = True
    except BaseException:
        if not branch_created:
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
