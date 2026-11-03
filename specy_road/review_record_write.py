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
  (:func:`runtime_files`), compared by content as well as size and mtime: any file of the checkout it ran in, git-ignored and ``work/`` files included, any
  file of the leaf's hand-off directory, or a ref (``HEAD``, a branch, a stash). A ``REVIEW-<model>.md`` it
  filed itself is put back as it was, so the gate never counts it. Nothing is filed;
* ``rerun`` — the output is missing, is not a JSON object, does not match the schema, or ``review record``
  refuses it (a wrong commit, an approve with a failing item): a rerun request, never a verdict;
* ``recorded`` — the notes went to ``notes-<model>.md`` and ``review record`` filed the record from them, with
  every check, the roster family and the ``history/`` copy an interactive filing gets.

The walk skips ``.git`` and nested checkouts (a linked worktree under ``work/.worktrees``, a nested repository):
they are other checkouts. Other sessions writing in the same checkout during the run count as the run's writes,
so run reviewers where nothing else writes; :func:`review_run_lock` keeps two reviewer runs of one leaf, whose
hand-off directory is shared, from failing each other. The reviewer's process gets :func:`reviewer_env`, so
re-running Python tests writes no bytecode or pytest cache.
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
from contextlib import redirect_stderr, redirect_stdout
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.git_subprocess import git_text
from specy_road.review_files import HISTORY_DIRNAME, REVIEW_PREFIX, render_front_matter, review_path
from specy_road.runtime_paths import specy_road_package_dir

OUTPUT_SCHEMA_NAME = "review-output.schema.json"
OUTPUT_PREFIX = "OUTPUT-"
LOCK_NAME = ".review-run.lock"
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


def runtime_files(reviews: Path, model: str) -> frozenset[str]:
    """The files a reviewer run may change: its notes and what the adapter writes during the run (the run
    record ``review_delegate.RUN_PREFIX`` names and its temporary copy, the raw log, Codex's ``-o`` file, the
    output schema and :data:`LOCK_NAME`). Prompts and packets are written before the run starts."""
    names = (f"notes-{model}.md", f"RUN-{model}.json", f"RUN-{model}.json.tmp", f"RUN-{model}.log",
             f"{OUTPUT_PREFIX}{model}.json", OUTPUT_SCHEMA_NAME, LOCK_NAME)
    return frozenset(str(reviews / n) for n in names)


def _own_records(reviews: Path, model: str) -> list[Path]:
    """This model's live record, in any case, and its ``history/`` copies."""
    live = [p for p in reviews.iterdir() if p.name.lower() == f"{REVIEW_PREFIX}{model}.md".lower()] \
        if reviews.is_dir() else []
    hist = reviews / HISTORY_DIRNAME
    return live + (sorted(hist.glob(f"*-{model}.md")) if hist.is_dir() else [])


def _content(path: str, is_link: bool) -> str:
    """SHA-256 of the file's bytes (a symlink's target text): a same-length rewrite with its mtime put back
    still differs. ``unreadable`` when it cannot be read (removed mid-walk, no permission)."""
    try:
        if is_link:
            return hashlib.sha256(os.readlink(path).encode()).hexdigest()
        with open(path, "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    except OSError:
        return "unreadable"


def _walk(base: Path, state: dict[str, Any]) -> None:
    """``(size, mtime, content digest)`` of every file under ``base``, ignored ones included; ``.git`` and nested
    checkouts (a directory holding ``.git``) are other repositories' and are skipped."""
    stack = [str(base)]
    while stack:
        try:
            entries = list(os.scandir(stack.pop()))
        except OSError:   # unreadable, or removed while walking
            continue
        for e in entries:
            try:
                if e.name == ".git" or (e.is_dir(follow_symlinks=False) and os.path.lexists(os.path.join(e.path, ".git"))):
                    continue
                if e.is_dir(follow_symlinks=False):
                    stack.append(e.path)
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            state[e.path] = (st.st_size, st.st_mtime_ns, _content(e.path, e.is_symlink()))


@dataclass
class Snapshot:
    """What a reviewer run could write; ``records`` keeps this model's own record bytes, ``exempt``
    :func:`runtime_files`, ``top`` the checkout walked."""
    state: dict[str, Any]
    records: dict[Path, bytes] = field(default_factory=dict)
    exempt: frozenset[str] = frozenset()
    top: Path = Path()

    def restore(self, reviews: Path, model: str) -> None:
        """Put this model's record files back as they were: a record the run filed itself never counts."""
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            p.write_bytes(data)


def snapshot(cwd: Path, reviews: Path, model: str) -> Snapshot:
    """Every file of the checkout at ``cwd`` and of the hand-off directory ``reviews``, plus every ref."""
    top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or cwd).resolve()
    reviews = reviews.resolve()
    state: dict[str, Any] = {"git refs": (git_text(["rev-parse", "HEAD"], top) or "") + "\n"
                             + (git_text(["for-each-ref", "--format=%(refname) %(objectname)"], top) or "")}
    _walk(top, state)
    if top not in reviews.parents:   # a reviewer in a linked worktree: the hand-off directory is the main checkout's
        _walk(reviews, state)
    return Snapshot(state, {p: p.read_bytes() for p in _own_records(reviews, model)}, runtime_files(reviews, model), top)


def written(before: Snapshot, after: Snapshot) -> list[str]:
    """Each path (or ``git refs``) added, removed or changed between the two snapshots, but the run's own
    :func:`runtime_files`; shown relative to the checkout when it is inside it."""
    keys = set(before.state) | set(after.state)
    changed = (k for k in keys if k not in before.exempt and before.state.get(k) != after.state.get(k))
    top = f"{before.top}{os.sep}"
    return sorted(k.removeprefix(top) for k in changed)


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
    """``env`` for a reviewer's process: no Python bytecode and no pytest cache, so re-running a test writes nothing."""
    addopts = env.get("PYTEST_ADDOPTS", "")
    extra = "" if "no:cacheprovider" in addopts else " -p no:cacheprovider"
    return {**env, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": (addopts + extra).strip()}


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
    """``value`` if it is a dict, else the final JSON object of its text, or ``None``. The final object is the last
    complete top-level one; it must start a line (prose and a ```` ```json ```` fence may precede it) and nothing
    after it may open another (``{``): a truncated or malformed later object is a rerun request, never the earlier
    one's verdict. Other trailing text (a closing fence, a harness's status lines) is permitted."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    dec, last, start, end = json.JSONDecoder(), None, 0, 0
    i = value.find("{")
    while i != -1:
        try:
            obj, stop = dec.raw_decode(value, i)
        except ValueError:
            i = value.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            last, start, end = obj, i, stop
        i = value.find("{", stop)
    if last is None or "{" in value[end:] or value[value.rfind("\n", 0, start) + 1:start].strip():
        return None
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
    if isinstance(data, dict) and isinstance(data.get("structured_output"), dict):   # a JSON envelope (claude, agy)
        data = data["structured_output"]
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


def run_logged(launch: Any, adapter: Any, cwd: Path, log: Path, transcript: list[str] | None = None) -> int:
    """Run one reviewer turn with :func:`reviewer_env`, its raw output appended to ``log`` under a :data:`RUN_MARK`
    line (and to ``transcript``, which ``prompt --channel cli``'s run record keeps: M11.72) and each event's
    summary echoed to stderr as it arrives; for ``prompt --channel cli``, whose terminal would otherwise show raw
    JSON lines."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as raw:
        raw.write(f"[review prompt] {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} {launch.argv[0]}\n")
        try:
            proc = subprocess.Popen(launch.argv, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                                    env=reviewer_env(dict(os.environ)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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
                 transcript: list[str] | None = None) -> int:
    """``prompt --channel cli``'s reviewer turn: run ``launch`` under the lock, then :func:`file_review` it;
    0 only when a record was filed. The node id is the hand-off directory's name; ``transcript`` gets the output
    and, last, the outcome line, which the run record's reviewer-failure event then names."""
    out, log = output_path(reviews, model), reviews / f"RUN-{model}.log"
    try:
        with review_run_lock(reviews):
            before = snapshot(root, reviews, model)
            rc = run_logged(launch, adapter, root, log, transcript)
            outcome = file_review(root, reviews.name, model, reviews, before=before,
                                  after=snapshot(root, reviews, model),
                                  output=final_output(adapter, run_text(log), out), ref=ref,
                                  launch_mode=launch.launch_mode)
    except ReviewRunBusy as e:
        print(f"error: {e}", file=sys.stderr)
        if transcript is not None:
            transcript.append(f"error: {e}")
        return 1
    print(f"{outcome.state}: {outcome.path or outcome.reason}", file=sys.stderr)
    if transcript is not None and outcome.state != "recorded":
        transcript.append(outcome.reason)
    return rc or (0 if outcome.state == "recorded" else 1)
