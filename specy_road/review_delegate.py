"""``specy-road review delegate``: run one rostered reviewer on its harness, as ``worker delegate`` runs an executor.

The reviewer prompt is :func:`build_prompt`'s (``prompt --role reviewer``), so
the reviewer keeps the packet-only, edit-nothing rules. The roster entry's
harness runs it through the worker adapters: a ``claude-code`` entry without
``channels.cli`` runs bare (:meth:`ClaudeCode.reviewer_launch`) with a session
id chosen up front, a ``codex`` or ``cursor`` one its adapter's read-only
reviewer command, any other its ``channels.cli``. Unlike a worker, the
command waits for the turn: a reviewer has one job, and its outcome is whether
a valid ``REVIEW-<model>.md`` for the commit under review exists afterwards,
filed by specy-road from the run's final JSON (:func:`file_review`): a run that
wrote anything else is a review failure, one with no valid JSON a rerun request.
A custom command gets its program's structured-output flags (:func:`reviewer_cli`),
and one leaf's reviewer runs take turns (:func:`review_run_lock`).

``work/reviews/<NODE_ID>/RUN-<model>.json`` records the run: the commit it was
for, the native session id (``--resume`` continues that session), each attempt
and the final ``state``, ``complete`` or ``incomplete``. A provider capacity or
rate-limit error is retried with doubling backoff, at most ``--retries`` times.
``handoff status`` and ``review list`` read these files, so a run that left an
older commit's record in place is reported as incomplete for the current
commit, never as that record's verdict. Raw output goes to ``RUN-<model>.log``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.git_subprocess import git_text
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.review_files import list_reviews, reviews_dir
from specy_road.review_record_write import (ReviewRunBusy, file_review, final_output, output_path, review_run_lock,
                                            reviewer_env, run_text, snapshot, write_schema)
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target, same_commit
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapters import ClaudeCode, Launch, Unsupported, adapter_for, reviewer_cli
from specy_road.worker_sessions import check_session_id

RUN_PREFIX = "RUN-"
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 30.0
#: What a provider says when it is out of capacity or the account is throttled (Anthropic 429/529
#: ``overloaded_error``, OpenAI 429 / usage limit, Google ``RESOURCE_EXHAUSTED``).
CAPACITY = re.compile(r"rate[ _-]?limit|usage limit|\b429\b|\b529\b|overloaded|capacity|too many requests"
                      r"|quota|resource[ _-]?exhausted", re.IGNORECASE)
RESUME_PROMPT = ("Continue the review from where you stopped. End your reply with the one JSON object the review "
                 "prompt's last section describes, repeated in full if you already gave it: specy-road files the "
                 "record from it.\n")


class DelegateError(Exception):
    """A refusal, with the sentence the CLI prints."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_path(repo_root: Path, node_id: str, model: str) -> Path:
    return reviews_dir(repo_root, node_id) / f"{RUN_PREFIX}{model}.json"


def load_run(repo_root: Path, node_id: str, model: str) -> dict[str, Any] | None:
    return _read_json(run_path(repo_root, node_id, model))


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


def _entry(repo_root: Path, model: str) -> dict[str, Any]:
    config, err = pinned_config(repo_root)
    if err:
        raise DelegateError(f"orchestration config: {err}")
    entry = next((e for e in config.get("roster") or [] if e.get("id") == model), None)
    if entry is None:
        raise DelegateError(f"{model!r} is not in the roster (roadmap/orchestration.yaml)")
    return entry


def _preflight(entry: dict[str, Any], cwd: Path) -> None:
    cmd = entry.get("preflight")
    if cmd and subprocess.run(str(cmd), shell=True, cwd=cwd, check=False).returncode != 0:
        raise DelegateError(f"preflight failed: {cmd}; nothing was launched")


class _Harness:
    """One roster entry's way of starting and resuming a reviewer turn."""

    def __init__(self, repo_root: Path, entry: dict[str, Any], node_id: str, cwd: Path) -> None:
        self.harness = str(entry.get("harness") or "generic")
        self.adapter = adapter_for(self.harness)
        prof = pinned_profile_for_entry(repo_root, entry)
        if prof is not None and not prof.ok:
            raise DelegateError(f"profile for {entry.get('id')!r}: " + "; ".join(prof.errors))
        self.cli = (entry.get("channels") or {}).get("cli")
        if not self.cli and self.harness == "generic" and prof is not None:
            self.cli = prof.cli()
        api = prof.api_id if prof is not None else None
        self.api_id = None if (api or "").strip().lower() in ("", "unknown") else api
        self.effort = prof.effort("reviewer") if prof is not None else None
        self.mode = prof.launch_mode() if prof is not None else "full"
        self.repo_root, self.node_id, self.cwd, self.model = repo_root, node_id, cwd, str(entry.get("id"))
        self.default = self.harness != "generic" and not self.cli   # the adapter's own read-only reviewer command
        self.launch_mode = "bare" if self.default and isinstance(self.adapter, ClaudeCode) else self.mode
        self.can_resume = self.adapter.caps.resume

    def launch(self, prompt: Path, session: str | None) -> Launch:
        """A fresh turn, or a resume of ``session`` (an id the harness reported)."""
        if self.default:
            sid = session or (str(uuid.uuid4()) if isinstance(self.adapter, ClaudeCode) else None)
            reviews = reviews_dir(self.repo_root, self.node_id)
            return self.adapter.reviewer_launch(prompt, self.api_id, reviews, self.effort,
                                                session=(sid, session is not None) if sid else None,
                                                schema=write_schema(reviews), output=output_path(reviews, self.model))
        kw = {"node_id": self.node_id, "repo_root": self.repo_root, "launch_mode": self.mode, "effort": self.effort}
        # A custom command gets its program's structured-output flags (Antigravity `agy`: --json-schema).
        cli = reviewer_cli(self.cli, write_schema(reviews_dir(self.repo_root, self.node_id))) if self.cli else self.cli
        if session is not None:
            return self.adapter.resume(session, prompt, self.cwd, self.api_id, cli, **kw)
        return self.adapter.launch(prompt, self.cwd, self.api_id, cli, **kw)


def _turn(h: _Harness, launch: Launch, log: Path) -> dict[str, Any]:
    """Run one turn to its end; ``exit``, the reported ``session_id`` and the ``errors`` it printed."""
    out: dict[str, Any] = {"exit": None, "session_id": None, "errors": [], "tail": []}
    env = reviewer_env({k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CLAUDE_CODE_EFFORT_LEVEL")})
    with log.open("a", encoding="utf-8") as raw:
        raw.write(f"[review delegate] {_now()} {launch.argv[0]}\n")
        try:
            proc = subprocess.Popen(launch.argv, cwd=h.cwd, env=env, text=True, encoding="utf-8",
                                    errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE if launch.stdin is not None else subprocess.DEVNULL)
        except OSError as e:
            out.update(exit=127, errors=[f"cannot start {launch.argv[0]}: {e}"])
            return out
        if launch.stdin is not None and proc.stdin:
            try:
                proc.stdin.write(launch.stdin)
                proc.stdin.close()
            except OSError as e:   # the harness quit before reading its prompt
                raw.write(f"[review delegate] harness closed stdin early: {e}\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            raw.write(line)
            out["tail"] = [*out["tail"][-19:], line.strip()]
            for ev in h.adapter.parse_events(line, launch):
                out["session_id"] = ev.session_id or out["session_id"]
                if ev.type == "error":
                    out["errors"].append(str((ev.detail or {}).get("message") or ev.summary))
        out["exit"] = proc.wait()
    return out


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


def _start(repo_root: Path, t: ReviewTarget, model: str, ref: str | None, h: _Harness,
           resume: bool) -> tuple[str, str | None]:
    """``(prompt text, session to resume)``; refuses a resume the record cannot support."""
    if not resume:
        text, _prof, err = build_prompt(repo_root, t.node["id"], role="reviewer", model=model, ref=ref)
        if err:
            raise DelegateError(err)
        return text, None
    if not h.can_resume:
        raise Unsupported(f"unsupported by {h.harness}: resume")
    prev = load_run(repo_root, t.node["id"], model) or {}
    if not prev.get("session_id") or prev.get("harness") != h.harness:
        raise DelegateError(f"no recorded {h.harness} reviewer session for {model!r} on {t.node['id']}; "
                            "delegate without --resume")
    if not same_commit(repo_root, prev.get("commit"), t.commit):
        raise DelegateError(f"the recorded session reviewed {str(prev.get('commit'))[:12]}, not the commit under "
                            f"review {str(t.commit)[:12]}; delegate without --resume for a fresh review")
    return RESUME_PROMPT, check_session_id(h.harness, prev["session_id"])


def _attempts(h: _Harness, run: dict[str, Any], path: Path, prompts: tuple[Path, Path], session: str | None,
              retries: int, backoff: float, sleep: Callable[[float], None]) -> str:
    """Turns until one ends without a capacity error or the retries are spent; returns why it failed, if it did.

    A retry resumes the session the harness reported, with the continue prompt; with none reported
    (the provider refused before the session started) it launches afresh with the full prompt.
    """
    reason = ""
    for n in range(retries + 1):
        launch = h.launch(prompts[1] if session else prompts[0], session)
        turn = _turn(h, launch, path.with_suffix(".log"))
        run["session_id"] = turn["session_id"] or launch.session_id or run["session_id"]
        if turn["session_id"] and h.can_resume:
            session = check_session_id(h.harness, turn["session_id"])
        failed = turn["exit"] != 0 or bool(turn["errors"])
        cap = capacity_error(turn["errors"] + turn["tail"]) if failed else None
        said = cap or next(iter(turn["errors"]), "")
        run["attempts"].append({"at": _now(), "exit": turn["exit"], "capacity": bool(cap), "error": said[:300] or None})
        _save(path, run)
        if not cap:
            return f"harness exited {turn['exit']}: {said[:200] or 'no error text'}" if failed else ""
        reason = f"capacity error after {n + 1} attempt(s): {cap[:200]}"
        if n < retries:
            sleep(backoff * 2 ** n)
    return reason


def _prompt_file(repo_root: Path, node_id: str, model: str, text: str, suffix: str = "") -> Path:
    p = repo_root / "work" / f"prompt-{node_id}-reviewer-{model}{suffix}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def delegate(repo_root: Path, node_id: str, model: str, *, ref: str | None = None, resume: bool = False,
             retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, worktree: Path | None = None,
             sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Run the reviewer until it ends or runs out of capacity retries; returns the run record."""
    try:
        t = resolve_target(repo_root, node_id, ref)
    except ReviewTargetError as e:
        raise DelegateError(str(e)) from None
    entry = _entry(repo_root, model)
    cwd = (worktree or Path(git_text(["rev-parse", "--show-toplevel"], repo_root) or repo_root)).resolve()
    h = _Harness(repo_root, entry, node_id, cwd)
    text, session = _start(repo_root, t, model, ref, h, resume)
    _preflight(entry, cwd)
    prompts = (_prompt_file(repo_root, node_id, model, text),
               _prompt_file(repo_root, node_id, model, RESUME_PROMPT, "-resume"))
    path, reviews = run_path(repo_root, node_id, model), reviews_dir(repo_root, node_id)
    run = {"node_id": node_id, "model": model, "harness": h.harness, "ref": t.ref, "commit": t.commit,
           "state": "running", "session_id": session, "resumed": resume, "started_at": _now(), "ended_at": None,
           "attempts": [], "reason": None, "log": str(path.with_suffix(".log"))}
    lock = contextlib.ExitStack()
    try:
        lock.enter_context(review_run_lock(reviews))   # one reviewer run per leaf: their files would cross-fail
    except ReviewRunBusy as e:
        raise DelegateError(str(e)) from None
    with lock:
        _save(path, run)
        output_path(reviews, model).unlink(missing_ok=True)   # a stale answer never stands in for this run's
        try:
            before = snapshot(cwd, reviews, model)
            reason = _attempts(h, run, path, prompts, session, retries, backoff, sleep)
            filed = file_review(repo_root, node_id, model, reviews, before=before, after=snapshot(cwd, reviews, model),
                                output=final_output(h.adapter, run_text(path.with_suffix(".log")),
                                                    output_path(reviews, model)),
                                ref=ref, launch_mode=h.launch_mode)
            ok, why = valid_record(repo_root, t, model) if filed.state == "recorded" else (False, filed.reason)
            run.update(state="complete" if ok else "incomplete", outcome=filed.state,
                       reason=None if ok else "; ".join(x for x in (reason, why) if x))
        except BaseException as e:   # an interrupt or a launch refusal still closes the record
            run.update(state="incomplete", reason=f"interrupted: {e or type(e).__name__}")
            raise
        finally:
            run["ended_at"] = _now()
            _save(path, run)
    return run


def run_states(repo_root: Path, node_id: str, commit: str | None) -> list[dict[str, Any]]:
    """Each ``RUN-*.json`` for the node; ``current`` when it is for ``commit`` (the commit under review)."""
    d = reviews_dir(repo_root, node_id)
    out = []
    for p in sorted(d.glob(f"{RUN_PREFIX}*.json")) if d.is_dir() else []:
        r = _read_json(p) or {}
        current = bool(commit and r.get("commit") and same_commit(repo_root, r["commit"], commit))
        out.append({"file": p.name, "model": r.get("model"), "state": r.get("state"), "commit": r.get("commit"),
                    "session_id": r.get("session_id"), "reason": r.get("reason"), "current": current})
    return out


def run_lines(runs: list[dict[str, Any]]) -> list[str]:
    """One line per delegated review run, saying which commit it was for."""
    lines = []
    for r in runs:
        when = "" if r["current"] else " (not the commit under review)"
        why = f": {r['reason']}" if r["state"] == "incomplete" and r.get("reason") else ""
        lines.append(f"{r['file']}: {r['state']} run by {r['model']} at {str(r['commit'] or '?')[:12]}{when}"
                     f", session {r['session_id'] or '-'}{why}")
    return lines


def run_problems(node_id: str, runs: list[dict[str, Any]]) -> list[str]:
    """An incomplete run at the commit under review is a problem: its reviewer has no verdict there."""
    return [f"{r['file']}: {r['model']}'s delegated review of this commit is incomplete ({r.get('reason') or '?'}); "
            f"`specy-road review delegate {node_id} --model {r['model']}` (add --resume to continue its session)"
            for r in runs if r["current"] and r["state"] == "incomplete"]


def cmd_review_delegate(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    try:
        run = delegate(root, ns.node_id, ns.model, ref=ns.ref, resume=ns.resume, retries=ns.retries,
                       backoff=ns.backoff, worktree=Path(ns.worktree) if ns.worktree else None)
    except (DelegateError, ReviewTargetError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Unsupported as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if ns.json:
        print(json.dumps(run, indent=2))
    else:
        print(f"{ns.node_id}: {ns.model} review at {str(run['commit'])[:12]} {run['state']}, "
              f"session {run['session_id'] or '-'}, {len(run['attempts'])} attempt(s)"
              + (f" — {run['reason']}" if run["reason"] else ""))
    return 0 if run["state"] == "complete" else 1


def _count(text: str) -> int:
    """``--retries``: a whole number, 0 or more (0 still makes the first attempt)."""
    n = int(text)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more, not {text}")
    return n


def _seconds(text: str) -> float:
    """``--backoff``: a finite number of seconds, 0 or more."""
    s = float(text)
    if not math.isfinite(s) or s < 0:
        raise argparse.ArgumentTypeError(f"must be a finite number of seconds, 0 or more, not {text}")
    return s


def add_parser(rsub: Any) -> None:
    """``review delegate`` under ``review_cli``'s ``review`` subcommands."""
    sp = rsub.add_parser("delegate", help="Run a rostered reviewer on its harness and wait for its record")
    sp.add_argument("node_id")
    sp.add_argument("--model", required=True, help="Roster id (reviewer role, or an active substitute)")
    sp.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    sp.add_argument("--resume", action="store_true", help="Continue the recorded reviewer session for this commit")
    sp.add_argument("--retries", type=_count, default=DEFAULT_RETRIES, metavar="N",
                    help=f"Capacity or rate-limit retries (default {DEFAULT_RETRIES})")
    sp.add_argument("--backoff", type=_seconds, default=DEFAULT_BACKOFF, metavar="SECONDS",
                    help=f"First retry's wait, doubled each time (default {DEFAULT_BACKOFF:g})")
    sp.add_argument("--worktree", help="Run the reviewer in this checkout (default: this one's git root)")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_review_delegate)
