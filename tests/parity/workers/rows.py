"""The worker table: one fixture repo per row, each driven through ``specy-road worker``.

Every row starts from :func:`tests.worker_repo_helpers.make_worker_repo` (leaf ``M1.1`` claimed on
``feature/rm-thing``, the main checkout on that branch, a roster whose ``opus`` runs a fake harness
on ``claude-code``) and runs the steps of one existing worker test: delegate, sync, message,
handoff, reclaim, terminate, reconcile, slot counting under ``max_workers``, a dead or closed
worker's lease released by ``sync`` (a lease ends with its worker; there is no time-based expiry),
an op left pending by a crash and a replayed op, and the prompt-submit hook of each harness.
``golden/<row>.txt`` holds each step's exit code and output, then every file under
``work/.workers/`` (the record, its event log, interventions, ops) and the row's lease refs, as
recorded before the worker modules were folded. The table imports only modules that exist before
and after that fold, so it passes on both.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import worker_cli
from specy_road.orchestration.workers import worker_lease as lease
from specy_road.orchestration.workers import worker_state as ws
from tests.parity.process.corpus import step_transcript
from tests.worker_cli_helpers import wait_for_worker
from tests.worker_lease_helpers import idle_worker, remote_and_clone, remote_leases
from tests.worker_repo_helpers import make_worker_repo

GOLDEN = Path(__file__).resolve().parent / "golden"
NODE = "M1.1"
#: Record fields that follow the machine, the process or the clock: shown as ``<MASKED>`` when set.
_VOLATILE = frozenset({
    "pid", "pgid", "harness_pid", "harness_start", "wrapper_token", "started_head", "contract_hash",
    "created", "updated", "last_output_at", "at", "git_head", "toolkit_version", "duration_ms",
    "duration_api_ms", "inputs",
})
_PID = re.compile(r"\b((?:pid|pgid|group)\\?\"?:?) \d+")
#: A digest of the prompt, which names the fixture's temp paths.
_HASH = re.compile(r"\b[0-9a-f]{64}\b")
#: A session id the adapter chose for the launch (``claude --session-id``).
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


@dataclass(frozen=True)
class Row:
    """``run(repo, tmp, steps)`` drives the row; ``steps`` collects each step's transcript."""

    name: str
    run: Callable[[Path, Path, list[str]], dict[str, Path]]
    max_workers: int = 2


def _cli(repo: Path, steps: list[str], *argv: str, stdin: str | None = None) -> int:
    """``specy-road worker <argv>`` in this process; its exit code and output join ``steps``."""
    full = ["worker", *argv, "--repo-root", str(repo)]
    out, err, old_stdin = io.StringIO(), io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(stdin or "")
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                pytest.raises(SystemExit) as e:
            worker_cli.main(full)
    finally:
        sys.stdin = old_stdin
    code = e.value.code or 0
    steps.append(json.dumps(
        {"argv": argv, "exit": code, "out": out.getvalue(), "err": err.getvalue()}
    ))
    return code


def _delegated(repo: Path, steps: list[str]) -> ws.WorkerRecord:
    _cli(repo, steps, "delegate", NODE, "--model", "opus")
    return wait_for_worker(repo, "w-0001")


def _delegate(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    _delegated(repo, steps)
    # The leaf's worker is returned, not duplicated.
    _cli(repo, steps, "delegate", NODE, "--model", "opus")
    return {}


def _sync(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    _cli(repo, steps, "sync")
    _delegated(repo, steps)
    _cli(repo, steps, "sync", "--ack")
    _cli(repo, steps, "sync")
    return {}


def _message(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    _delegated(repo, steps)
    _cli(repo, steps, "message", "w-0001", "--text", "also update docs")
    wait_for_worker(repo, "w-0001")
    return {}


def _handoff(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    _delegated(repo, steps)
    _cli(repo, steps, "handoff", "w-0001")
    _cli(repo, steps, "message", "w-0001", "--text", "x")   # the human holds the lease
    return {}


def _reclaim(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    _delegated(repo, steps)
    _cli(repo, steps, "handoff", "w-0001")
    (repo / "src" / "b.py").write_text("x\n")
    _cli(repo, steps, "reclaim", "w-0001", "--note", "told it to use sqlite")
    _cli(repo, steps, "reclaim", "w-0001")   # not handed off now
    return {}


def _terminate(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    _delegated(repo, steps)
    _cli(repo, steps, "terminate", "w-0001")
    _cli(repo, steps, "message", "w-0001", "--text", "x")   # a terminated worker takes no turn
    return {}


def _reconcile(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    rec = _delegated(repo, steps)
    ws.take_checkpoint(repo, rec)
    _cli(repo, steps, "reconcile", "w-0001", "--json")
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "outside.md").write_text("outside the touch zones\n")
    _cli(repo, steps, "reconcile", "w-0001", "--json")
    return {}


def _slots(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    """One slot, held by an idle record: a second leaf is refused, the first leaf's worker
    returned."""
    rec = ws.create_record(repo, NODE, "generic", "x", repo)
    ws.set_state(repo, rec, "idle")
    phase = repo / "roadmap" / "phases" / "M1.json"
    nodes = json.loads(phase.read_text())
    second = copy.deepcopy(nodes["nodes"][0])
    second.update(id="M1.2", codename="other", node_key="22222222-2222-5222-8222-222222222222",
                  planning_dir="planning/M1.2_other.md")
    nodes["nodes"].append(second)
    phase.write_text(json.dumps(nodes))
    _cli(repo, steps, "delegate", "M1.2", "--model", "opus")
    _cli(repo, steps, "delegate", NODE, "--model", "opus", "--json")
    return {}


def _lease_expiry(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    """A dead worker's and a closed worker's leases are released by ``sync``."""
    remote, clone = remote_and_clone(tmp, repo)
    dead, closed = idle_worker(repo, NODE), idle_worker(repo, "M1.2", "sid-2")
    for rec in (dead, closed):
        lease.acquire_lease(repo, rec, new=True)
    ws.set_state(repo, dead, "running", pid=None)   # its wrapper is gone
    ws.set_state(repo, closed, "failed", pid=None)   # closed without its lease released
    steps.append(json.dumps({"leases_before": remote_leases(remote)}))
    _cli(repo, steps, "sync")
    steps.append(json.dumps({"leases_after": remote_leases(remote)}))
    return {"remote": remote, "clone": clone}


def _outbox_replay(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
    """An op a crash left pending is refused on retry; a finished op answers from its first
    result."""
    ws.begin_op(repo, "op-1", "delegate", NODE, {"model": "opus"})   # the crash: never completed
    _cli(repo, steps, "delegate", NODE, "--model", "opus", "--op-id", "op-1")
    _cli(repo, steps, "delegate", NODE, "--model", "opus", "--op-id", "op-2", "--json")
    wait_for_worker(repo, "w-0001")
    _cli(repo, steps, "delegate", NODE, "--model", "opus", "--op-id", "op-2", "--json")
    _cli(repo, steps, "delegate", NODE, "--model", "sol", "--op-id", "op-2")   # other arguments
    return {}


def _hook(harness: str, payload_key: str) -> Callable[[Path, Path, list[str]], dict[str, Path]]:
    def run(repo: Path, tmp: Path, steps: list[str]) -> dict[str, Path]:
        rec = ws.create_record(repo, NODE, harness, "opus", repo)
        ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
        ws.set_state(repo, rec, "idle", pid=None)
        ws.set_lease(repo, ws.load_record(repo, rec.worker_id), "human")
        _cli(repo, steps, "hook", "--format", harness, "--print-config")
        _cli(repo, steps, "hook", "--format", harness,
             stdin=json.dumps({payload_key: "sid-1", "prompt": "do not add an abstraction"}))
        _cli(repo, steps, "hook", "--format", harness,
             stdin=json.dumps({payload_key: "someone-else", "prompt": "ignored"}))
        _cli(repo, steps, "hook", "--format", harness, stdin="not json")
        return {}
    return run


ROWS = (
    Row("delegate", _delegate),
    Row("sync", _sync),
    Row("message", _message),
    Row("handoff", _handoff),
    Row("reclaim", _reclaim),
    Row("terminate", _terminate),
    Row("reconcile", _reconcile),
    Row("slots_max_workers", _slots, max_workers=1),
    Row("lease_expiry", _lease_expiry),
    Row("outbox_replay_after_crash", _outbox_replay),
    Row("hook_claude_code", _hook("claude-code", "session_id")),
    Row("hook_codex", _hook("codex", "session_id")),
    Row("hook_cursor", _hook("cursor", "conversation_id")),
)


def _masked(value: object) -> object:
    if isinstance(value, dict):
        return {
            k: ("<MASKED>" if k in _VOLATILE and v is not None else _masked(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_masked(v) for v in value]
    return value


def _state_files(repo: Path) -> str:
    """Every file under ``work/.workers/``, parsed and masked; the lock, mailbox and log files by
    name only."""
    root = ws.workers_dir(repo)
    parts = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".yaml":
            body = json.dumps(_masked(yaml.safe_load(text)), indent=2, sort_keys=True)
        elif path.suffix == ".jsonl":
            body = "\n".join(
                json.dumps(_masked(json.loads(line)), sort_keys=True) for line in text.splitlines()
            )
        else:
            body = "<present>"
        parts.append(f"=== {rel}\n{body}\n")
    return "".join(parts)


def record(row: Row, tmp: Path) -> str:
    """The golden text for ``row``: its steps, then the state files they left."""
    repo, script = make_worker_repo(tmp, max_workers=row.max_workers)
    steps: list[str] = []
    extra = row.run(repo, tmp, steps)
    dirs = {"repo": repo.resolve(), "tmp": tmp.resolve(), "fake": script.resolve(),
            **{k: v.resolve() for k, v in extra.items()}}
    body = "\n".join(steps) + "\n" + _state_files(repo)
    text = step_transcript([row.name], 0, _HASH.sub("<HASH>", _UUID.sub("<UUID>", body)), "", dirs)
    return _PID.sub(r"\1 <N>", text)


def golden_path(row: Row) -> Path:
    """Where ``row``'s recorded output lives."""
    return GOLDEN / f"{row.name}.txt"
