"""Milestone rollup session file under ``work/.milestone-session.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SESSION_VERSION = 1
MILESTONE_SESSION_BASENAME = ".milestone-session.yaml"


def milestone_session_path(work_dir: Path) -> Path:
    return work_dir / MILESTONE_SESSION_BASENAME


@dataclass(frozen=True)
class MilestoneSession:
    parent_node_id: str
    parent_codename: str
    rollup_branch: str
    integration_branch: str
    remote: str


def rollup_branch_for_codename(parent_codename: str) -> str:
    return f"feature/rm-{parent_codename}"


def write_milestone_session(
    path: Path,
    *,
    parent_node_id: str,
    parent_codename: str,
    integration_branch: str,
    remote: str,
) -> None:
    doc: dict[str, Any] = {
        "version": SESSION_VERSION,
        "parent_node_id": parent_node_id,
        "parent_codename": parent_codename,
        "rollup_branch": rollup_branch_for_codename(parent_codename),
        "integration_branch": integration_branch,
        "remote": remote,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def read_milestone_session(path: Path) -> MilestoneSession | None:
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("version") != SESSION_VERSION:
        return None
    pid = raw.get("parent_node_id")
    pc = raw.get("parent_codename")
    rb = raw.get("rollup_branch")
    ib = raw.get("integration_branch")
    rem = raw.get("remote")
    if not all(
        isinstance(x, str) and x.strip()
        for x in (pid, pc, rb, ib, rem)
    ):
        return None
    if rb != rollup_branch_for_codename(pc):
        return None
    return MilestoneSession(
        parent_node_id=pid.strip(),
        parent_codename=pc.strip(),
        rollup_branch=rb.strip(),
        integration_branch=ib.strip(),
        remote=rem.strip(),
    )


def remove_milestone_session(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
