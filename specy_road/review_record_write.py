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
from specy_road.review_answer import (FILLED_BY_SPECY_ROAD, Rerun, drop_nulls, final_answer,  # noqa: F401 — re-exported
                                      output_schema)
from specy_road.review_files import render_front_matter, review_path
from specy_road.integrity_removals import target_unplanned_removals
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target
from specy_road.review_write_check import (  # re-exported: the post-run write check lives there (file limit)
    LOCK_NAME,
    OUTPUT_SCHEMA_NAME,
    Snapshot,
    snapshot,
    written,
)
from specy_road.reviewer_run_failure import close_run, harness_error_line, record_reviewer_failure_event

#: The line each reviewer turn's raw output starts under in ``RUN-<model>.log``; the last one opens this turn.
RUN_MARK = re.compile(r"^\[review (delegate|prompt)\] ")


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
    path.write_text(json.dumps(strict_schema(*acceptance_keys(root, reviews.name, ref)), indent=2) + "\n",
                    encoding="utf-8")
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
            "```json", json.dumps(output_schema(), indent=2), "```", ""]


class ReviewRunBusy(Exception):
    def __init__(self, node_id: str) -> None:
        super().__init__(f"another reviewer run of {node_id} is in progress; run its reviewers one after another")


@contextlib.contextmanager
def review_run_lock(reviews: Path) -> Iterator[None]:
    """One reviewer run per leaf at a time: the hand-off directory is shared, so a second run's files would read
    as the first run's writes. Raises :class:`ReviewRunBusy` at once rather than wait for a whole review."""
    reviews.mkdir(parents=True, exist_ok=True)
    with (reviews / LOCK_NAME).open("a+") as f:
        try:
            import fcntl  # noqa: PLC0415 — POSIX; Windows has msvcrt
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt  # noqa: PLC0415
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ReviewRunBusy(reviews.name) from None
        except OSError:
            raise ReviewRunBusy(reviews.name) from None
        yield


def reviewer_env(env: dict[str, str]) -> dict[str, str]:
    """``env`` for a reviewer's process: no Python bytecode and no pytest cache, so re-running a test writes nothing,
    and no optional Git locks (``GIT_OPTIONAL_LOCKS=0``), so a read-only ``git status`` neither takes ``index.lock``
    nor refreshes the index, and a Git directory root changes only when the reviewer writes there."""
    addopts = env.get("PYTEST_ADDOPTS", "")
    extra = "" if "no:cacheprovider" in addopts else " -p no:cacheprovider"
    return {**env, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": (addopts + extra).strip(),
            "GIT_OPTIONAL_LOCKS": "0"}


def run_text(log: Path) -> str:
    """This turn's raw output: the log after its last :data:`RUN_MARK` line."""
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max((i + 1 for i, line in enumerate(lines) if RUN_MARK.match(line)), default=0)
    return "\n".join(lines[start:])


@dataclass(frozen=True)
class Outcome:
    """A launched reviewer run's filing: ``exit`` is the harness's exit code (``prompt --channel cli`` exits with
    it when non-zero); only ``recorded`` closes the run complete (:func:`close_review_run`)."""
    state: Literal["recorded", "rerun", "review_failure"]
    reason: str = ""
    path: Path | None = None
    exit: int | None = 0


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
    from specy_road.bundled_scripts.review_cli import cmd_review_record  # noqa: PLC0415 — review_cli imports this module's callers
    ns = argparse.Namespace(node_id=node_id, model=model, verdict=verdict, file=str(notes), ref=ref,
                            launch_mode=launch_mode, sign_key=sign_key, repo_root=root)
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cmd_review_record(ns)
    return rc, buf.getvalue().strip()


def file_review(root: Path, node_id: str, model: str, reviews: Path, *, answer: dict[str, Any] | Rerun,
                before: Snapshot, after: Snapshot, ref: str | None = None,
                launch_mode: str | None = None, sign_key: Path | None = None) -> Outcome:
    """The run's outcome (module docstring); ``answer`` is :func:`final_answer`'s, ``before`` and ``after`` the
    :func:`snapshot` either side of the run; ``sign_key``: ``review record --sign-key``, for ``policy.signed_reviews``."""
    wrote = written(before, after)
    if wrote:
        before.restore(reviews, model)
        return Outcome("review_failure", f"review failure: the reviewer run wrote {', '.join(wrote)}; a reviewer "
                                         "writes nothing, and specy-road files its record")
    if isinstance(answer, Rerun):
        return Outcome("rerun", answer.reason)
    record = {k: v for k, v in answer.items() if k != "notes"}
    notes = reviews / f"notes-{model}.md"
    notes.write_text(render_front_matter(record, "\n" + answer["notes"].strip() + "\n"), encoding="utf-8")
    rc, said = _review_record(root, node_id, model, record["verdict"], notes, ref, launch_mode, sign_key)
    if rc != 0:
        return Outcome("rerun", f"rerun requested: review record refused the output: {said[-400:]}")
    return Outcome("recorded", "", review_path(root, node_id, model))


def run_logged(launch: Any, adapter: Any, cwd: Path, log: Path, transcript: list[str] | None = None) -> int:
    """Run one reviewer turn with :func:`reviewer_env` (over the launch's own ``env``, e.g. M11.62's Claude avoid-list), its raw output appended to ``log`` under a :data:`RUN_MARK`
    line (and to ``transcript``, which ``prompt --channel cli``'s run record keeps: M11.72) and each event's
    summary echoed to stderr as it arrives; for ``prompt --channel cli``, whose terminal would otherwise show raw
    JSON lines."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", newline="") as raw:
        raw.write(f"[review prompt] {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} {launch.argv[0]}\n")
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
                raw.write(f"[harness closed stdin early: {e}]\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            raw.write(line)
            if transcript is not None:
                transcript.append(line.rstrip("\n"))
            for ev in adapter.parse_events(line, launch):
                print(f"{ev.type}: {ev.summary}", file=sys.stderr)
        return proc.wait()


def run_and_file(launch: Any, adapter: Any, root: Path, model: str, reviews: Path, ref: str | None = None,
                 transcript: list[str] | None = None, sign_key: Path | None = None,
                 output: Path | None = None) -> Outcome:
    """``prompt --channel cli``'s reviewer turn: run ``launch``, then :func:`file_review` it (signed with
    ``sign_key``; ``output``: the :func:`answer_scratch` file the launch writes its answer to). The caller holds
    :func:`review_run_lock` from before it writes any of the run's files, and closes the run record from the
    returned :class:`Outcome`. The node id is the hand-off directory's name; ``transcript`` gets the output and,
    last, the outcome line (but a rerun request after a failed harness), which the reviewer-failure event names."""
    path = reviews / f"RUN-{model}.log"
    before = snapshot(root, reviews, model)
    rc = run_logged(launch, adapter, root, path, transcript)
    outcome = file_review(root, reviews.name, model, reviews, answer=final_answer(adapter, run_text(path), output),
                          before=before, after=snapshot(root, reviews, model), ref=ref,
                          launch_mode=launch.launch_mode, sign_key=sign_key)
    print(f"{outcome.state}: {outcome.path or outcome.reason}", file=sys.stderr)
    # The outcome line goes last, for the run record's reviewer-failure event; but a rerun request after a harness
    # failure is that failure's consequence, and the event reads a capacity error from the last plain line only.
    if transcript is not None and outcome.state != "recorded" and not (rc and outcome.state == "rerun"):
        transcript.append(outcome.reason)
    return Outcome(outcome.state, outcome.reason, outcome.path, rc)
