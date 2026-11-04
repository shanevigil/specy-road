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
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.chore_cli import chore_prompt, chore_target, load_chore
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.git_subprocess import git_text
from specy_road.orchestration_config import harness_model
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.orchestration_role_env import harness_env
from specy_road.review_files import reviews_dir
from specy_road.review_record_write import (OUTPUT_SCHEMA_NAME, Outcome, ReviewRunBusy, RootFence, file_review,
                                            final_output, output_path, prepare_harness_files, review_run_lock,
                                            reviewer_env, run_text, snapshot, write_schema)
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target, same_commit
from specy_road.reviewer_run_failure import capacity_error, gate_policy_summary, valid_record  # noqa: F401 — re-exported
from specy_road.reviewer_run_failure import (_now, _read_json, close_run, harness_error_line,
                                             record_reviewer_failure_event, run_path as _run_path, save_run,
                                             turn_capacity_error)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapters import ClaudeCode, Launch, Unsupported, adapter_for, reviewer_cli
from specy_road.worker_lock import WorkerError
from specy_road.worker_sessions import check_session_id

RUN_PREFIX = "RUN-"
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 30.0
#: A chore reviewer's resume (chore_cli): it writes its own verdict file, so there is no JSON object to repeat.
CHORE_RESUME_PROMPT = ("Continue the review from where you stopped. If you already filed your verdict, say so and "
                       "stop.\n")
RESUME_PROMPT = ("Continue the review from where you stopped. End your reply with the one JSON object the review "
                 "prompt's last section describes, repeated in full if you already gave it: specy-road files the "
                 "record from it.\n")


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

    def __init__(self, repo_root: Path, entry: dict[str, Any], node_id: str, cwd: Path, chore: bool = False) -> None:
        self.harness = str(entry.get("harness") or "generic")
        self.adapter = adapter_for(self.harness)
        prof = pinned_profile_for_entry(repo_root, entry)
        if prof is not None and not prof.ok:
            raise DelegateError(f"profile for {entry.get('id')!r}: " + "; ".join(prof.errors))
        self.cli = (entry.get("channels") or {}).get("cli")
        if not self.cli and self.harness == "generic" and prof is not None:
            self.cli = prof.cli()
        api = prof.api_id if prof is not None else ""   # no profile and no harness_model: the harness's default
        self.api_id = harness_model(entry, api)
        self.effort = prof.effort("reviewer") if prof is not None else None
        self.mode = prof.launch_mode() if prof is not None else "full"
        self.repo_root, self.node_id, self.cwd, self.model = repo_root, node_id, cwd, str(entry.get("id"))
        # The adapter's own read-only reviewer command. A chore reviewer writes its verdict file itself (chore_cli),
        # so it keeps the launch it had before M8.3: Claude Code's bare reviewer command, else the adapter's own.
        self.chore = chore
        self.default = self.harness != "generic" and not self.cli and (not chore or isinstance(self.adapter, ClaudeCode))
        self.launch_mode = "bare" if self.default and isinstance(self.adapter, ClaudeCode) else self.mode
        self.can_resume = self.adapter.caps.resume
        self.fenced = False   # a RootFence saw the hand-off root move during one of this run's turns

    def launch(self, prompt: Path, session: str | None) -> Launch:
        """A fresh turn, or a resume of ``session`` (an id the harness reported)."""
        if self.default:
            sid = session or (str(uuid.uuid4()) if isinstance(self.adapter, ClaudeCode) else None)
            reviews = reviews_dir(self.repo_root, self.node_id)
            structured = {} if self.chore else {"schema": reviews / OUTPUT_SCHEMA_NAME, "output": output_path(reviews, self.model)}
            return self.adapter.reviewer_launch(prompt, self.api_id, reviews, self.effort,
                                                session=(sid, session is not None) if sid else None, **structured)
        kw = {"node_id": self.node_id, "repo_root": self.repo_root, "launch_mode": self.mode, "effort": self.effort}
        # A custom command gets its program's structured-output flags (Antigravity `agy`: --json-schema).
        cli = (reviewer_cli(self.cli, reviews_dir(self.repo_root, self.node_id) / OUTPUT_SCHEMA_NAME)
               if self.cli and not self.chore else self.cli)
        if session is not None:
            return self.adapter.resume(session, prompt, self.cwd, self.api_id, cli, **kw)
        return self.adapter.launch(prompt, self.cwd, self.api_id, cli, **kw)


def _turn(h: _Harness, launch: Launch, log: Path) -> dict[str, Any]:
    """Run one turn to its end; ``exit``, the reported ``session_id`` and the ``errors`` it printed."""
    out: dict[str, Any] = {"exit": None, "session_id": None, "errors": [], "tail": []}
    # the role and the harness's avoid-list for installed guard hooks (M8.5, M11.62), no caches (M8.3)
    env = reviewer_env(harness_env(os.environ, "reviewer", harness=h.harness))
    with log.open("a", encoding="utf-8") as raw:
        raw.write(f"[review delegate] {_now()} {launch.argv[0]}\n")
        # specy-road changes the hand-off root's entries only between turns: one moving during the turn is the harness's
        fence = RootFence(reviews_dir(h.repo_root, h.node_id), h.model)
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
    h.fenced = h.fenced or fence.moved()
    return out


def _start(repo_root: Path, t: ReviewTarget, model: str, ref: str | None, h: _Harness,
           resume: bool) -> tuple[str, str | None]:
    """``(prompt text, session to resume)``; refuses a resume the record cannot support."""
    if not resume and t.node.get("chore"):
        return chore_prompt(t.node["chore"], "reviewer", model, repo_root, commit=t.commit), None
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
        cap = turn_capacity_error(turn["errors"], turn["tail"]) if failed else None
        said = cap or next(iter(turn["errors"]), "")
        run["attempts"].append({"at": _now(), "exit": turn["exit"], "capacity": bool(cap), "error": said[:300] or None})
        save_run(path, run)
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


def _close(repo_root: Path, t: ReviewTarget, model: str, run: dict[str, Any], path: Path, reason: str,
           filed: Outcome | None) -> None:
    """Close the run from its filing outcome and the last attempt. A recorded verdict, or a chore run (``filed``
    is ``None``: its reviewer wrote its own verdict file), goes through :func:`close_run`; a review failure or rerun
    request is incomplete whatever older record is on file, with a reviewer-failure event (M11.72) naming the
    harness's error, or the outcome when the harness ended cleanly."""
    log = path.with_suffix(".log")
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:] if log.is_file() else []
    last = run["attempts"][-1] if run["attempts"] else {}
    errors = [last["error"]] if last.get("error") else []
    if filed is None or filed.state == "recorded":
        if filed is not None:
            run["outcome"] = filed.state
        close_run(repo_root, t, model, run, exit_code=last.get("exit"), errors=errors, tail=tail, reason_prefix=reason)
        return
    run.update(state="incomplete", outcome=filed.state, reason="; ".join(x for x in (reason, filed.reason) if x))
    harness_failed = errors or last.get("exit") not in (0, None)
    record_reviewer_failure_event(run, harness_error_line(exit_code=last.get("exit"), errors=errors, tail=tail,
                                                          fallback=filed.reason) if harness_failed else filed.reason)


def delegate(repo_root: Path, node_id: str, model: str, *, ref: str | None = None, resume: bool = False,
             retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, worktree: Path | None = None,
             sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Run the reviewer until it ends or runs out of capacity retries; returns the run record.

    ``node_id`` may be a chore slug started with ``--review`` (chore_cli): the reviewer runs in its worktree."""
    chore = load_chore(repo_root, node_id)
    if chore is not None:
        if chore.get("closed_at") or not chore["review"]:
            raise DelegateError(f"chore {node_id} is closed" if chore.get("closed_at")
                                else f"chore {node_id} was started without --review")
        t, worktree = chore_target(repo_root, chore), worktree or Path(chore["worktree"])
    else:
        try:
            t = resolve_target(repo_root, node_id, ref)
        except ReviewTargetError as e:
            raise DelegateError(str(e)) from None
    entry = _entry(repo_root, model)
    cwd = (worktree or Path(git_text(["rev-parse", "--show-toplevel"], repo_root) or repo_root)).resolve()
    h = _Harness(repo_root, entry, node_id, cwd, chore=chore is not None)
    text, session = _start(repo_root, t, model, ref, h, resume)
    _preflight(entry, cwd)
    prompts = (_prompt_file(repo_root, node_id, model, text),
               _prompt_file(repo_root, node_id, model, CHORE_RESUME_PROMPT if chore else RESUME_PROMPT, "-resume"))
    path, reviews = run_path(repo_root, node_id, model), reviews_dir(repo_root, node_id)
    run = {"node_id": node_id, "model": model, "harness": h.harness, "ref": t.ref, "commit": t.commit,
           "state": "running", "session_id": session, "resumed": resume, "source": "review-delegate",
           "started_at": _now(), "ended_at": None, "attempts": [], "events": [], "reason": None,
           "log": str(path.with_suffix(".log"))}
    lock = contextlib.ExitStack()
    try:
        lock.enter_context(review_run_lock(reviews))   # one reviewer run per leaf: their files would cross-fail
    except ReviewRunBusy as e:
        raise DelegateError(str(e)) from None
    with lock:
        save_run(path, run)
        prepare_harness_files(reviews, model)   # the answer emptied (never a stale one), both written in place
        try:
            # M8.3's read-only check and filing are for roadmap reviews; a chore reviewer files its own verdict file.
            if chore is None:
                write_schema(repo_root, reviews)   # before the snapshot: the reviewer must not change it
            before = snapshot(cwd, reviews, model, t.ref) if chore is None else None
            reason = _attempts(h, run, path, prompts, session, retries, backoff, sleep)
            filed = None if before is None else file_review(
                repo_root, node_id, model, reviews, before=before, after=snapshot(cwd, reviews, model, t.ref),
                output=final_output(h.adapter, run_text(path.with_suffix(".log")), output_path(reviews, model)),
                ref=ref, launch_mode=h.launch_mode, fenced=h.fenced)
            _close(repo_root, t, model, run, path, reason, filed)
        except BaseException as e:   # an interrupt or a launch refusal still closes the record
            err = f"interrupted: {e or type(e).__name__}"
            run.update(state="incomplete", reason=err)
            record_reviewer_failure_event(run, err)
            raise
        finally:
            run["ended_at"] = _now()
            save_run(path, run)
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
    except (DelegateError, ReviewTargetError, WorkerError) as e:   # WorkerError: an unsafe recorded session id
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
    sp.add_argument("--worktree", help="Run the reviewer in this checkout (default: a chore's worktree for a "
                                       "chore slug, else this checkout's git root)")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_review_delegate)
