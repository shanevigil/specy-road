"""``specy-road review delegate``: run one rostered reviewer on its harness, as ``worker delegate`` runs an executor.

The reviewer prompt is :func:`build_prompt`'s (``prompt --role reviewer``), so
the reviewer keeps the packet-only, edit-nothing rules. The roster entry's
harness runs it through the worker adapters: a ``claude-code`` entry without
``channels.cli`` runs bare or explicit (:func:`specy_road.reviewer_auth.claude_reviewer_mode`,
:meth:`ClaudeCode.reviewer_launch`) with a session
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
commit, never as that record's verdict. Raw output goes to ``RUN-<model>.log``. Before a run starts, the
previous round's record, log and notes are kept under ``history/`` (:func:`specy_road.review_usage.archive_round`).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.chore_cli import chore_prompt, chore_target, load_chore
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.git_subprocess import git_text
from specy_road.orchestration_pinned import pinned_config
from specy_road.review_delegate_harness import HarnessSetupError, _Harness
from specy_road.review_delegate_packet import ensure_packet
from specy_road.review_eligible import writers
from specy_road.review_files import reviews_dir
from specy_road.review_answer import stream_lines
from specy_road.review_model_check import check_note, check_run, rostered
from specy_road.review_record_write import (Outcome, ReviewRunBusy, answer_scratch, attempt_text,
                                            close_review_run, delegate_turn, file_review, final_answer, review_run_lock,
                                            snapshot, write_schema)
from specy_road.review_run_status import superseded_by
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target, same_commit
from specy_road.review_usage import add_parser as add_usage_parser, archive_round
from specy_road.reviewer_run_failure import capacity_error, valid_record  # noqa: F401 — re-exported
from specy_road.reviewer_run_failure import gate_policy_summary as _gate_policy_summary
from specy_road.reviewer_run_failure import (_now, _read_json, close_run, run_path as _run_path, save_run,
                                             turn_capacity_error)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.worker_adapters import Unsupported
from specy_road.worker_lock import WorkerError
from specy_road.worker_sessions import check_session_id

RUN_PREFIX = "RUN-"
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 30.0
#: A chore reviewer's resume (chore_cli): it writes its own verdict file, so there is no JSON object to repeat.
CHORE_RESUME_PROMPT = ("Continue the review from where you stopped. If you already filed your verdict, say so and "
                       "stop.\n")
RESUME_PROMPT = ("Continue the review from where you stopped. Your final message must be exactly the one JSON object "
                 "the review prompt's last section describes, repeated in full if you already gave it, with nothing "
                 "before or after it: specy-road files the record from it.\n")


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


def _no_model_refusal(model: str, harness: str) -> str:
    return (f"{model}: no model would be passed to {harness}, so it would run its own default model; "
            "set harness_model on the roster entry, or routing: dynamic to accept the harness's choice")


def _model_check(repo_root: Path, model: str, log: Path, attempt: dict[str, Any]) -> tuple[str | None, tuple[str | None, str]]:
    text_out = attempt_text(log, attempt)
    rev_entry, prof = rostered(repo_root, model)
    reported, state = check_run(text_out, rev_entry, prof)
    if note := check_note(state, reported, model):
        print(note, file=sys.stderr)
    return reported, (reported, state)


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
        # each attempt's answer starts absent: a resumed turn (a Codex resume writes no -o file) never files an earlier one's
        if h.output is not None:
            h.output.unlink(missing_ok=True)
        launch = h.launch(prompts[1] if session else prompts[0], session)
        turn = delegate_turn(h.adapter, h.harness, h.log, h.cwd, launch)
        run["session_id"] = turn["session_id"] or launch.session_id or run["session_id"]
        if turn["session_id"] and h.can_resume:
            session = check_session_id(h.harness, turn["session_id"])
        failed = turn["exit"] != 0 or bool(turn["errors"])
        cap = turn_capacity_error(turn["errors"], turn["tail"]) if failed else None
        said = cap or next(iter(turn["errors"]), "")
        if failed and not said:   # no parsed error: the last non-blank line of this turn's log span (the harness's own)
            lines = [ln.strip() for ln in attempt_text(h.log, turn).splitlines() if ln.strip()]
            said = lines[-1][:200] if lines else "no error text"
        run["attempts"].append({"at": _now(), "exit": turn["exit"], "capacity": bool(cap), "error": said[:300] or None,
                                "log_start": turn["log_start"], "log_end": turn["log_end"],   # the span run_text reads
                                "log_sha256": turn["log_sha256"]})
        if path.is_symlink():   # replaced below, never followed; the tripwire still reports it (review_write_check)
            h.replaced.append(path)
        save_run(path, run)
        if not cap:
            return f"harness exited {turn['exit']}: {said[:200]}" if failed else ""
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
    """Close the run from its filing outcome and the last attempt (:func:`close_review_run`). A chore run files
    nothing (``filed`` is ``None``: its reviewer wrote its own verdict file, M8.2), so ``close_run`` judges it by
    that file."""
    last = run["attempts"][-1] if run["attempts"] else {}
    tail = stream_lines(attempt_text(path.with_suffix(".log"), last))[-20:]   # the last attempt only
    errors = [last["error"]] if last.get("error") else []
    if filed is None:
        close_run(repo_root, t, model, run, exit_code=last.get("exit"), errors=errors, tail=tail, reason_prefix=reason)
        return
    close_review_run(repo_root, t, model, run, replace(filed, exit=last.get("exit")), reason=reason, errors=errors,
                     tail=tail)


def _delegate_locked(repo_root: Path, t: ReviewTarget, node_id: str, model: str, entry: dict[str, Any], h: _Harness,
                     path: Path, reviews: Path, cwd: Path, chore: bool, ref: str | None, resume: bool,
                     retries: int, backoff: float, sleep: Callable[[float], None], sign_key: Path | None,
                     answer: Path) -> dict[str, Any]:
    h.output = None if chore else answer
    if not chore and not resume:   # M15.17: a missing or other-commit packet is built, not refused
        ensure_packet(repo_root, t, ref)
    text, session = _start(repo_root, t, model, ref, h, resume)
    _preflight(entry, cwd)   # M8.3: after the lock, before the RUN record is saved
    if h.note:   # bare mode and the subscription login, same sentence prompt prints
        print(h.note, file=sys.stderr)
    if h.api_id is None and entry.get("routing") != "dynamic":
        raise DelegateError(_no_model_refusal(model, h.harness))
    prompts = (_prompt_file(repo_root, node_id, model, text),
               _prompt_file(repo_root, node_id, model, CHORE_RESUME_PROMPT if chore else RESUME_PROMPT, "-resume"))
    archive_round(repo_root, node_id, model)   # M14.6: the previous round's RUN json, log and notes, kept in history/
    run = {"node_id": node_id, "model": model, "harness": h.harness, "ref": t.ref, "commit": t.commit,
           "state": "running", "session_id": session, "resumed": resume, "source": "review-delegate",
           "started_at": _now(), "ended_at": None, "attempts": [], "events": [], "reason": None,
           "launch_mode": h.launch_mode, "requested_model": h.api_id, "reported_model": None,
           "log": str(path.with_suffix(".log"))}
    save_run(path, run)
    h.log = log = path.with_suffix(".log")
    try:
        # M8.3's read-only check and filing are for roadmap reviews; a chore reviewer files its own verdict file.
        if not chore:
            write_schema(repo_root, reviews, ref)   # before the snapshot: the reviewer must not change it
        before = snapshot(cwd, reviews, model) if not chore else None
        reason = _attempts(h, run, path, prompts, session, retries, backoff, sleep)
        model_check = None
        if before is not None:
            attempt = run["attempts"][-1] if run["attempts"] else {}
            reported, model_check = _model_check(repo_root, model, log, attempt)
            run["reported_model"] = reported
        filed = None if before is None else file_review(
            repo_root, node_id, model, reviews, answer=final_answer(
                h.adapter, attempt_text(log, run["attempts"][-1] if run["attempts"] else {}), answer),
            before=before, after=snapshot(cwd, reviews, model, before).with_symlinks(h.replaced), ref=ref,
            launch_mode=h.launch_mode, sign_key=sign_key, model_check=model_check)
        _close(repo_root, t, model, run, path, reason, filed)
    except BaseException as e:   # an interrupt or a launch refusal still closes the record
        close_review_run(repo_root, t, model, run, Outcome("rerun", f"interrupted: {e or type(e).__name__}", exit=None))
        raise
    finally:
        run["ended_at"] = _now()
        save_run(path, run)
    return run


def delegate(repo_root: Path, node_id: str, model: str, *, ref: str | None = None, resume: bool = False,
             retries: int = DEFAULT_RETRIES, backoff: float = DEFAULT_BACKOFF, worktree: Path | None = None,
             sleep: Callable[[float], None] = time.sleep, sign_key: Path | None = None) -> dict[str, Any]:
    """Run the reviewer until it ends or runs out of capacity retries; returns the run record. ``sign_key``
    signs the filed record (``review record --sign-key``).

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
        if wrote := writers(repo_root, t.node["id"], (t.entry or {}).get("branch")).get(model):   # before any write
            raise DelegateError(f"{model} wrote {wrote[0]} on {node_id}; the executor never reviews its own leaf")
    entry = _entry(repo_root, model)
    cwd = (worktree or Path(git_text(["rev-parse", "--show-toplevel"], repo_root) or repo_root)).resolve()
    try:
        h = _Harness(repo_root, entry, node_id, cwd, chore=chore is not None)
    except HarnessSetupError as e:
        raise DelegateError(str(e)) from None
    if h.auth_error:   # forced bare with no key: before the lock, the prompt files and the RUN record
        raise DelegateError(h.auth_error)
    path, reviews = run_path(repo_root, node_id, model), reviews_dir(repo_root, node_id)
    lock = contextlib.ExitStack()
    try:   # one reviewer run per leaf, taken before the run writes any of its files: they would cross-fail
        lock.enter_context(review_run_lock(reviews))
    except ReviewRunBusy as e:
        raise DelegateError(str(e)) from None
    with lock, answer_scratch(model) as answer:
        return _delegate_locked(repo_root, t, node_id, model, entry, h, path, reviews, cwd, chore is not None, ref,
                                resume, retries, backoff, sleep, sign_key, answer)


def run_states(repo_root: Path, node_id: str, commit: str | None) -> list[dict[str, Any]]:
    """Each ``RUN-*.json`` for the node; ``current`` when it is for ``commit`` (the commit under review);
    ``superseded`` names a valid record filed later at the run's commit when the run did not complete."""
    d = reviews_dir(repo_root, node_id)
    out = []
    for p in sorted(d.glob(f"{RUN_PREFIX}*.json")) if d.is_dir() else []:
        r = _read_json(p) or {}
        current = bool(commit and r.get("commit") and same_commit(repo_root, r["commit"], commit))
        out.append({"file": p.name, "model": r.get("model"), "state": r.get("state"), "commit": r.get("commit"),
                    "session_id": r.get("session_id"), "reason": r.get("reason"), "events": r.get("events") or [],
                    "current": current, "superseded": superseded_by(repo_root, node_id, r)})
    return out


def gate_policy_summary(gate: Any, runs: list[dict[str, Any]]) -> str:
    """``handoff status`` policy line (:func:`specy_road.reviewer_run_failure.gate_policy_summary`); a superseded run
    is no reviewer failure."""
    return _gate_policy_summary(gate, [r for r in runs if not r.get("superseded")])


def run_lines(runs: list[dict[str, Any]]) -> list[str]:
    """One line per delegated review run, saying which commit it was for."""
    lines = []
    for r in runs:
        when = "" if r["current"] else " (not the commit under review)"
        why = f": {r['reason']}" if r["state"] == "incomplete" and r.get("reason") else ""
        later = f" — superseded: {r['superseded']} was filed later at this commit" if r.get("superseded") else ""
        lines.append(f"{r['file']}: {r['state']} run by {r['model']} at {str(r['commit'] or '?')[:12]}{when}"
                     f", session {r['session_id'] or '-'}{why}{later}")
    return lines


def run_problems(node_id: str, runs: list[dict[str, Any]]) -> list[str]:
    """An incomplete run at the commit under review is a problem: its reviewer has no verdict there, unless a
    record filed later supersedes it."""
    return [f"{r['file']}: {r['model']}'s delegated review of this commit is incomplete ({r.get('reason') or '?'}); "
            f"`specy-road review delegate {node_id} --model {r['model']}` (add --resume to continue its session)"
            for r in runs if r["current"] and r["state"] == "incomplete" and not r.get("superseded")]


def cmd_review_delegate(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    try:
        run = delegate(root, ns.node_id, ns.model, ref=ns.ref, resume=ns.resume, retries=ns.retries,
                       backoff=ns.backoff, worktree=Path(ns.worktree) if ns.worktree else None, sign_key=ns.sign_key)
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
    """``review delegate``, and ``review usage`` over its runs, under ``review_cli``'s ``review`` subcommands."""
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
    sp.add_argument("--sign-key", type=Path, metavar="PATH",
                    help="Sign the filed record with this OpenSSH private key (needed under policy.signed_reviews)")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_review_delegate)
    add_usage_parser(rsub)   # registered here so review_cli.py stays under its file-limits cap
