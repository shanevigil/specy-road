"""File a reviewer run's final JSON as ``work/reviews/<NODE_ID>/REVIEW-<model>.md`` (M8.3).

A reviewer started by specy-road (``prompt --channel cli`` on a harness's default reviewer command, or
``review delegate``) writes nothing: it ends its reply with one JSON object shaped by
:func:`output_schema`, the review-record schema less the fields ``review record`` fills, plus ``notes``.
Claude Code validates it with ``--json-schema``, Codex with ``--output-schema`` (and writes it to ``-o``);
on any other harness the last JSON object of the final message is taken (:func:`json_object`).
:func:`file_review` then decides the run's outcome:

* ``review_failure`` — the run wrote something besides its notes: a changed or untracked file in the checkout
  it ran in (outside the project's ``work/``), a moved ``HEAD``, or a ``REVIEW-<model>.md`` it filed itself,
  which is put back as it was so the gate never counts it;
* ``rerun`` — the output is missing, is not a JSON object, does not match the schema, or ``review record``
  refuses it (a wrong commit, an approve with a failing item): a rerun request, never a verdict;
* ``recorded`` — the notes went to ``notes-<model>.md`` and ``review record`` filed the record from them, with
  every check, the roster family and the ``history/`` copy an interactive filing gets.

Paths a run could write that git ignores, other than this model's own record, are not inspected.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.review_files import HISTORY_DIRNAME, REVIEW_PREFIX, render_front_matter, review_path
from specy_road.runtime_paths import project_prefix, specy_road_package_dir

OUTPUT_SCHEMA_NAME = "review-output.schema.json"
OUTPUT_PREFIX = "OUTPUT-"
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


def write_schema(reviews: Path) -> Path:
    """``review-output.schema.json`` in the hand-off directory, for the harness flags that read a file."""
    path = reviews / OUTPUT_SCHEMA_NAME
    reviews.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output_schema(), indent=2) + "\n", encoding="utf-8")
    return path


def output_path(reviews: Path, model: str) -> Path:
    """Where Codex writes the reviewer's last message (``-o``)."""
    return reviews / f"{OUTPUT_PREFIX}{model}.json"


def schema_lines() -> list[str]:
    """The prompt's last section: the object to end the reply with."""
    return ["## Your final message: one JSON object", "",
            "End your reply with exactly one JSON object matching this schema, and nothing after it. `commit` is the "
            "packet's **Commit under review**, quoted; `notes` holds your Markdown notes.", "",
            "```json", json.dumps(output_schema(), indent=2), "```", ""]


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:   # gone, or a directory (a nested repository)
        return "absent"


def _own_records(reviews: Path, model: str) -> list[Path]:
    """This model's live record, in any case, and its ``history/`` copies."""
    live = [p for p in reviews.iterdir() if p.name.lower() == f"{REVIEW_PREFIX}{model}.md".lower()] \
        if reviews.is_dir() else []
    hist = reviews / HISTORY_DIRNAME
    return live + (sorted(hist.glob(f"*-{model}.md")) if hist.is_dir() else [])


@dataclass
class Snapshot:
    """What a reviewer run could write, with a digest each; ``records`` keeps this model's own record bytes."""
    state: dict[str, str]
    records: dict[Path, bytes] = field(default_factory=dict)

    def restore(self, reviews: Path, model: str) -> None:
        """Put this model's record files back as they were: a record the run filed itself never counts."""
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            p.write_bytes(data)


def snapshot(cwd: Path, root: Path, reviews: Path, model: str) -> Snapshot:
    """``HEAD``, every changed or untracked file of the checkout at ``cwd`` outside the project's ``work/``,
    and this model's own record files."""
    top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or cwd)
    state = {"HEAD": git_text(["rev-parse", "HEAD"], top) or ""}
    work = f"{project_prefix(root)}work/"
    toks = iter((git_stdout(["status", "--porcelain=v1", "-z", "--untracked-files=all"], top) or "").split("\0"))
    for tok in toks:
        if len(tok) < 4:
            continue
        if {"R", "C"} & set(tok[:2]):   # a rename or copy: its source path follows
            next(toks, None)
        if not tok[3:].startswith(work):
            state[tok[3:]] = _digest(top / tok[3:])
    records = {p: p.read_bytes() for p in _own_records(reviews, model)}
    state.update({f"{reviews.name}/{p.relative_to(reviews)}": _digest(p) for p in records})
    return Snapshot(state, records)


def written(before: Snapshot, after: Snapshot) -> list[str]:
    """Each path (or ``HEAD``) whose content changed between the two snapshots."""
    keys = set(before.state) | set(after.state)
    return sorted(k for k in keys if before.state.get(k) != after.state.get(k))


def run_text(log: Path) -> str:
    """This turn's raw output: the log after its last :data:`RUN_MARK` line."""
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max((i + 1 for i, line in enumerate(lines) if RUN_MARK.match(line)), default=0)
    return "\n".join(lines[start:])


def final_output(adapter: Any, text: str, output_file: Path | None = None) -> Any:
    """The reviewer's final answer: Codex's ``-o`` file, else the last message the adapter reads from the
    output lines, else the whole output (plain final-message JSON)."""
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
    """``value`` if it is a dict, else the last top-level JSON object in its text (a fenced block counts)."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    dec, last = json.JSONDecoder(), None
    i = value.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(value, i)
        except ValueError:
            i = value.find("{", i + 1)
            continue
        last = obj if isinstance(obj, dict) else last
        i = value.find("{", end)
    return last


@dataclass
class Outcome:
    state: str            # "recorded", "rerun" or "review_failure"
    reason: str = ""
    path: Path | None = None


def _review_record(root: Path, node_id: str, model: str, verdict: str, notes: Path, ref: str | None,
                   launch_mode: str | None) -> tuple[int, str]:
    """``review record`` itself, its output captured (a ``--json`` caller owns stdout)."""
    from specy_road.bundled_scripts.review_cli import cmd_review_record  # noqa: PLC0415 — review_cli imports this module's callers
    ns = argparse.Namespace(node_id=node_id, model=model, verdict=verdict, file=str(notes), ref=ref,
                            launch_mode=launch_mode, sign_key=None, repo_root=root)
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = cmd_review_record(ns)
    return rc, buf.getvalue().strip()


def file_review(root: Path, node_id: str, model: str, reviews: Path, *, output: Any, before: Snapshot,
                after: Snapshot, ref: str | None = None, launch_mode: str | None = None) -> Outcome:
    """The run's outcome (module docstring); ``output`` is :func:`final_output`'s, ``before`` and ``after``
    the :func:`snapshot` either side of the run."""
    wrote = written(before, after)
    if wrote:
        before.restore(reviews, model)
        return Outcome("review_failure", f"review failure: the reviewer run wrote {', '.join(wrote)}; a reviewer "
                                         "writes nothing but its notes, and specy-road files its record")
    data = json_object(output)
    if data is None:
        return Outcome("rerun", "rerun requested: the reviewer's output ends with no JSON object")
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in Draft202012Validator(output_schema()).iter_errors(data)]
    if errors:
        return Outcome("rerun", "rerun requested: the final JSON does not match the review output schema: "
                                + "; ".join(sorted(errors)[:5]))
    record = {k: v for k, v in data.items() if k != "notes"}
    notes = reviews / f"notes-{model}.md"
    notes.write_text(render_front_matter(record, "\n" + data["notes"].strip() + "\n"), encoding="utf-8")
    rc, said = _review_record(root, node_id, model, record["verdict"], notes, ref, launch_mode)
    if rc != 0:
        return Outcome("rerun", f"rerun requested: review record refused the output: {said[-400:]}")
    return Outcome("recorded", "", review_path(root, node_id, model))


def run_logged(launch: Any, adapter: Any, cwd: Path, log: Path) -> int:
    """Run one reviewer turn, its raw output appended to ``log`` under a :data:`RUN_MARK` line and each event's
    summary echoed to stderr; for ``prompt --channel cli``, whose terminal would otherwise show raw JSON lines."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as raw:
        raw.write(f"[review prompt] {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} {launch.argv[0]}\n")
        try:
            proc = subprocess.Popen(launch.argv, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE if launch.stdin is not None else subprocess.DEVNULL)
        except OSError as e:   # e.g. the harness is not on PATH
            print(f"error: could not launch {launch.argv[0]}: {e.strerror}", file=sys.stderr)
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
            for ev in adapter.parse_events(line, launch):
                print(f"{ev.type}: {ev.summary}", file=sys.stderr)
        return proc.wait()
