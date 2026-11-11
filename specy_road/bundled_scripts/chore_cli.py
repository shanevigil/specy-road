#!/usr/bin/env python3
"""CLI for ``specy-road chore start|close|garden`` (``docs/orchestration-chores.md``): work outside the roadmap.

A chore is ``work/chores/<slug>.json`` in the main checkout: no roadmap node,
branch or registry row. It runs in the checkout it was started from (or
``--worktree``), on the branch checked out there, and declares touch zones as a
leaf does. ``worker delegate``, ``message``, ``resume``, ``sync``, ``usage``,
``reconcile`` and ``review delegate`` take the slug where they take a node id;
its model may be off the roster when ``--harness`` names where it runs.
``chore close`` writes ``work/chores/<slug>.md``: the summary, the workers'
usage, and each reviewer's verdict, or ``unreviewed``. ``chore garden`` (``chore_garden.py``)
reports drift and may file it as roadmap leaves. Exit codes: 0 done, 1 refused.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from specy_road.cli_args import add_json_arg, add_model_arg
from specy_road.bundled_scripts.chore_garden import as_json, garden
from specy_road.chore_records import (
    _SLUG,
    chore_node,
    chore_prompt,
    chore_target,
    chores_dir,
    load_chore,
    open_chore,
)
from specy_road.clock import utc_now_iso
from specy_road.fs_atomic import atomic_write_text
from specy_road.finish_implementation_check import _clean
from specy_road.git_subprocess import current_branch_name, git_root, head_sha, is_worktree_root
from specy_road.review_files import list_reviews
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_cli_render import usage, usage_lines
from specy_road.worker_orphans import HELD_STATES, end_finished_workers
from specy_road.worker_state import HARNESSES, WorkerError, events_since, list_records


def _save(repo_root: Path, chore: dict[str, Any]) -> None:
    chores_dir(repo_root).mkdir(parents=True, exist_ok=True)
    atomic_write_text(chores_dir(repo_root) / f"{chore['slug']}.json", json.dumps(chore, indent=2) + "\n")


def start(repo_root: Path, slug: str, *, task: str, zones: list[str], review: bool = False,
          model: str | None = None, harness: str | None = None, worktree: Path | None = None) -> dict[str, Any]:
    if not _SLUG.match(slug):
        raise WorkerError(f"{slug!r} is not a chore slug: lower-case letters, digits and '-', not starting with 'w-'")
    if not zones or any(_clean(z) is None for z in zones):   # reconcile drops these, and no zones means unguarded
        raise WorkerError(f"every --zone must name a path; got {zones!r}")
    if (chores_dir(repo_root) / f"{slug}.json").exists():
        raise WorkerError(f"chore {slug} already exists under {chores_dir(repo_root)}; pick another slug")
    wt = Path(worktree or git_root(repo_root) or repo_root).resolve()
    if not is_worktree_root(wt):
        raise WorkerError(f"{wt} is not a git worktree root")
    branch = current_branch_name(wt, is_worktree=True)
    if not branch:
        raise WorkerError(f"{wt} has a detached HEAD; check out a branch for the chore to run on")
    chore = {"slug": slug, "task": task, "touch_zones": zones, "review": review, "model": model, "harness": harness,
             "worktree": str(wt), "branch": branch, "base": head_sha(wt), "started_at": utc_now_iso(), "closed_at": None}
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
    chore.update(closed_at=utc_now_iso(), summary=summary, head=head_sha(Path(chore["worktree"])),
                 verdicts=_verdicts(repo_root, chore))
    lines = [f"# Chore `{slug}`", "", f"- Task: {chore['task']}", f"- Worktree: `{chore['worktree']}` on "
             f"`{chore['branch']}`, {str(chore['base'])[:12]}..{str(chore['head'])[:12]}",
             f"- Touch zones: {', '.join(f'`{z}`' for z in chore['touch_zones'])}",
             f"- Started {chore['started_at']}, closed {chore['closed_at']}", "", "## Summary", "", summary, "",
             "## Usage", "", *(f"    {line}" for line in used), "", "## Review", "", *(f"- {v}" for v in chore["verdicts"]), ""]
    path = chores_dir(repo_root) / f"{slug}.md"
    atomic_write_text(path, "\n".join(lines))
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


def cmd_garden(ns: argparse.Namespace) -> int:
    if ns.open_chores and not ns.under:
        raise WorkerError("--open-chores needs --under <PARENT>: the node the chore leaves are added under")
    report = garden(resolve_repo_root(ns), ns.under if ns.open_chores else None)
    if ns.json:
        print(as_json(report))
        return 0
    for f in report["findings"]:
        print(f.text())
    for line in report["notes"]:
        print(f"garden: {line}", file=sys.stderr)
    for line in report["chores"]:
        print(f"garden: {line}")
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
    add_model_arg(sp, help="Default executor model for `worker delegate <slug>`; may be off the roster")
    sp.add_argument("--harness", choices=HARNESSES, help="Where an off-roster model runs")
    sp.add_argument("--worktree", help="Run in this checkout (default: this one)")
    add_json_arg(sp)
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_start)
    sp = cs.add_parser("close", help="End idle workers and write work/chores/<slug>.md (summary, usage, verdict)")
    sp.add_argument("slug")
    sp.add_argument("--summary", required=True, help="What was done")
    add_json_arg(sp)
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_close)
    sp = cs.add_parser("garden", help="Read-only drift scans, one finding per line; --open-chores files them as leaves")
    sp.add_argument("--open-chores", action="store_true",
                    help="Add one leaf per finding class through the add-node write; none while one is still open")
    sp.add_argument("--under", metavar="PARENT", help="The node --open-chores adds its leaves under (required with it)")
    add_json_arg(sp)
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_garden)
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
