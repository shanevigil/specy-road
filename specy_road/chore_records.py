"""Chore records: the library half of ``chore start|close``.

A chore is ``work/chores/<slug>.json`` in the main checkout. Worker launch,
reconcile, message and review read that record. They import it here so they
do not import the ``chore`` command entry point.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import head_sha
from specy_road.review_files import reviews_dir, reviews_root
from specy_road.review_target import ReviewTarget
from specy_road.orchestration.workers.worker_state import WorkerError

# Lower case, so never a node id (``M1.2``); not ``w-``, which names a worker id where a target is either.
_SLUG = re.compile(r"^(?!w-)[a-z0-9][a-z0-9-]*$")


def chores_dir(repo_root: Path) -> Path:
    return reviews_root(repo_root).parent / "chores"   # the main checkout's work/, as work/.workers is


def load_chore(repo_root: Path, slug: str) -> dict[str, Any] | None:
    """The chore ``slug``, open or closed; ``None`` when ``slug`` is not one (a node id)."""
    path = chores_dir(repo_root) / f"{slug}.json"
    if not _SLUG.match(slug) or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def open_chore(repo_root: Path, slug: str) -> dict[str, Any] | None:
    """As :func:`load_chore`, refusing a closed chore: no worker turn may start on it."""
    chore = load_chore(repo_root, slug)
    if chore and chore.get("closed_at"):
        raise WorkerError(f"chore {slug} was closed at {chore['closed_at']}; start a new chore instead")
    return chore


def chore_node(chore: dict[str, Any]) -> dict[str, Any]:
    """The node-shaped view of a chore that eligibility checks and review records read: its task is A1."""
    return {"id": chore["slug"], "codename": chore["slug"], "title": chore["task"], "acceptance": [chore["task"]],
            "touch_zones": list(chore["touch_zones"]), "chore": chore}


def chore_target(repo_root: Path, chore: dict[str, Any]) -> ReviewTarget:
    """What reconcile and review judge: the chore's worktree head against the head it was started at."""
    node = chore_node(chore)
    entry = {"node_id": chore["slug"], "branch": chore["branch"], "touch_zones": list(chore["touch_zones"])}
    return ReviewTarget(node, [node], entry, chore["branch"], head_sha(Path(chore["worktree"])), None, chore["base"])


def chore_prompt(chore: dict[str, Any], role: str, model: str, repo_root: Path, commit: str | None = None) -> str:
    """The executor's or reviewer's prompt. The executor's names nothing that moves, so its hash is its contract."""
    zones = "\n".join(f"- `{z}`" for z in chore["touch_zones"])
    head = [f"# Chore `{chore['slug']}` ({role}) for `{model}`", "", f"base: {chore['base']}", "",
            "A chore is work outside the roadmap: there is no roadmap node, brief, claim or registry row.", "",
            "## Task", "", chore["task"], "", "## Touch zones", "", zones, ""]
    if role == "executor":
        return "\n".join(head + [
            "## Rules", "",
            f"1. Work in `{chore['worktree']}` on branch `{chore['branch']}`. Change only paths inside the touch "
            "zones; `specy-road worker reconcile` flags anything outside them.",
            "2. Commit by explicit path (`git commit --only <paths>`), never `-A`, `-a` or a bare `git commit`.",
            "3. Do not edit the roadmap or the registry, claim a leaf, push or merge.",
            "4. End with a short summary of what you changed and how you checked it, then stop.", ""])
    dest = reviews_dir(repo_root, chore["slug"]) / f"REVIEW-{model}.md"
    return "\n".join(head + [
        "## Review", "",
        f"In `{chore['worktree']}`, read `git diff {chore['base']}..{commit}` and judge it against the task and the "
        "touch zones. Edit nothing in the worktree. Write your verdict to", "", f"`{dest}`", "",
        "in exactly this form (`block` with `required_changes` when the task is not done or a path is outside "
        "the zones), then stop:", "",
        "```", "---", f"node_id: {chore['slug']}", f"model: {model}", "date: 'YYYY-MM-DD'", "verdict: approve",
        f"commit: '{commit}'", "acceptance: {A1: pass}",
        "findings: {correctness: [], regression: [], boundary: [], test_integrity: []}",
        "fresh_session: true", "authored_fix: false", "is_coordinator: false", "---", "",
        "Your notes.", "```", ""])
