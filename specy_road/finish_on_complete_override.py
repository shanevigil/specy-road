"""Refuse a ``finish-this-task --on-complete`` that changes the configured landing mode.

The context-regression replay (CR9) had agents asked to "finish and clean up"
run ``finish-this-task --on-complete merge --delete-branch`` in a repo whose
committed ``roadmap/git-workflow.yaml`` says ``on_complete: pr``: the leaf
landed on the integration branch without its PR and the branch was deleted.
How work lands is the team's decision, so a flag that changes it needs a
person's explicit choice, spelled ``--override-on-complete``.

``pr`` is never refused: it lands nothing and keeps the branch, and it is the
fallback a failed merge landing names.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from specy_road.git_workflow_config import (
    DEFAULT_ON_COMPLETE,
    ON_COMPLETE_MODES,
    load_git_workflow_config,
)
from specy_road.on_complete_session import (
    on_complete_session_path,
    read_on_complete_session,
)
from specy_road.registry_yaml import read_registry, registry_path

OVERRIDE_FLAG = "--override-on-complete"


def configured_on_complete(repo_root: Path, *, session: str | None) -> tuple[str, str]:
    """``(mode, source)`` finish-this-task uses when no ``--on-complete`` is passed."""
    if session in ON_COMPLETE_MODES:
        return session, "the pickup's work/.on-complete-<NODE_ID>.yaml"
    env = os.environ.get("SPECY_ROAD_ON_COMPLETE", "").strip()
    if env in ON_COMPLETE_MODES:
        return env, "SPECY_ROAD_ON_COMPLETE"
    data, err = load_git_workflow_config(repo_root)
    value = (data or {}).get("on_complete") if not err else None
    if isinstance(value, str) and value in ON_COMPLETE_MODES:
        return value, "roadmap/git-workflow.yaml"
    return DEFAULT_ON_COMPLETE, "the default (roadmap/git-workflow.yaml sets no on_complete)"


def session_for_branch(repo_root: Path, branch: str) -> str | None:
    """The pickup's per-task ``on_complete`` for ``feature/rm-<codename>``, if any."""
    codename = branch.removeprefix("feature/rm-")
    entries = read_registry(registry_path(repo_root)).get("entries") or []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("codename") == codename:
            node_id = str(entry.get("node_id") or "")
            if not node_id:
                return None
            path = on_complete_session_path(repo_root / "work", node_id)
            return read_on_complete_session(path, node_id=node_id, codename=codename)
    return None


def needs_override(repo_root: Path, mode: str, *, session: str | None = None) -> bool:
    """True when ``--on-complete <mode>`` would need :data:`OVERRIDE_FLAG`."""
    return mode != "pr" and mode != configured_on_complete(repo_root, session=session)[0]


def on_complete_override_or_exit(
    repo_root: Path,
    *,
    cli: str | None,
    branch: str,
    acknowledged: bool,
) -> None:
    """Exit 1 when ``cli`` changes the configured mode without the acknowledgement."""
    if not cli or cli == "pr":
        return
    configured, source = configured_on_complete(
        repo_root, session=session_for_branch(repo_root, branch),
    )
    if cli == configured:
        return
    if acknowledged:
        print(
            f"[warn] --on-complete {cli} overrides on_complete: {configured} "
            f"(from {source}); {OVERRIDE_FLAG} was passed.",
            file=sys.stderr,
        )
        return
    print(
        f"error: this repository finishes with on_complete: {configured} (from {source}); "
        f"--on-complete {cli} would change how this work lands.\n"
        "  How work lands is the team's choice, not the agent's: a person must choose "
        f"the override and pass {OVERRIDE_FLAG} themselves.\n"
        "  Otherwise run finish-this-task without --on-complete"
        + (
            " and leave the branch for its PR (no merge, no --delete-branch)."
            if configured == "pr" else "."
        ),
        file=sys.stderr,
    )
    raise SystemExit(1)
