"""``specy-road review usage``: tokens and cost of each delegated reviewer run, and the node's reviewer total.

``review delegate`` keeps each round: before a run replaces ``RUN-<model>.json``, :func:`archive_round` copies
it into ``history/`` as ``RUN-<model>-<commit12>-<n>.json`` and moves its ``.log`` beside it (the log is
appended per attempt, so the current one then holds only the current round), and moves ``notes-<model>.md``
to ``history/notes/notes-<model>-<commit12>-<n>.md`` when that run left notes behind. Notes go one level down because ``history/*.md`` is
read as filed review records, and a reviewer drafts its record in its notes.

Usage is read from each run's log with the harness adapter's own parser, the one ``worker`` events use, and
running session totals become per-turn figures with :func:`turn_usage`, as ``worker usage`` does. A figure no
turn reported stays ``None`` (``?``), never 0. Only RUN records whose ``source`` is ``review-delegate`` are
counted; ``prompt-cli`` and other RUN files are ignored (A3).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.worker_cli_render import _sum_usage
from specy_road.review_files import HISTORY_DIRNAME, reviews_dir
from specy_road.reviewer_run_failure import _read_json
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapter_base import Launch
from specy_road.worker_adapter_parsers import USAGE_FIELDS, usage_text
from specy_road.worker_adapters import adapter_for
from specy_road.worker_state import WorkerEvent
from specy_road.worker_usage_delta import turn_usage

NOTES_DIRNAME = "notes"
DELEGATE_SOURCE = "review-delegate"
_ROUND = re.compile(r"-(\d+)\.json$")


def is_delegate_run(record: dict[str, Any]) -> bool:
    """True when the RUN record was opened by ``review delegate`` (A3)."""
    return record.get("source") == DELEGATE_SOURCE


def _round_of(p: Path) -> int:
    m = _ROUND.search(p.name)
    return int(m.group(1)) if m else 0


def _history_runs(hist: Path, model: str | None = None, *, delegate_only: bool = False) -> list[tuple[Path, dict[str, Any]]]:
    """Archived RUN records (of ``model``, when given); the model is read from the record, not the name."""
    out = []
    for p in sorted(hist.glob("RUN-*.json")) if hist.is_dir() else []:
        r = _read_json(p) or {}
        if delegate_only and not is_delegate_run(r):
            continue
        if model is None or r.get("model") == model:
            out.append((p, r))
    return out


def _clear_nondelegate_artifacts(d: Path, model: str) -> None:
    """Remove log and notes left by a non-delegate RUN so the next ``review delegate`` appends to a fresh log."""
    log = d / f"RUN-{model}.log"
    if log.is_file():
        log.unlink()
    notes = d / f"notes-{model}.md"
    if notes.is_file():
        notes.unlink()


def archive_round(repo_root: Path, node_id: str, model: str) -> Path | None:
    """Keep the previous round's RUN json, log and notes under ``history/``; returns the archived json."""
    d = reviews_dir(repo_root, node_id)
    cur = d / f"RUN-{model}.json"
    if not cur.is_file():
        return None
    cur_run = _read_json(cur) or {}
    if not is_delegate_run(cur_run):
        _clear_nondelegate_artifacts(d, model)
        return None
    hist = d / HISTORY_DIRNAME
    hist.mkdir(parents=True, exist_ok=True)
    commit = re.sub(r"[^0-9A-Za-z]", "", str(cur_run.get("commit") or ""))[:12] or "unknown"
    n = 1 + max((_round_of(p) for p, _r in _history_runs(hist, model, delegate_only=True)), default=0)
    stem = f"RUN-{model}-{commit}-{n}"
    shutil.copy2(cur, hist / f"{stem}.json")
    log = cur.with_suffix(".log")
    if log.is_file():
        log.replace(hist / f"{stem}.log")   # moved: the next round appends to a fresh log
    notes = d / f"notes-{model}.md"
    if notes.is_file():
        (hist / NOTES_DIRNAME).mkdir(exist_ok=True)
        notes.replace(hist / NOTES_DIRNAME / f"notes-{model}-{commit}-{n}.md")
    return hist / f"{stem}.json"


def _log_turns(harness: str, log: Path, events: list[WorkerEvent]) -> list[dict[str, Any]]:
    """Each turn's usage in ``log``; ``events`` carries a resumed session's earlier totals and is extended."""
    if not log.is_file():
        return []
    adapter, launch, turns = adapter_for(harness), Launch(argv=[]), []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        for p in adapter.parse_events(line, launch):
            if p.usage is None:
                continue
            detail = turn_usage({**dict.fromkeys(USAGE_FIELDS), **p.usage}, events)
            events.append(WorkerEvent(len(events) + 1, "", "", "usage", "worker", "worker_suggestion", "", 0, detail))
            turns.append(detail)
    return turns


def review_usage(repo_root: Path, node_id: str) -> dict[str, Any]:
    """``{"node_id", "runs": [...], "total"}`` over every delegated reviewer run, current and archived."""
    d = reviews_dir(repo_root, node_id)
    runs = [(p, r, _round_of(p)) for p, r in _history_runs(d / HISTORY_DIRNAME, delegate_only=True)]
    last = {}
    for _p, r, n in runs:
        last[r.get("model")] = max(n, last.get(r.get("model"), 0))
    for p in sorted(d.glob("RUN-*.json")) if d.is_dir() else []:
        r = _read_json(p) or {}
        if not is_delegate_run(r):
            continue
        runs.append((p, r, last.get(r.get("model"), 0) + 1))
    rows, sessions = [], {}
    for p, r, n in sorted(runs, key=lambda x: (str(x[1].get("model")), x[2])):
        model = r.get("model") or p.stem.removeprefix("RUN-")
        events = sessions.get(model, []) if r.get("resumed") else []   # a resumed session's totals run on
        sessions[model] = events
        turns = _log_turns(str(r.get("harness") or "generic"), p.with_suffix(".log"), events)
        rows.append({"model": model, "harness": r.get("harness"), "round": n, "commit": r.get("commit"),
                     "state": r.get("state"), "file": str(p.relative_to(d)), "turns": len(turns),
                     **_sum_usage(turns)})
    return {"node_id": node_id, "runs": rows,
            "total": {"runs": len(rows), "turns": sum(r["turns"] for r in rows), **_sum_usage(rows)}}


def review_usage_lines(data: dict[str, Any]) -> list[str]:
    lines = [f"{data['node_id']} review usage ({len(data['runs'])} run(s); ? = not reported)"]
    for r in data["runs"]:
        lines.append(f"  {r['model']} round {r['round']} at {str(r['commit'] or '?')[:12]} ({r['state'] or '?'}), "
                     f"{r['turns']} turn(s): {usage_text(r)}")
    t = data["total"]
    lines.append(f"  total, {t['turns']} turn(s): {usage_text(t)}")
    return lines


def cmd_review_usage(ns: argparse.Namespace) -> int:
    data = review_usage(resolve_repo_root(ns), ns.node_id)
    print(json.dumps(data, indent=2) if ns.json else "\n".join(review_usage_lines(data)))
    return 0


def add_parser(rsub: Any) -> None:
    """``review usage`` under ``review_cli``'s ``review`` subcommands."""
    sp = rsub.add_parser("usage", help="Tokens and cost per delegated reviewer run, and their total")
    sp.add_argument("node_id")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_review_usage)
