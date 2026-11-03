"""``specy-road review delegate``: run one rostered reviewer on its harness, as ``worker delegate`` runs an executor.

The reviewer prompt is :func:`build_prompt`'s (``prompt --role reviewer``), so
the reviewer keeps the packet-only, edit-nothing rules. The roster entry's
harness runs it through the worker adapters: a ``claude-code`` entry without
``channels.cli`` runs bare (:meth:`ClaudeCode.reviewer_launch`) with a session
id chosen up front, any other runs its adapter's command. Unlike a worker, the
command waits for the turn: a reviewer has one job, and its outcome is whether
a valid ``REVIEW-<model>.md`` for the commit under review exists afterwards.

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
import json
import math
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.git_subprocess import git_text
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.review_files import reviews_dir
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target, same_commit
from specy_road.reviewer_run_failure import (_now, _read_json, _save, capacity_error, close_run, gate_policy_summary,
                                             record_reviewer_failure_event, run_path as _run_path, valid_record)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapters import ClaudeCode, Launch, Unsupported, adapter_for
from specy_road.worker_sessions import check_session_id

RUN_PREFIX = "RUN-"
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 30.0
RESUME_PROMPT = ("Continue the review from where you stopped. If you already filed your verdict with "
                 "`specy-road review record`, say so and stop.\n")


class DelegateError(Exception):
    """A refusal, with the sentence the CLI prints."""


def run_path(repo_root: Path, node_id: str, model: str) -> Path:
    return _run_path(repo_root, node_id, model)


def load_run(repo_root: Path, node_id: str, model: str) -> dict[str, Any] | None:
    return _read_json(run_path(repo_root, node_id, model))


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
        self.repo_root, self.node_id, self.cwd = repo_root, node_id, cwd
        self.bare = self.harness == "claude-code" and not self.cli
        self.can_resume = self.adapter.caps.resume

    def launch(self, prompt: Path, session: str | None) -> Launch:
        """A fresh turn, or a resume of ``session`` (an id the harness reported)."""
        if self.bare:
            sid = session or str(uuid.uuid4())
            assert isinstance(self.adapter, ClaudeCode)
            return self.adapter.reviewer_launch(prompt, self.api_id, reviews_dir(self.repo_root, self.node_id),
                                                self.effort, session=(sid, session is not None))
        kw = {"node_id": self.node_id, "repo_root": self.repo_root, "launch_mode": self.mode, "effort": self.effort}
        if session is not None:
            return self.adapter.resume(session, prompt, self.cwd, self.api_id, self.cli, **kw)
        return self.adapter.launch(prompt, self.cwd, self.api_id, self.cli, **kw)


def _turn(h: _Harness, launch: Launch, log: Path) -> dict[str, Any]:
    """Run one turn to its end; ``exit``, the reported ``session_id`` and the ``errors`` it printed."""
    out: dict[str, Any] = {"exit": None, "session_id": None, "errors": [], "tail": []}
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "CLAUDE_CODE_EFFORT_LEVEL")}
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
    path = run_path(repo_root, node_id, model)
    run = {"node_id": node_id, "model": model, "harness": h.harness, "ref": t.ref, "commit": t.commit,
           "state": "running", "session_id": session, "resumed": resume, "source": "review-delegate",
           "started_at": _now(), "ended_at": None, "attempts": [], "events": [], "reason": None,
           "log": str(path.with_suffix(".log"))}
    _save(path, run)
    try:
        reason = _attempts(h, run, path, prompts, session, retries, backoff, sleep)
        log_path = path.with_suffix(".log")
        log_tail = (log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
                    if log_path.is_file() else [])
        last = run["attempts"][-1] if run["attempts"] else {}
        err_line = last.get("error")
        close_run(repo_root, t, model, run, exit_code=last.get("exit"),
                  errors=[err_line] if err_line else [], tail=log_tail, reason_prefix=reason)
    except BaseException as e:   # an interrupt or a launch refusal still closes the record
        err = f"interrupted: {e or type(e).__name__}"
        run.update(state="incomplete", reason=err)
        record_reviewer_failure_event(run, err)
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
                    "session_id": r.get("session_id"), "reason": r.get("reason"), "events": r.get("events") or [],
                    "current": current})
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
