"""Reviewer runs that end without a counted record: failure events and handoff visibility."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.review_files import list_reviews, reviews_dir
from specy_road.review_target import ReviewTarget, same_commit

RUN_PREFIX = "RUN-"
CAPACITY = re.compile(r"rate[ _-]?limit|usage limit|\b429\b|\b529\b|overloaded|capacity|too many requests"
                      r"|quota|resource[ _-]?exhausted", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_path(repo_root: Path, node_id: str, model: str) -> Path:
    return reviews_dir(repo_root, node_id) / f"{RUN_PREFIX}{model}.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save(path: Path, run: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def capacity_error(texts: list[str]) -> str | None:
    """The first of ``texts`` that reads as a capacity or rate-limit error, else ``None``."""
    return next((t for t in texts if CAPACITY.search(t)), None)


def valid_record(repo_root: Path, t: ReviewTarget, model: str) -> tuple[bool, str]:
    """``(ok, why not)``: is there a valid ``REVIEW-<model>.md`` for the commit under review?"""
    rec = next((r for r in list_reviews(repo_root, t.node["id"], acceptance_ids(t.node))
                if r.path.name == f"REVIEW-{model}.md"), None)
    if rec is None:
        return False, f"no REVIEW-{model}.md was filed"
    if not rec.ok:
        return False, f"{rec.path.name} is invalid: {'; '.join(rec.errors)}"
    if rec.data.get("node_id") != t.node["id"] or not same_commit(repo_root, rec.data["commit"], t.commit):
        return False, f"{rec.path.name} reviews {str(rec.data.get('commit'))[:12]}, not this commit"
    return True, ""


def harness_error_line(*, exit_code: int | None, errors: list[str], tail: list[str],
                       fallback: str = "") -> str:
    """One line from the harness for a reviewer-failure event (capacity, login, exit, …)."""
    if exit_code == 0 and not errors and not fallback:
        return "no review record was filed"
    cap = capacity_error(errors + tail)
    if cap:
        return cap
    if errors:
        return errors[-1][:500]
    for line in reversed(tail):
        if line.strip():
            return line.strip()[:500]
    if fallback:
        return fallback[:500]
    return f"harness exited {exit_code}" if exit_code is not None else "reviewer run failed"


def record_reviewer_failure_event(run: dict[str, Any], error: str) -> None:
    run.setdefault("events", []).append({"type": "reviewer-failure", "at": _now(), "error": error[:500]})


def reviewer_failure_gate_note(runs: list[dict[str, Any]]) -> str:
    """When the gate is not met, name the latest reviewer-failure on the commit under review."""
    for r in runs:
        if not r.get("current") or r.get("state") != "incomplete":
            continue
        failures = [e for e in (r.get("events") or []) if e.get("type") == "reviewer-failure"]
        err = failures[-1]["error"] if failures else (r.get("reason") or "?")
        model = r.get("model") or "?"
        return f"reviewer failure ({model}): {err}"
    return ""


def close_run(repo_root: Path, t: ReviewTarget, model: str, run: dict[str, Any], *,
              exit_code: int | None, errors: list[str], tail: list[str], reason_prefix: str = "") -> None:
    """Set ``complete`` or ``incomplete`` from the review record after the run; record a failure event."""
    ok, why = valid_record(repo_root, t, model)
    if ok:
        run.update(state="complete", reason=None)
        return
    err = harness_error_line(exit_code=exit_code, errors=errors, tail=tail, fallback=why or reason_prefix)
    run.update(state="incomplete", reason="; ".join(x for x in (reason_prefix, why) if x) or err)
    record_reviewer_failure_event(run, err)


def open_reviewer_cli_run(repo_root: Path, t: ReviewTarget, model: str, harness: str) -> Path:
    """Start a ``RUN-<model>.json`` for ``prompt --channel cli`` (reviewer role only)."""
    path = run_path(repo_root, t.node["id"], model)
    run = {"node_id": t.node["id"], "model": model, "harness": harness or "generic", "ref": t.ref,
           "commit": t.commit, "state": "running", "session_id": None, "resumed": False, "source": "prompt-cli",
           "started_at": _now(), "ended_at": None, "attempts": [], "events": [], "reason": None,
           "log": str(path.with_suffix(".log"))}
    _save(path, run)
    return path


def gate_policy_summary(gate: Any, runs: list[dict[str, Any]]) -> str:
    """``handoff status`` policy line, with a reviewer failure beside ``not met`` when one applies."""
    note = reviewer_failure_gate_note(runs)
    base = gate.summary()
    return f"{base} — {note}" if not gate.passed and note else base


def close_reviewer_cli_run(repo_root: Path, t: ReviewTarget, model: str, path: Path, exit_code: int,
                           output_lines: list[str]) -> None:
    """Finish a reviewer ``prompt --channel cli`` run: compare records and file a reviewer-failure when needed."""
    run = _read_json(path) or {}
    log = Path(run.get("log") or path.with_suffix(".log"))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8")
    tail = [ln.strip() for ln in output_lines[-20:] if ln.strip()]
    prefix = f"harness exited {exit_code}" if exit_code != 0 else ""
    run["attempts"] = [{"at": _now(), "exit": exit_code, "capacity": bool(capacity_error(output_lines)),
                        "error": harness_error_line(exit_code=exit_code, errors=[], tail=tail, fallback=prefix)[:300]
                        or None}]
    close_run(repo_root, t, model, run, exit_code=exit_code, errors=[], tail=output_lines, reason_prefix=prefix)
    run["ended_at"] = _now()
    _save(path, run)
