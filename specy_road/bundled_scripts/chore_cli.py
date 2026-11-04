#!/usr/bin/env python3
"""CLI for ``specy-road chore start|close`` (``docs/orchestration-chores.md``): work outside the roadmap.

A chore is ``work/chores/<slug>.json`` in the main checkout: no roadmap node,
branch or registry row. It runs in the checkout it was started from (or
``--worktree``), on the branch checked out there, and declares touch zones as a
leaf does. ``worker delegate``, ``message``, ``resume``, ``sync``, ``usage``,
``reconcile`` and ``review delegate`` take the slug where they take a node id;
its model may be off the roster when ``--harness`` names where it runs.
``chore close`` writes ``work/chores/<slug>.md``: the summary, the workers'
usage, and each reviewer's verdict, or ``unreviewed``. Exit codes: 0 done, 1 refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text, head_sha
from specy_road.review_files import list_reviews, reviews_dir, reviews_root
from specy_road.review_target import ReviewTarget
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_state import HARNESSES, WorkerError, _now, _write_atomic, events_since, list_records

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


def _save(repo_root: Path, chore: dict[str, Any]) -> None:
    chores_dir(repo_root).mkdir(parents=True, exist_ok=True)
    _write_atomic(chores_dir(repo_root) / f"{chore['slug']}.json", json.dumps(chore, indent=2) + "\n")


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


def start(repo_root: Path, slug: str, *, task: str, zones: list[str], review: bool = False,
          model: str | None = None, harness: str | None = None, worktree: Path | None = None) -> dict[str, Any]:
    if not _SLUG.match(slug):
        raise WorkerError(f"{slug!r} is not a chore slug: lower-case letters, digits and '-', not starting with 'w-'")
    if (chores_dir(repo_root) / f"{slug}.json").exists():
        raise WorkerError(f"chore {slug} already exists under {chores_dir(repo_root)}; pick another slug")
    wt = Path(worktree or git_text(["rev-parse", "--show-toplevel"], repo_root) or repo_root).resolve()
    top = git_text(["rev-parse", "--show-toplevel"], wt) if wt.is_dir() else None
    if not top or Path(top).resolve() != wt:
        raise WorkerError(f"{wt} is not a git worktree root")
    branch = git_text(["branch", "--show-current"], wt)
    if not branch:
        raise WorkerError(f"{wt} has a detached HEAD; check out a branch for the chore to run on")
    chore = {"slug": slug, "task": task, "touch_zones": zones, "review": review, "model": model, "harness": harness,
             "worktree": str(wt), "branch": branch, "base": head_sha(wt), "started_at": _now(), "closed_at": None}
    _save(repo_root, chore)
    return chore


def _verdicts(repo_root: Path, chore: dict[str, Any]) -> list[str]:
    if not chore["review"]:
        return ["unreviewed (no review was run)"]
    recs = [r for r in list_reviews(repo_root, chore["slug"], ["A1"]) if r.ok]
    return [f"{r.data['model']}: {r.data['verdict']} at {str(r.data['commit'])[:12]}" for r in recs] \
        or ["unreviewed (review requested; no valid review record was filed)"]


def close(repo_root: Path, slug: str, summary: str) -> tuple[Path, dict[str, Any]]:
    """End the chore's idle workers and write its record; a worker still running refuses the close."""
    from specy_road.bundled_scripts.worker_cli_render import usage, usage_lines  # noqa: PLC0415
    from specy_road.worker_orphans import HELD_STATES, end_finished_workers  # noqa: PLC0415 — it imports this module

    chore = open_chore(repo_root, slug)
    if chore is None:
        raise WorkerError(f"no chore {slug} under {chores_dir(repo_root)}")
    recs = [r for r in list_records(repo_root) if r.node_id == slug]
    running = [r.worker_id for r in recs if r.active and r.state not in HELD_STATES]
    if running:
        raise WorkerError(f"chore {slug} has a running worker ({', '.join(running)}); wait for it or terminate it")
    end_finished_workers(repo_root, slug)
    used = usage_lines(usage([(r, [e.to_dict() for e in events_since(repo_root, r.worker_id)]) for r in recs])) \
        if recs else ["no workers ran"]
    chore.update(closed_at=_now(), summary=summary, head=head_sha(Path(chore["worktree"])),
                 verdicts=_verdicts(repo_root, chore))
    lines = [f"# Chore `{slug}`", "", f"- Task: {chore['task']}", f"- Worktree: `{chore['worktree']}` on "
             f"`{chore['branch']}`, {str(chore['base'])[:12]}..{str(chore['head'])[:12]}",
             f"- Touch zones: {', '.join(f'`{z}`' for z in chore['touch_zones'])}",
             f"- Started {chore['started_at']}, closed {chore['closed_at']}", "", "## Summary", "", summary, "",
             "## Usage", "", *(f"    {line}" for line in used), "", "## Review", "", *(f"- {v}" for v in chore["verdicts"]), ""]
    path = chores_dir(repo_root) / f"{slug}.md"
    _write_atomic(path, "\n".join(lines))
    _save(repo_root, chore)
    return path, chore


def cmd_start(ns: argparse.Namespace) -> int:
    chore = start(resolve_repo_root(ns), ns.slug, task=ns.task, zones=ns.zone, review=ns.review, model=ns.model,
                  harness=ns.harness, worktree=Path(ns.worktree) if ns.worktree else None)
    print(json.dumps(chore, indent=2) if ns.json else
          f"chore {ns.slug}: started on {chore['branch']} in {chore['worktree']} at {chore['base'][:12]}"
          + ("; review requested" if ns.review else "") + f"\nDelegate with `specy-road worker delegate {ns.slug}"
          + ("" if ns.model else " --model ID") + "`.")
    return 0


def cmd_close(ns: argparse.Namespace) -> int:
    path, chore = close(resolve_repo_root(ns), ns.slug, ns.summary)
    print(json.dumps({**chore, "record": str(path)}, indent=2) if ns.json else f"chore {ns.slug}: closed; wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chore", help="Chores: worker-run work outside the roadmap")
    cs = c.add_subparsers(dest="chore_cmd", required=True)
    sp = cs.add_parser("start", help="Create work/chores/<slug>.json: the worker commands then take the slug")
    sp.add_argument("slug")
    sp.add_argument("--task", required=True, help="What the chore is to do (the executor's task, the reviewer's A1)")
    sp.add_argument("--zone", action="append", required=True, metavar="PATH",
                    help="A touch zone (repeatable); worker reconcile flags changes outside them")
    sp.add_argument("--review", action="store_true", help="Allow `review delegate <slug>`; without it close records unreviewed")
    sp.add_argument("--model", help="Default executor model for `worker delegate <slug>`; may be off the roster")
    sp.add_argument("--harness", choices=HARNESSES, help="Where an off-roster model runs")
    sp.add_argument("--worktree", help="Run in this checkout (default: this one)")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_start)
    sp = cs.add_parser("close", help="End idle workers and write work/chores/<slug>.md (summary, usage, verdict)")
    sp.add_argument("slug")
    sp.add_argument("--summary", required=True, help="What was done")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_close)
    return p


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        raise SystemExit(ns.func(ns))
    except WorkerError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
