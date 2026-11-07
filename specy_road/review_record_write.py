"""File a reviewer run's final JSON as ``work/reviews/<NODE_ID>/REVIEW-<model>.md`` (M8.3).

A reviewer started by specy-road (``prompt --channel cli`` or ``review delegate``) writes nothing: it ends its
reply with one JSON object shaped by :func:`output_schema`, the review-record schema less the fields
``review record`` fills, plus ``notes``. Claude Code validates it with ``--json-schema``, Codex with
``--output-schema`` (and writes it to ``-o``, in a private temporary directory: :func:`answer_scratch`),
Antigravity's ``agy`` with ``--json-schema`` (:func:`~specy_road.worker_adapter_base.reviewer_cli`). One extractor,
:func:`~specy_road.review_answer.final_answer`, reads every harness's answer from the final turn's last terminal
message, by the harness's row of :data:`~specy_road.review_answer.TURNS`. :func:`file_review` then decides the run's
outcome:

* ``review_failure`` — the tripwire (:mod:`specy_road.review_write_check`; prevention is the read-only launch)
  saw a write: the leaf worktree's ``git status`` gained or changed an entry, or the hand-off directory gained or
  changed a file other than the notes and specy-road's run files. A ``REVIEW-<model>.md`` the run filed itself is
  put back as it was, so the gate never counts it. Nothing is filed;
* ``rerun`` — :func:`~specy_road.review_answer.final_answer` found no answer, or ``review record`` refuses it (a
  wrong commit, an approve with a failing item, no ``sign_key`` under ``policy.signed_reviews``): a rerun request,
  never a verdict;
* ``recorded`` — specy-road wrote the notes to ``notes-<model>.md`` and ``review record`` filed the record from
  them, with every check, the roster family and the ``history/`` copy an interactive filing gets.

:func:`close_review_run` is the one way a launched reviewer's run record is closed, from that :class:`Outcome`.

Other sessions writing in the same checkout during the run count as the run's writes, so run reviewers where
nothing else writes; :func:`review_run_lock` keeps two reviewer runs of one leaf, whose hand-off directory is
shared, from failing each other. The reviewer's process gets :func:`reviewer_env`, so re-running Python tests
writes no bytecode or pytest cache.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.bundled_scripts.generate_brief import index, load_nodes
from specy_road.review_answer import (FILLED_BY_SPECY_ROAD, UNREADABLE_ANSWER, Rerun, drop_nulls, events,
                                      final_answer, output_schema, stream_lines)
from specy_road.review_files import render_front_matter, review_path
from specy_road.review_model_check import Check, check_note, check_run, rostered
from specy_road.review_record_rules import NOTES_RULES_LINES
from specy_road.integrity_removals import target_unplanned_removals
from specy_road.review_lock import ReviewRunBusy, review_run_lock  # re-exported: the per-leaf lock (file limit)
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target
from specy_road.review_write_check import (  # re-exported: the post-run write check lives there (file limit)
    OUTPUT_SCHEMA_NAME,
    Snapshot,
    append_log,
    replace_file,
    snapshot,
    written,
)
from specy_road.orchestration_role_env import harness_env
from specy_road.reviewer_run_failure import _now, close_run, harness_error_line, record_reviewer_failure_event



def strict_schema(ids: list[str], removals: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """:func:`output_schema` in OpenAI strict structured-output form, which Codex's ``--output-schema`` is sent in:
    every object lists all its properties as required and allows no others, so an optional field becomes required
    and may be ``null`` (:func:`drop_nulls` removes it again). ``acceptance`` names exactly the keys ``review record``
    checks (strict mode has no free-key map or ``propertyNames``): the leaf's ``ids``, each taking the record
    schema's ``additionalProperties`` values, and each unplanned test removal of ``removals`` (M15.18), taking its
    ``patternProperties`` value (``pass`` only) or ``null``, which a blocking reviewer answers and
    :func:`drop_nulls` removes. Both come from :func:`output_schema`'s ``acceptance``, so the two cannot diverge.
    Anything it admits, less its nulls, is :func:`output_schema`-valid but for the checks it cannot carry, which the
    validator still makes."""
    base = output_schema()
    props = {k: v if k in base["required"] else {"anyOf": [v, {"type": "null"}]} for k, v in base["properties"].items()}
    acc = base["properties"]["acceptance"]
    (removal,) = acc["patternProperties"].values()
    keys = {a: acc["additionalProperties"] for a in ids}
    keys |= {r: {"anyOf": [{"type": "string", "enum": [removal["const"]], "description": removal["description"]},
                           {"type": "null"}]} for r in removals}
    props["acceptance"] = {"type": "object", "description": acc["description"], "additionalProperties": False,
                           "required": list(keys), "properties": keys}
    return {**base, "required": list(props), "properties": props}


def acceptance_keys(root: Path, node_id: str, ref: str | None) -> tuple[list[str], list[str]]:
    """The acceptance keys ``review record`` checks for ``node_id`` at ``ref``, from the same resolved target: its
    acceptance ids, and its unplanned test removals (:func:`~specy_road.integrity_removals.target_unplanned_removals`, which the
    packet lists and ``review record`` requires on an approve). A target that does not resolve has none; ``review
    record`` then refuses the filing itself."""
    try:
        t = resolve_target(root, node_id, ref)
    except ReviewTargetError:
        return acceptance_ids(index(load_nodes(root))[node_id]), []
    return acceptance_ids(t.node), target_unplanned_removals(root, t)


def write_schema(root: Path, reviews: Path, ref: str | None = None) -> Path:
    """``review-output.schema.json`` in the hand-off directory, for the harness flags that read a file: the
    :func:`strict_schema` of the leaf the directory is named for, at ``ref`` (the reviewed ref ``review record`` is
    given), with :func:`acceptance_keys`. Codex needs it and the others accept it. Callers write it under
    :func:`review_run_lock`, before the run's first snapshot, so the reviewer may not change it."""
    path = reviews / OUTPUT_SCHEMA_NAME
    reviews.mkdir(parents=True, exist_ok=True)
    replace_file(path, json.dumps(strict_schema(*acceptance_keys(root, reviews.name, ref)), indent=2) + "\n")
    return path


@contextlib.contextmanager
def answer_scratch(model: str) -> Iterator[Path]:
    """Where a harness that writes its final message to a file (Codex ``-o``) writes it: a private temporary
    directory outside the checkout and the hand-off directory, so specy-road's answer file is never in the tree the
    write check compares, and removed with the run."""
    with tempfile.TemporaryDirectory(prefix="specy-road-review-") as d:
        yield Path(d) / f"answer-{model}.json"


def schema_lines() -> list[str]:
    """The prompt's last section: the object to end the reply with."""
    return ["## Your final message: one JSON object", "",
            "Your final message must be exactly one JSON object matching this schema: no prose, no code fence, "
            "nothing before or after it (anything else is a rerun request). `commit` is the "
            "packet's **Commit under review**, quoted; `notes` holds your Markdown notes. A field the schema does not "
            "require may be left out or `null`.", "",
            "List every required change you can find in this one review, not just the first. Before you answer, "
            "re-scan the diff for further instances of each defect class (other inputs, other call sites, other "
            "files) and for any acceptance line not fully met. A later round should find nothing you could have "
            "reported now.",
            "",
            *NOTES_RULES_LINES,   # M21.35: read right before the answer is written
            "```json", json.dumps(output_schema(), indent=2), "```", ""]


def repair_prompt(refusal: str, kind: str) -> str:
    """A failed answer's repair turn (``review delegate``, M21.35, M21.42): ``refusal`` in a fence longer than any
    backtick run in it. A ``record`` refusal is ``review record``'s whole output, followed by the notes rules and the
    request for the whole corrected object; a ``parse`` one is specy-road's reading of the final message
    (:func:`~specy_road.review_answer.final_answer`'s rerun reason), followed by the request for the whole object
    alone, no fence and nothing after it."""
    fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", refusal)), default=0))
    if kind == "parse":
        return "\n".join(["## Your final message could not be read", "",
                          "specy-road read your final message (this is not `review record`'s output) and filed "
                          "nothing. Its reading:", "", fence, refusal, fence, "",
                          "Send the whole JSON object the review prompt's last section describes as your final "
                          "message: no code fence, no prose, nothing before or after it.", ""])
    return "\n".join(["## Your answer was refused", "",
                      "`review record` refused the JSON object you sent and filed nothing. Its output:", "",
                      fence, refusal, fence, "",
                      "Fix every line it names, by the rules below.", "", *NOTES_RULES_LINES,
                      "Send the whole corrected JSON object as your final message, exactly the one object the "
                      "review prompt's last section describes, with nothing before or after it.", ""])


def reviewer_env(env: dict[str, str]) -> dict[str, str]:
    """``env`` for a reviewer's process: no Python bytecode and no pytest cache, so re-running a test writes nothing,
    and no optional Git locks (``GIT_OPTIONAL_LOCKS=0``), so a read-only ``git status`` neither takes ``index.lock``
    nor refreshes the index, and a Git directory root changes only when the reviewer writes there."""
    addopts = env.get("PYTEST_ADDOPTS", "")
    extra = "" if "no:cacheprovider" in addopts else " -p no:cacheprovider"
    return {**env, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": (addopts + extra).strip(),
            "GIT_OPTIONAL_LOCKS": "0"}


def log_offset(raw: Any) -> int:
    """Where the next byte goes in the run log open as ``raw`` (:func:`append_log`): its size after a flush. An
    attempt's span is two of these, taken by specy-road around the harness's output (:func:`run_text`)."""
    raw.flush()
    return os.fstat(raw.fileno()).st_size


def run_text(log: Path, start: int, end: int, digest: str | None = None) -> str:
    """One attempt's raw output: exactly the log's bytes ``[start, end)``, offsets specy-road took itself before
    the harness started and after it ended (:func:`log_offset`; ``review delegate`` keeps them in each attempt of
    the run record). Nothing the harness prints can create, move or hide an attempt boundary: the marker lines
    specy-road writes are outside the span and only for people reading the log. ``digest`` is the SHA-256 of the
    bytes specy-road wrote there (:class:`SpanWriter`): a span whose bytes differ (the log cut, rewritten or
    appended to by anyone else during the run), or a log shorter than ``end``, gives no output, so a rerun request."""
    try:
        with log.open("rb") as f:
            if os.fstat(f.fileno()).st_size < end:
                return ""
            f.seek(start)
            data = f.read(max(0, end - start))
    except OSError:
        return ""
    if digest is not None and hashlib.sha256(data).hexdigest() != digest:
        return ""
    return data.decode("utf-8", errors="replace")


class SpanWriter:
    """Writes one attempt's output to the run log and keeps its span: ``start`` and ``end`` offsets (:func:`log_offset`)
    and the SHA-256 of every byte written in between, all specy-road's own state (:func:`run_text`)."""

    def __init__(self, raw: Any) -> None:
        self.raw, self.start, self.end = raw, log_offset(raw), log_offset(raw)
        self._sha = hashlib.sha256()

    def write(self, text: str) -> None:
        self.raw.write(text)
        self._sha.update(text.encode("utf-8"))

    def close(self) -> list[Any]:
        """``[start, end, digest]``, the arguments :func:`run_text` takes after the log."""
        self.end = log_offset(self.raw)
        return [self.start, self.end, self._sha.hexdigest()]


@dataclass(frozen=True)
class Outcome:
    """A launched reviewer run's filing: ``exit`` is the harness's exit code (``prompt --channel cli`` exits with
    it when non-zero); only ``recorded`` closes the run complete (:func:`close_review_run`)."""
    state: Literal["recorded", "rerun", "review_failure"]
    reason: str = ""
    path: Path | None = None
    exit: int | None = 0
    refusal: str = ""   # ``review record``'s whole output when it refused the answer (M21.35's repair turn)
    parse: str = ""   # final_answer's rerun reason when the answer itself did not parse (M21.42's repair turn)


def close_review_run(repo_root: Path, t: ReviewTarget, model: str, run: dict[str, Any], filed: Outcome, *,
                     reason: str = "", errors: list[str] | None = None, tail: list[str] | None = None) -> None:
    """Close a launched reviewer's run record from its filing; every close path (``review delegate``, ``prompt
    --channel cli``, an interrupt) comes here with an :class:`Outcome`. ``recorded`` goes through ``close_run``,
    which checks the filed record against the commit; anything else is ``incomplete`` whatever older record of the
    commit is on file, never ``complete`` with no reason, with a reviewer-failure event (M11.72) naming the
    harness's error, or the outcome when the harness ended cleanly. ``reason`` is the caller's (a capacity error)."""
    errors, tail = errors or [], tail or []
    run["outcome"] = filed.state
    if filed.state == "recorded":
        close_run(repo_root, t, model, run, exit_code=filed.exit, errors=errors, tail=tail, reason_prefix=reason)
        return
    run.update(state="incomplete", reason="; ".join(x for x in (reason, filed.reason) if x))
    harness_failed = errors or filed.exit not in (0, None)
    record_reviewer_failure_event(run, harness_error_line(exit_code=filed.exit, errors=errors, tail=tail,
                                                          fallback=filed.reason) if harness_failed else filed.reason)


def _review_record(root: Path, node_id: str, model: str, verdict: str, notes: Path, ref: str | None,
                   launch_mode: str | None, sign_key: Path | None) -> tuple[int, str]:
    """``review record`` itself, its output captured (a ``--json`` caller owns stdout); ``sign_key`` as its
    ``--sign-key``."""
    from specy_road.bundled_scripts.review_cli import cmd_review_record   # deferred: review_cli imports this module's callers
    ns = argparse.Namespace(node_id=node_id, model=model, verdict=verdict, file=str(notes), ref=ref,
                            launch_mode=launch_mode, sign_key=sign_key, repo_root=root)
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cmd_review_record(ns)
    return rc, buf.getvalue().strip()


def file_review(root: Path, node_id: str, model: str, reviews: Path, *, answer: dict[str, Any] | Rerun,
                before: Snapshot, after: Snapshot, ref: str | None = None,
                launch_mode: str | None = None, sign_key: Path | None = None,
                model_check: tuple[str | None, Check] | None = None) -> Outcome:
    """The run's outcome (module docstring); ``answer`` is :func:`final_answer`'s, ``before`` and ``after`` the
    :func:`snapshot` either side of the run; ``sign_key``: ``review record --sign-key``, for ``policy.signed_reviews``;
    ``model_check``: the harness's reported model and :func:`~specy_road.review_model_check.check`'s result, filed as
    ``harness_model`` and, on a mismatch, ``model_mismatch`` (M15.3)."""
    wrote = written(before, after)
    if wrote:
        before.restore(reviews, model)
        return Outcome("review_failure", f"review failure: the reviewer run wrote {', '.join(wrote)}; a reviewer "
                                         "writes nothing, and specy-road files its record")
    if isinstance(answer, Rerun):   # an unreadable run log is an I/O error, not the reviewer's answer: no parse reason
        unreadable = answer.reason.startswith(UNREADABLE_ANSWER.partition("{")[0])
        return Outcome("rerun", answer.reason, parse="" if unreadable else answer.reason)
    record = {k: v for k, v in answer.items() if k != "notes"}
    if model_check and model_check[0]:
        record["harness_model"] = model_check[0]
    if model_check and model_check[1] == "mismatch":
        record["model_mismatch"] = True
    notes = reviews / f"notes-{model}.md"
    replace_file(notes, render_front_matter(record, "\n" + answer["notes"].strip() + "\n"))   # never through a link
    rc, said = _review_record(root, node_id, model, record["verdict"], notes, ref, launch_mode, sign_key)
    if rc != 0:
        return Outcome("rerun", f"rerun requested: review record refused the output: {said[-400:]}", refusal=said)
    return Outcome("recorded", "", review_path(root, node_id, model))


def run_logged(launch: Any, adapter: Any, cwd: Path, log: Path, transcript: list[str] | None = None,
               span: list[int] | None = None) -> int:
    """Run one reviewer turn with :func:`reviewer_env` (over the launch's own ``env``, e.g. M11.62's Claude
    avoid-list), its raw output appended to ``log`` after a marker line for people (and to ``transcript``, which
    ``prompt --channel cli``'s run record keeps: M11.72) and each event's summary echoed to stderr as it arrives.
    ``span`` gets the output's ``[start, end]`` offsets in the log (:func:`run_text`)."""
    span = span if span is not None else []
    with append_log(log) as raw:   # never through a symlink
        raw.write(f"[review prompt] {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} {launch.argv[0]}\n")
        out = SpanWriter(raw)
        span[:] = [out.start, out.start, None]
        note = ""
        try:
            proc = subprocess.Popen(launch.argv, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                                    env=reviewer_env({**os.environ, **(launch.env or {})}),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE if launch.stdin is not None else subprocess.DEVNULL)
        except OSError as e:   # e.g. the harness is not on PATH
            print(f"error: could not launch {launch.argv[0]}: {e.strerror}", file=sys.stderr)
            if transcript is not None:
                transcript.append(f"error: could not launch {launch.argv[0]}: {e.strerror}")
            return 127
        if launch.stdin is not None and proc.stdin:
            try:
                proc.stdin.write(launch.stdin)
                proc.stdin.close()
            except OSError as e:   # the harness quit before reading its prompt
                note = f"[harness closed stdin early: {e}]\n"
        assert proc.stdout is not None
        for line in proc.stdout:
            out.write(line)
            if transcript is not None:
                transcript.append(line.rstrip("\n"))
            for ev in events(adapter, line, launch):   # total: untrusted output (review_answer)
                print(f"{ev.type}: {ev.summary}", file=sys.stderr)
        rc = proc.wait()
        span[:] = out.close()
        raw.write(note)   # specy-road's own note, after the span
        return rc


def delegate_turn(adapter: Any, harness: str, log: Path, cwd: Path, launch: Any) -> dict[str, Any]:
    """``review delegate``'s reviewer turn, run to its end: ``exit``, the reported ``session_id``, the ``errors`` it
    printed, the last lines (``tail``) and its log span (``log_start``, ``log_end``, ``log_sha256``: :func:`run_text`)."""
    out: dict[str, Any] = {"exit": None, "session_id": None, "errors": [], "tail": []}
    # the role and the harness's avoid-list for installed guard hooks (M8.5, M11.62), the launch's own env
    # (Codex: the isolated CODEX_HOME) over that, then no caches (M8.3), as run_logged does for prompt --run
    env = reviewer_env({**harness_env(os.environ, "reviewer", harness=harness), **(launch.env or {})})
    with append_log(log) as raw:   # never through a symlink (review_write_check)
        raw.write(f"[review delegate] {_now()} {launch.argv[0]}\n")   # for people; never parsed
        span = SpanWriter(raw)   # the attempt's span: specy-road's own offsets and digest
        out.update(log_start=span.start, log_end=span.start, log_sha256=None)
        note = ""
        try:
            proc = subprocess.Popen(launch.argv, cwd=cwd, env=env, text=True, encoding="utf-8",
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
                note = f"[review delegate] harness closed stdin early: {e}\n"
        assert proc.stdout is not None
        for line in proc.stdout:
            span.write(line)
            out["tail"] = [*out["tail"][-19:], line.strip()]
            for ev in events(adapter, line, launch):   # total: untrusted output (review_answer)
                out["session_id"] = ev.session_id or out["session_id"]
                if ev.type == "error":
                    out["errors"].append(str((ev.detail or {}).get("message") or ev.summary))
        out["exit"] = proc.wait()
        out["log_start"], out["log_end"], out["log_sha256"] = span.close()
        raw.write(note)   # specy-road's own note, after the span
    return out


def attempt_text(log: Path, attempt: dict[str, Any]) -> str:
    """An attempt's output: the log span specy-road recorded in its own attempt entry (:func:`run_text`); none when
    the attempt has no span (it never launched)."""
    if "log_start" not in attempt:
        return ""
    return run_text(log, attempt["log_start"], attempt["log_end"], attempt.get("log_sha256"))


def run_and_file(launch: Any, adapter: Any, root: Path, model: str, reviews: Path, ref: str | None = None,
                 transcript: list[str] | None = None, sign_key: Path | None = None,
                 output: Path | None = None, cwd: Path | None = None) -> Outcome:
    """``prompt --channel cli --run``'s reviewer turn: run ``launch`` in ``cwd`` (the leaf's worktree; default
    ``root``), compare the model its harness reports with the roster entry's (:mod:`specy_road.review_model_check`),
    then :func:`file_review` it (signed with
    ``sign_key``; ``output``: the :func:`answer_scratch` file the launch writes its answer to). The caller holds
    :func:`review_run_lock` from before it writes any of the run's files, and closes the run record from the
    returned :class:`Outcome`. The node id is the hand-off directory's name; ``transcript`` gets the output and,
    last, the outcome line (but a rerun request after a failed harness), which the reviewer-failure event names."""
    path, cwd = reviews / f"RUN-{model}.log", cwd or root
    before = snapshot(cwd, reviews, model)
    span: list[Any] = [0, 0, None]
    rc = run_logged(launch, adapter, cwd, path, transcript, span)
    text = run_text(path, *span)
    entry, prof = rostered(root, model)
    reported, state = check_run(text, entry, prof)
    if note := check_note(state, reported, model):
        print(note, file=sys.stderr)
    outcome = file_review(root, reviews.name, model, reviews, answer=final_answer(adapter, text, output),
                          before=before, after=snapshot(cwd, reviews, model, before), ref=ref,
                          launch_mode=launch.launch_mode, sign_key=sign_key, model_check=(reported, state))
    print(f"{outcome.state}: {outcome.path or outcome.reason}", file=sys.stderr)
    # The outcome line goes last, for the run record's reviewer-failure event; but a rerun request after a harness
    # failure is that failure's consequence, and the event reads a capacity error from the last plain line only.
    if transcript is not None and outcome.state != "recorded" and not (rc and outcome.state == "rerun"):
        transcript.append(outcome.reason)
    return Outcome(outcome.state, outcome.reason, outcome.path, rc)
