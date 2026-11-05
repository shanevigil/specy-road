"""File a reviewer run's final JSON as ``work/reviews/<NODE_ID>/REVIEW-<model>.md`` (M8.3).

A reviewer started by specy-road (``prompt --channel cli`` or ``review delegate``) writes nothing: it ends its
reply with one JSON object shaped by :func:`output_schema`, the review-record schema less the fields
``review record`` fills, plus ``notes``. Claude Code validates it with ``--json-schema``, Codex with
``--output-schema`` (and writes it to ``-o``), Antigravity's ``agy`` with ``--json-schema``
(:func:`~specy_road.worker_adapter_base.reviewer_cli`); on any other harness the final message's last complete
JSON object is taken, provided it starts a line and no later object was begun (:func:`json_object`), and a JSON
envelope's ``structured_output`` is the answer.
:func:`file_review` then decides the run's outcome:

* ``review_failure`` — the run wrote something besides its notes and the run's own runtime files
  (:func:`runtime_files`), compared by permission mode and content as well as size and mtime: any file of the checkout it ran in, git-ignored and ``work/`` files included, any
  file of the leaf's hand-off directory, the Git metadata a reviewer of this leaf could change (the checkout's
  ``HEAD`` and its reflog, the reviewed branch's ref, reflog and ``packed-refs`` line, a hook, the worktree's
  ``.git`` pointer: :func:`~specy_road.review_write_check._walk_git`), ``HEAD`` or the reviewed branch moving, or the Git index's entries (a
  ``git add``, ``git update-index --assume-unchanged``; a stat refresh by ``git status`` is not one), or the
  transcript ``RUN-<model>.log`` other than by specy-road's appends (:class:`RunLog`). A
  ``REVIEW-<model>.md`` it filed itself is put back as it was, so the gate never counts it. Nothing is filed;
* ``rerun`` — the output is missing, is not a JSON object, does not match the schema, or ``review record``
  refuses it (a wrong commit, an approve with a failing item, no ``sign_key`` under ``policy.signed_reviews``):
  a rerun request, never a verdict;
* ``recorded`` — the notes went to ``notes-<model>.md`` and ``review record`` filed the record from them, with
  every check, the roster family and the ``history/`` copy an interactive filing gets.

The walk skips nested checkouts (a linked worktree under ``work/.worktrees``, a nested repository): they are other
checkouts. Of the Git directories it reads only what :func:`~specy_road.review_write_check._walk_git` names, so an
IDE polling the repository or another worktree committing on another branch is not this run's write. Other sessions writing in the same checkout during the run count as the run's writes,
so run reviewers where nothing else writes; :func:`review_run_lock` keeps two reviewer runs of one leaf, whose
hand-off directory is shared, from failing each other. The reviewer's process gets :func:`reviewer_env`, so
re-running Python tests writes no bytecode or pytest cache.
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
from contextlib import redirect_stderr, redirect_stdout
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.bundled_scripts.generate_brief import index, load_nodes
from specy_road.review_files import render_front_matter, review_path
from specy_road.review_write_check import (  # re-exported: the post-run write check lives there (file limit)
    LOCK_NAME,
    OUTPUT_PREFIX,
    OUTPUT_SCHEMA_NAME,
    RootFence,
    RunLog,
    Snapshot,
    harness_files,
    prepare_harness_files,
    runtime_files,
    snapshot,
    written,
)
from specy_road.reviewer_run_failure import harness_error_line, record_reviewer_failure_event
from specy_road.runtime_paths import specy_road_package_dir

#: Record fields ``review record`` writes itself; a reviewer's output never carries them.
FILLED_BY_SPECY_ROAD = ("family", "independence", "notes_sha256", "signature", "launch_mode")
#: The line each reviewer turn's raw output starts under in ``RUN-<model>.log``; the last one opens this turn.
RUN_MARK = re.compile(r"^\[review (delegate|prompt)\] ")
NOTES_DESCRIPTION = ("Your review notes in Markdown: findings with evidence, the commands you re-ran and their "
                     "results, and `## Excess` when it applies. specy-road writes them below the record's front matter.")


@cache
def output_schema() -> dict[str, Any]:
    """The review-record schema without the fields specy-road fills, plus the reviewer's ``notes``."""
    base = json.loads((specy_road_package_dir() / "schemas" / "review-record.schema.json").read_text(encoding="utf-8"))
    props = {k: v for k, v in base["properties"].items() if k not in FILLED_BY_SPECY_ROAD}
    props["notes"] = {"type": "string", "minLength": 1, "description": NOTES_DESCRIPTION}
    return {"$schema": base["$schema"], "title": "specy-road reviewer output",
            "description": "One reviewer's verdict as its final message; specy-road files it as REVIEW-<model>.md.",
            "type": "object", "required": [*base["required"], "notes"], "additionalProperties": False,
            "properties": props, "$defs": base["$defs"]}


def strict_schema(ids: list[str]) -> dict[str, Any]:
    """:func:`output_schema` in OpenAI strict structured-output form, which Codex's ``--output-schema`` is sent in:
    every object lists all its properties as required and allows no others, so an optional field becomes required
    and may be ``null`` (:func:`drop_nulls` removes it again), and ``acceptance`` names exactly the leaf's ``ids``
    (strict mode has no free-key map or ``propertyNames``). Anything it admits, less its nulls, is
    :func:`output_schema`-valid but for the checks it cannot carry, which the validator still makes."""
    base = output_schema()
    props = {k: v if k in base["required"] else {"anyOf": [v, {"type": "null"}]} for k, v in base["properties"].items()}
    acc = base["properties"]["acceptance"]
    props["acceptance"] = {"type": "object", "description": acc["description"], "additionalProperties": False,
                           "required": list(ids), "properties": {a: acc["additionalProperties"] for a in ids}}
    return {**base, "required": list(props), "properties": props}


def drop_nulls(data: dict[str, Any]) -> dict[str, Any]:
    """``data`` without the optional fields :func:`strict_schema` let the reviewer answer ``null``."""
    return {k: v for k, v in data.items() if v is not None or k in output_schema()["required"]}


def write_schema(root: Path, reviews: Path) -> Path:
    """``review-output.schema.json`` in the hand-off directory, for the harness flags that read a file: the
    :func:`strict_schema` of the leaf the directory is named for, which Codex needs and the others accept. It is
    not in :func:`runtime_files`: callers write it under :func:`review_run_lock`, before the run's first snapshot."""
    path = reviews / OUTPUT_SCHEMA_NAME
    reviews.mkdir(parents=True, exist_ok=True)
    ids = acceptance_ids(index(load_nodes(root))[reviews.name])
    path.write_text(json.dumps(strict_schema(ids), indent=2) + "\n", encoding="utf-8")
    return path


def output_path(reviews: Path, model: str) -> Path:
    """Where Codex writes the reviewer's last message (``-o``)."""
    return reviews / f"{OUTPUT_PREFIX}{model}.json"


def schema_lines() -> list[str]:
    """The prompt's last section: the object to end the reply with."""
    return ["## Your final message: one JSON object", "",
            "End your reply with exactly one JSON object matching this schema, and nothing after it. `commit` is the "
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


def final_output(adapter: Any, text: str, output_file: Path | None = None) -> Any:
    """The reviewer's final answer: Codex's ``-o`` file, else the last answer event the adapter reads from the
    output lines (one with no valid answer, ``""``, replaces an earlier one: a rerun request), else the whole
    output (plain final-message JSON)."""
    if output_file is not None and output_file.is_file():
        saved = output_file.read_text(encoding="utf-8", errors="replace")
        if saved.strip():
            return saved
    found = None
    for line in text.splitlines():
        msg = adapter.final_message(line)
        found = msg if msg is not None else found
    return found if found is not None else text


def json_object(value: Any) -> dict[str, Any] | None:
    """``value`` if it is a dict, else the final JSON object of its text, or ``None``. The final object is the last
    complete top-level one; it must start a line (prose and a ```` ```json ```` fence may precede it), nothing
    after it may open another object (``{``) or a JSON array (:func:`_later_array`): a truncated or malformed later
    object or array is a rerun request, never the earlier one's verdict; and it must not sit inside an object or
    array left open before it (:func:`_open_braces`): a complete object nested in malformed outer JSON, or in an
    array, is a rerun request too. Other trailing text (a closing fence, a harness's status lines) is permitted."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    dec, spans = json.JSONDecoder(), []
    i = value.find("{")
    while i != -1:
        try:
            obj, stop = dec.raw_decode(value, i)
        except ValueError:
            i = value.find("{", i + 1)
            continue
        spans.append((i, stop, obj))
        i = value.find("{", stop)
    if not spans:
        return None
    start, end, last = spans[-1]
    if ("{" in value[end:] or _later_array(value[end:]) or value[value.rfind("\n", 0, start) + 1:start].strip()
            or _open_braces(value, spans)):
        return None
    return last


_ARRAY_LINE = re.compile(r"^[ \t]*\[", re.M)
_JSON_VALUE = re.compile(r"\s*(?:[\[{\"\-\d\]]|(?:true|false|null)\b)")


def _later_array(tail: str) -> bool:
    """Whether ``tail``, the text after the final object, has a line that starts a JSON array: one that opens with
    a JSON value (complete or not: ``[1,``, ``[]``) or never closes (``[``, ``[broken``). A later array, like a
    later object, is a rerun request; a closed bracket of prose (``[INFO] done``, ``[the docs](x)``) is not."""
    for line in _ARRAY_LINE.finditer(tail):
        at = line.end()
        if _JSON_VALUE.match(tail, at) or _depth(tail[at - 1:]):
            return True
    return False


def _depth(text: str, depth: int = 0) -> int:
    """``depth`` after ``text``: ``{`` or ``[`` adds one, ``}`` or ``]`` takes one away but never below none."""
    for ch in text:
        depth = depth + 1 if ch in "{[" else max(0, depth - 1) if ch in "}]" else depth
    return depth


def _open_braces(value: str, spans: list[tuple[int, int, Any]]) -> bool:
    """Whether an object or array opened outside the complete objects (``spans``) is still open where the last one
    starts: ``{`` or ``[`` adds one, ``}`` or ``]`` takes one away but never below none, so balanced prose
    (``use {x}``, ``[link]``) and a stray ``}`` leave the final object at top level, and an unterminated outer
    object, or any array around it, does not."""
    depth, pos = 0, 0
    for begin, stop, _obj in spans:
        depth, pos = _depth(value[pos:begin], depth), stop
    return depth > 0


@dataclass
class Outcome:
    state: str            # "recorded", "rerun" or "review_failure"
    reason: str = ""
    path: Path | None = None


def close_unfiled(run: dict[str, Any], filed: Outcome, reason: str = "", *, exit_code: int | None,
                  errors: list[str], tail: list[str]) -> None:
    """Close the run of a review failure or rerun request: incomplete whatever older record of the commit is on
    file, with a reviewer-failure event (M11.72) naming the harness's error, or the outcome when the harness ended
    cleanly; ``reason`` is the caller's own (a capacity error)."""
    run.update(state="incomplete", outcome=filed.state, reason="; ".join(x for x in (reason, filed.reason) if x))
    harness_failed = errors or exit_code not in (0, None)
    record_reviewer_failure_event(run, harness_error_line(exit_code=exit_code, errors=errors, tail=tail,
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


def file_review(root: Path, node_id: str, model: str, reviews: Path, *, output: Any, before: Snapshot,
                after: Snapshot, ref: str | None = None, launch_mode: str | None = None,
                fenced: bool = False, log: RunLog | None = None, sign_key: Path | None = None) -> Outcome:
    """The run's outcome (module docstring); ``output`` is :func:`final_output`'s, ``before`` and ``after``
    the :func:`snapshot` either side of the run; ``fenced``: a :class:`RootFence` saw the hand-off root move
    during a harness turn (a file created, renamed or deleted there); ``log``: the run's :class:`RunLog`, a write
    when it :meth:`~RunLog.changed`; ``sign_key``: ``review record --sign-key``, for ``policy.signed_reviews``."""
    top = f"{before.top}{os.sep}"
    shown = str(reviews.resolve()).removeprefix(top)
    wrote = sorted({*written(before, after), *([shown] if fenced else []),
                    *([str(log.path.resolve()).removeprefix(top)] if log is not None and log.changed() else [])})
    if wrote:
        before.restore(reviews, model)
        return Outcome("review_failure", f"review failure: the reviewer run wrote {', '.join(wrote)}; a reviewer "
                                         "writes nothing but its notes, and specy-road files its record")
    data = json_object(output)
    if isinstance(data, dict) and isinstance(data.get("structured_output"), dict):   # a JSON envelope (claude, agy)
        data = data["structured_output"]
    if data is None:
        return Outcome("rerun", "rerun requested: the reviewer's output ends with no JSON object")
    data = drop_nulls(data)
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in Draft202012Validator(output_schema()).iter_errors(data)]
    if errors:
        return Outcome("rerun", "rerun requested: the final JSON does not match the review output schema: "
                                + "; ".join(sorted(errors)[:5]))
    record = {k: v for k, v in data.items() if k != "notes"}
    notes = reviews / f"notes-{model}.md"
    notes.write_text(render_front_matter(record, "\n" + data["notes"].strip() + "\n"), encoding="utf-8")
    rc, said = _review_record(root, node_id, model, record["verdict"], notes, ref, launch_mode, sign_key)
    if rc != 0:
        return Outcome("rerun", f"rerun requested: review record refused the output: {said[-400:]}")
    return Outcome("recorded", "", review_path(root, node_id, model))


def run_logged(launch: Any, adapter: Any, cwd: Path, log: RunLog, transcript: list[str] | None = None) -> int:
    """Run one reviewer turn with :func:`reviewer_env` (over the launch's own ``env``, e.g. M11.62's Claude avoid-list), its raw output appended to ``log`` under a :data:`RUN_MARK`
    line (and to ``transcript``, which ``prompt --channel cli``'s run record keeps: M11.72) and each event's
    summary echoed to stderr as it arrives; for ``prompt --channel cli``, whose terminal would otherwise show raw
    JSON lines."""
    with log.open() as raw:
        log.write(raw, f"[review prompt] {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} {launch.argv[0]}\n")
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
                log.write(raw, f"[harness closed stdin early: {e}]\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            log.write(raw, line)
            if transcript is not None:
                transcript.append(line.rstrip("\n"))
            for ev in adapter.parse_events(line, launch):
                print(f"{ev.type}: {ev.summary}", file=sys.stderr)
        return proc.wait()


def run_and_file(launch: Any, adapter: Any, root: Path, model: str, reviews: Path, ref: str | None = None,
                 transcript: list[str] | None = None, sign_key: Path | None = None,
                 filed: list[Outcome] | None = None) -> int:
    """``prompt --channel cli``'s reviewer turn: run ``launch``, then :func:`file_review` it (signed with
    ``sign_key``, the :class:`Outcome` appended to ``filed`` for the run record); 0 only when a record was filed. The caller holds :func:`review_run_lock` from before it writes
    any of the run's files. The node id is the hand-off directory's name; ``transcript`` gets the output
    and, last, the outcome line (but a rerun request after a failed harness), which the run record's
    reviewer-failure event then names."""
    out, path = output_path(reviews, model), reviews / f"RUN-{model}.log"
    path.touch()   # created now, so the turn's appends move nothing in the hand-off root
    prepare_harness_files(reviews, model)   # and the answer and notes, written in place during the turn
    before, log = snapshot(root, reviews, model, ref), RunLog(path)
    fence = RootFence(reviews, model)
    rc = run_logged(launch, adapter, root, log, transcript)
    outcome = file_review(root, reviews.name, model, reviews, before=before, after=snapshot(root, reviews, model, ref),
                          output=final_output(adapter, run_text(path), out), ref=ref, launch_mode=launch.launch_mode,
                          fenced=fence.moved(), log=log, sign_key=sign_key)
    print(f"{outcome.state}: {outcome.path or outcome.reason}", file=sys.stderr)
    if filed is not None:
        filed.append(outcome)
    # The outcome line goes last, for the run record's reviewer-failure event; but a rerun request after a harness
    # failure is that failure's consequence, and the event reads a capacity error from the last plain line only.
    if transcript is not None and outcome.state != "recorded" and not (rc and outcome.state == "rerun"):
        transcript.append(outcome.reason)
    return rc or (0 if outcome.state == "recorded" else 1)
