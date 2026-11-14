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

from specy_road import clock, decisions, session_presence
from specy_road.orchestration.workers import (
    worker_lease,
    worker_outbox,
    worker_reconcile,
)
from specy_road.orchestration.workers import worker_state as ws
from specy_road.bundled_scripts import chore_cli, chore_garden
from specy_road.brainstorm_session import (
    BrainstormSession,
    session_path,
    write_session,
)
from specy_road.bundled_scripts.grind_session_events import EventEmitter
from specy_road.bundled_scripts.roadmap_chunk_atomic import AtomicWritePlan
from specy_road.reviewer_run_failure import record_reviewer_failure_event
from specy_road.orchestration.workers.worker_turn_check import TurnWatch

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
    worker_lease.record_hook_prompt(repo, "sid-1", "hello")
    return json.loads(worker_lease.interventions_path(repo, rec.worker_id).read_text())["at"]


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
        "worker_lease_witness",
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


Writer = tuple[Path, Callable[[], object], bytes | None]


def _worker(tmp_path: Path) -> tuple[Path, ws.WorkerRecord]:
    repo = make_review_repo(tmp_path)
    return repo, ws.create_record(repo, "M1.1", "codex", "sol", repo)


def _save_record(tmp_path: Path) -> Writer:
    repo, rec = _worker(tmp_path)
    return ws.record_path(repo, rec.worker_id), lambda: ws.set_lease(repo, rec, "human"), None


def _mailbox_flag(tmp_path: Path) -> Writer:
    repo, rec = _worker(tmp_path)
    path = ws.workers_dir(repo) / "FLAG"
    return path, lambda: ws.append_event(repo, rec, "output", source="worker", summary="x"), None


def _begin_op(tmp_path: Path) -> Writer:
    repo = make_review_repo(tmp_path)
    path = worker_outbox.ops_dir(repo) / "op-1.yaml"
    return path, lambda: worker_outbox.begin_op(repo, "op-1", "delegate", "M1.1"), None


def _complete_op(tmp_path: Path) -> Writer:
    repo = make_review_repo(tmp_path)
    worker_outbox.begin_op(repo, "op-1", "delegate", "M1.1")
    path = worker_outbox.ops_dir(repo) / "op-1.yaml"
    return path, lambda: worker_outbox.complete_op(repo, "op-1", {"note": "café"}), None


def _sync_marks(tmp_path: Path) -> Writer:
    repo, rec = _worker(tmp_path)
    worker_reconcile.sync(repo, ack=True)

    def write() -> None:
        ws.append_event(repo, rec, "output", source="worker", summary="x")
        worker_reconcile.sync(repo, ack=True)

    return ws.workers_dir(repo) / "sync.yaml", write, None


def _presence(tmp_path: Path) -> Writer:
    repo = make_review_repo(tmp_path)
    session_presence.start_session(repo, "agent-1", paths=[])
    path = session_presence.session_path(repo, "agent-1")
    return path, lambda: session_presence.start_session(repo, "agent-1", paths=[], note="é"), None


def _chore(tmp_path: Path, name: str) -> Writer:
    repo = make_review_repo(tmp_path)
    chore_cli.start(repo, "fix-env", task="Repair café", zones=["src"])
    path = chore_cli.chores_dir(repo) / f"fix-env.{name}"
    unicode_bytes = "café".encode() if name == "md" else None
    return path, lambda: chore_cli.close(repo, "fix-env", "done"), unicode_bytes


def _garden(tmp_path: Path) -> Writer:
    repo = make_review_repo(tmp_path)
    return chore_garden.record_path(repo), lambda: chore_garden.garden(repo), None


def _brainstorm(tmp_path: Path) -> Writer:
    session = BrainstormSession(slug="s", topic="café")
    write_session(tmp_path, session)
    return session_path(tmp_path, "s"), lambda: write_session(tmp_path, session), "café".encode()


#: One row per ``atomic_write_text`` call site (``module:function``), each reached through its
#: public caller: ``(the file it writes, a call that writes it, UTF-8 bytes it must contain)``.
#: The row's file exists before the call when the caller replaces one. The roadmap chunk writer
#: has its own tests below, because its rollback removes the temporary file.
WRITERS: dict[str, Callable[[Path], Writer]] = {
    "orchestration/workers/worker_state.py:save_record": _save_record,
    "orchestration/workers/worker_state.py:append_event": _mailbox_flag,
    "orchestration/workers/worker_outbox.py:begin_op": _begin_op,
    "orchestration/workers/worker_outbox.py:complete_op": _complete_op,
    "orchestration/workers/worker_reconcile.py:sync": _sync_marks,
    "session_presence.py:start_session": _presence,
    "bundled_scripts/chore_cli.py:_save": lambda tmp_path: _chore(tmp_path, "json"),
    "bundled_scripts/chore_cli.py:close": lambda tmp_path: _chore(tmp_path, "md"),
    "bundled_scripts/chore_garden.py:garden": _garden,
    "brainstorm_session.py:write_session": _brainstorm,
}
TESTED_APART = {"bundled_scripts/roadmap_chunk_atomic.py:write"}


@pytest.mark.parametrize("writer", WRITERS.values(), ids=WRITERS.keys())
def test_a_writer_keeps_utf8_lf_and_the_umask_mode(tmp_path: Path, writer) -> None:
    path, write, unicode_bytes = writer(tmp_path)
    if path.exists():
        path.chmod(0o600)  # a replaced file takes the new temporary file's mode, not its own
    write()
    raw = path.read_bytes()
    assert raw.decode("utf-8") and b"\r" not in raw
    assert unicode_bytes is None or unicode_bytes in raw
    assert path.stat().st_mode & 0o777 == 0o666 & ~_umask()


@pytest.mark.parametrize("writer", WRITERS.values(), ids=WRITERS.keys())
def test_a_failed_write_leaves_its_temporary_file(tmp_path: Path, monkeypatch, writer) -> None:
    path, write, _ = writer(tmp_path)
    before = path.read_bytes() if path.exists() else None
    replace = os.replace

    def refuse_this_file(src, dst, *args, **kwargs):
        if Path(dst) == path:
            raise OSError(5, "refused by the test", str(dst))
        return replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", refuse_this_file)
    with pytest.raises(OSError):
        write()
    monkeypatch.undo()
    assert (path.read_bytes() if path.exists() else None) == before
    assert [p.name for p in path.parent.glob(f".{path.name}.*.tmp")] == [
        f".{path.name}.{os.getpid()}.tmp"
    ]


def test_every_atomic_text_write_has_a_row() -> None:
    found = {
        site
        for rel, text in _sources()
        if rel != "fs_atomic.py" and "atomic_write_text(" in text
        for site in _call_sites(rel, text, "atomic_write_text")
    }
    assert found == set(WRITERS) | TESTED_APART


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
    "orchestration/workers/worker_lease.py:checkout_id":
        "replaces an invalid id; an absent one is installed by os.link",
    "finish_bookkeeping_undo.py:_restore": "puts back a file's bytes and mode, or a symlink",
    "finish_bookkeeping_undo.py:restore_pre_commit": "puts git's index bytes back",
    "orchestration/workers/worker_sandbox.py:_install_seed":
        "copies bytes over a read-only placeholder, mode 0600",
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


def _call_sites(rel: str, text: str, callee: str) -> list[str]:
    """``module:function`` for each call of ``callee``, by its innermost enclosing function."""
    sites: list[str] = []

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call) and ast.unparse(child.func) == callee:
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
        for site in _call_sites(rel, text, "os.replace")
    }
    stray = sorted(
        s
        for s in found
        if s.split(":")[0] not in OS_REPLACE_ALLOWED and s not in OS_REPLACE_ALLOWED
    )
    assert stray == [], "write through specy_road.fs_atomic.atomic_write_text"
    assert {s.split(":")[0] for s in found} >= {"fs_atomic.py", "safe_write.py"}
