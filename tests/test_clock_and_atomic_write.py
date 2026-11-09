"""One clock (``specy_road.clock``) and one atomic text writer (``specy_road.fs_atomic``).

Each replaced timestamp keeps the type and string form it had before the move, each replaced
writer keeps its encoding, newline handling, file mode and failure leftovers, and two source
scans keep new copies out.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from tests.decisions_repo_helpers import decisions_repo
from tests.review_repo_helpers import make_review_repo
from tests.worker_lease_helpers import idle_worker

from specy_road import (
    clock,
    decisions,
    session_presence,
    worker_lease,
    worker_outbox,
    worker_witness,
)
from specy_road import worker_state as ws
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormSession,
    session_path,
    write_session,
)
from specy_road.bundled_scripts.grind_session_events import EventEmitter
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.reviewer_run_failure import record_reviewer_failure_event
from specy_road.worker_turn_check import TurnWatch

PACKAGE = Path(__file__).resolve().parents[1] / "specy_road"
FROZEN = datetime(2026, 11, 9, 1, 2, 3, 456789, tzinfo=timezone.utc)
SECOND = "2026-11-09T01:02:03+00:00"


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # the package only ever asks for UTC
        return FROZEN


@pytest.fixture
def frozen(monkeypatch) -> None:
    monkeypatch.setattr(clock, "datetime", FrozenDatetime)


def _grind_event(tmp_path: Path) -> Any:
    out = io.StringIO()
    with redirect_stdout(out):
        EventEmitter(as_json=True).emit("started")
    return json.loads(out.getvalue())["ts"]


def _record(tmp_path: Path) -> Any:
    repo = make_review_repo(tmp_path)
    return ws.create_record(repo, "M1.1", "codex", "sol", repo).updated


def _op(tmp_path: Path) -> Any:
    repo = make_review_repo(tmp_path)
    worker_outbox.begin_op(repo, "op-1", "delegate", "M1.1")
    return yaml.safe_load((worker_outbox.ops_dir(repo) / "op-1.yaml").read_text(encoding="utf-8"))[
        "at"
    ]


def _presence(tmp_path: Path) -> Any:
    return session_presence.start_session(make_review_repo(tmp_path), "agent-1", paths=[]).started


def _lease(tmp_path: Path) -> Any:
    repo = make_review_repo(tmp_path)
    rec, _ = worker_lease.handoff(repo, idle_worker(repo, "M1.1").worker_id)
    return rec.lease["since"]


def _witness(tmp_path: Path) -> Any:
    repo = make_review_repo(tmp_path)
    rec, _ = worker_lease.handoff(repo, idle_worker(repo, "M1.1", "sid-1").worker_id)
    worker_witness.record_hook_prompt(repo, "sid-1", "hello")
    return json.loads(worker_witness.interventions_path(repo, rec.worker_id).read_text())["at"]


def _reviewer_failure(tmp_path: Path) -> Any:
    run: dict[str, Any] = {}
    record_reviewer_failure_event(run, "boom")
    return run["events"][0]["at"]


def _superseded(tmp_path: Path) -> Any:
    repo = decisions_repo(tmp_path)
    decisions.add_preference(repo, summary="first", role="executor")
    decisions.add_preference(repo, summary="second", role="executor", supersedes="P1")
    doc = decisions.read_decisions(decisions.decisions_path(repo, False))
    return next(e for e in doc["entries"] if e["id"] == "P1")["closed"]


def _turn_clock(tmp_path: Path) -> Any:
    repo = make_review_repo(tmp_path)
    return TurnWatch(repo, ws.create_record(repo, "M1.1", "codex", "sol", repo)).now()


@pytest.mark.parametrize(
    ("read", "expected"),
    [
        (_grind_event, "2026-11-09T01:02:03Z"),
        (_record, SECOND),
        (_op, SECOND),
        (_presence, SECOND),
        (_lease, SECOND),
        (_witness, SECOND),
        (_reviewer_failure, SECOND),
        (_superseded, SECOND),
        (_turn_clock, FROZEN),
    ],
    ids=[
        "grind_session_events",
        "worker_state",
        "worker_outbox",
        "session_presence",
        "worker_lease",
        "worker_witness",
        "reviewer_run_failure",
        "decisions",
        "worker_turn_check",
    ],
)
def test_each_timestamp_keeps_its_type_and_form(
    tmp_path: Path, frozen, read: Callable[[Path], Any], expected: Any
) -> None:
    got = read(tmp_path)
    assert type(got) is type(expected) and got == expected


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _record_writer(tmp_path: Path) -> tuple[Path, Callable[[], None], bytes | None]:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "codex", "sol", repo)
    return ws.record_path(repo, rec.worker_id), lambda: ws.set_lease(repo, rec, "human"), None


def _op_writer(tmp_path: Path) -> tuple[Path, Callable[[], None], bytes | None]:
    repo = make_review_repo(tmp_path)
    worker_outbox.begin_op(repo, "op-1", "delegate", "M1.1")
    path = worker_outbox.ops_dir(repo) / "op-1.yaml"
    return path, lambda: worker_outbox.complete_op(repo, "op-1", {"note": "café"}), None


def _presence_writer(tmp_path: Path) -> tuple[Path, Callable[[], None], bytes | None]:
    repo = make_review_repo(tmp_path)
    path = session_presence.session_path(repo, "agent-1")
    return (
        path,
        lambda: session_presence.start_session(repo, "agent-1", paths=[], note="café"),
        None,
    )


def _brainstorm_writer(tmp_path: Path) -> tuple[Path, Callable[[], None], bytes | None]:
    session = BrainstormSession(slug="s", topic="café")
    return session_path(tmp_path, "s"), lambda: write_session(tmp_path, session), "café".encode()


WRITERS = [_record_writer, _op_writer, _presence_writer, _brainstorm_writer]
WRITER_IDS = ["worker_state", "worker_outbox", "session_presence", "brainstorm_session"]


@pytest.mark.parametrize("writer", WRITERS, ids=WRITER_IDS)
def test_a_writer_keeps_utf8_lf_and_the_umask_mode(tmp_path: Path, writer) -> None:
    path, write, unicode_bytes = writer(tmp_path)
    write()
    path.chmod(0o600)  # a replaced file takes the new temporary file's mode, not its own
    write()
    raw = path.read_bytes()
    assert raw.decode("utf-8") and b"\r" not in raw and raw.endswith(b"\n")
    assert unicode_bytes is None or unicode_bytes in raw
    assert path.stat().st_mode & 0o777 == 0o666 & ~_umask()


@pytest.mark.parametrize("writer", WRITERS, ids=WRITER_IDS)
def test_a_failed_write_leaves_its_temporary_file(tmp_path: Path, writer) -> None:
    path, write, _ = writer(tmp_path)
    path.unlink(missing_ok=True)
    # A rename onto a non-empty directory fails after the temporary file is written.
    (path / "occupied").mkdir(parents=True)
    with pytest.raises(OSError):
        write()
    assert [p.name for p in path.parent.glob(f".{path.name}.*.tmp")] == [
        f".{path.name}.{os.getpid()}.tmp"
    ]


def test_a_roadmap_write_failing_on_its_second_file_restores_the_first_and_leaves_no_temporary_file(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    first.write_bytes(b"before\r\n")
    (second / "occupied").mkdir(parents=True)
    plan = AtomicWritePlan(tmp_path)
    plan.stage_text(first, "café\n")
    plan.stage_text(second, "x\n")
    with pytest.raises(OSError):
        plan.commit(lambda: None)
    assert first.read_bytes() == b"before\r\n"
    assert not [p for p in tmp_path.iterdir() if ".tmp" in p.name]


def test_a_roadmap_write_keeps_utf8_lf_and_the_umask_mode(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text("old\n", encoding="utf-8")
    path.chmod(0o600)
    plan = AtomicWritePlan(tmp_path)
    plan.stage_text(path, "café\n")
    plan.commit(lambda: None)
    assert path.read_bytes() == "café\n".encode()
    assert path.stat().st_mode & 0o777 == 0o666 & ~_umask()


#: The wall clock is read in :mod:`specy_road.clock` only.
CLOCK_CALL = re.compile(r"\.now\(\s*(?:datetime\.)?timezone\.utc\s*\)|\.utcnow\(")

#: Where ``os.replace(`` may appear: a whole module, or ``module:function`` for one specialised
#: installer that is not a text write.
OS_REPLACE_ALLOWED = {
    "fs_atomic.py": "the shared atomic text writer",
    "safe_write.py": "descriptor-anchored writes that refuse symlinks on the path",
    "review_write_check.py:replace_file": "never writes through a symlink at the file or a parent",
    "worker_lease.py:checkout_id": "replaces an invalid id; an absent one is installed by os.link",
    "finish_bookkeeping_undo.py:_restore": "puts back a file's bytes and mode, or a symlink",
    "finish_bookkeeping_undo.py:restore_pre_commit": "puts git's index bytes back",
    "worker_sandbox.py:_install_seed": "copies bytes over a read-only placeholder, mode 0600",
}


def _sources() -> list[tuple[str, str]]:
    return [
        (p.relative_to(PACKAGE).as_posix(), p.read_text(encoding="utf-8"))
        for p in sorted(PACKAGE.rglob("*.py"))
    ]


def test_the_wall_clock_is_read_only_in_clock_py() -> None:
    found = [
        f"{rel}:{text.count(chr(10), 0, m.start()) + 1}"
        for rel, text in _sources()
        if rel != "clock.py"
        for m in CLOCK_CALL.finditer(text)
    ]
    assert found == [], "use specy_road.clock.utc_now() or utc_now_iso()"


def _replace_sites(rel: str, text: str) -> list[str]:
    """``module:function`` for each ``os.replace`` call, by its innermost enclosing function."""
    sites: list[str] = []

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call) and ast.unparse(child.func) == "os.replace":
                sites.append(f"{rel}:{owner}")
            visit(
                child,
                child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else owner,
            )

    visit(ast.parse(text), "<module>")
    return sites


def test_os_replace_is_only_in_fs_atomic_and_the_allowlist() -> None:
    found = {
        site
        for rel, text in _sources()
        if "os.replace(" in text
        for site in _replace_sites(rel, text)
    }
    stray = sorted(
        s
        for s in found
        if s.split(":")[0] not in OS_REPLACE_ALLOWED and s not in OS_REPLACE_ALLOWED
    )
    assert stray == [], "write through specy_road.fs_atomic.atomic_write_text"
    assert {s.split(":")[0] for s in found} >= {"fs_atomic.py", "safe_write.py"}
