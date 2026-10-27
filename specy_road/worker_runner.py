"""The per-worker wrapper: runs the harness, turns its output into events, records the exit (slice 7b).

``worker delegate`` does not wait for a worker. It spawns this module as a
detached process (``start_new_session``, no inherited stdio) and returns the
worker id; the wrapper is what outlives the coordinator's command. It runs
the adapter's command in the worktree, writes every raw output line to
``work/.workers/<id>.log``, appends the lines the adapter understands to the
event log, remembers the harness's session id the moment it appears, and
sets the final state from the exit code. There is no daemon above it
(design note D3): the record and the log are the whole of its interface.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from specy_road.review_files import latest_ready
from specy_road.worker_adapters import Launch, adapter_for
from specy_road.worker_state import (
    WorkerRecord,
    append_event,
    load_record,
    record_path,
    save_record,
    set_state,
)


def log_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".log")


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def spawn(repo_root: Path, rec: WorkerRecord, launch: Launch, *, resumed: bool = False) -> int:
    """Start the wrapper detached and return its pid; the record goes to ``running``."""
    if launch.session_id and not rec.provider_session_id:
        rec.provider_session_id = launch.session_id
    payload = json.dumps({"launch": asdict(launch), "resumed": resumed})
    env = {k: v for k, v in os.environ.items() if k != "SPECY_ROAD_AGENT_ID"}
    # The wrapper must run this very package, not whichever specy_road the
    # interpreter would import from the worker's cwd or an editable install.
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = pkg_parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    p = subprocess.Popen(  # noqa: S603 — our own module, arguments are not user-shaped
        [sys.executable, "-m", "specy_road.worker_runner", str(repo_root), rec.worker_id, payload],
        cwd=rec.worktree, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    set_state(repo_root, rec, "running", pid=p.pid)
    return p.pid


def run(repo_root: Path, worker_id: str, launch: Launch, *, resumed: bool = False) -> int:
    """The wrapper body, in the foreground. Returns the harness's exit code."""
    rec = load_record(repo_root, worker_id)
    adapter = adapter_for(rec.harness)
    log = log_path(repo_root, worker_id)
    if rec.state != "running":
        set_state(repo_root, rec, "running", pid=os.getpid())
    if resumed:
        append_event(repo_root, rec, "resumed", source="broker", summary="resumed with a new prompt")
    with log.open("a", encoding="utf-8") as raw:
        try:
            proc = subprocess.Popen(  # noqa: S603 — the adapter's documented command
                launch.argv, cwd=rec.worktree, stdin=subprocess.PIPE if launch.stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=raw, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as e:
            append_event(repo_root, rec, "error", source="system", summary=f"cannot start {launch.argv[0]}: {e}")
            set_state(repo_root, rec, "failed", pid=None)
            return 127
        if launch.stdin is not None and proc.stdin:
            proc.stdin.write(launch.stdin)
            proc.stdin.close()
        assert proc.stdout is not None
        for line in proc.stdout:
            raw.write(line)
            raw.flush()
            _consume(repo_root, rec, adapter, line)
        code = proc.wait()
    return _finish(repo_root, rec, code)


def _consume(repo_root: Path, rec: WorkerRecord, adapter, line: str) -> None:
    parsed = adapter.parse(line)
    if parsed is None:
        return
    if parsed.session_id and rec.provider_session_id != parsed.session_id:
        if rec.provider_session_id is None:
            rec.provider_session_id = parsed.session_id
            save_record(repo_root, rec)
    append_event(repo_root, rec, parsed.type, source="worker", summary=parsed.summary, detail=parsed.detail)


def _finish(repo_root: Path, rec: WorkerRecord, code: int) -> int:
    rec = load_record(repo_root, rec.worker_id)   # the record may have moved on (handoff, terminate)
    if rec.state == "terminated":
        return code
    ready = latest_ready(repo_root, rec.node_id) is not None
    if code == 0:
        append_event(repo_root, rec, "completion", source="worker",
                     summary=f"exit 0; READY file {'present' if ready else 'missing'}", detail={"exit": 0, "ready": ready})
        set_state(repo_root, rec, "completed" if ready else "idle", pid=None)
    else:
        append_event(repo_root, rec, "error", source="worker", summary=f"exit {code}; see {log_path(repo_root, rec.worker_id).name}",
                     detail={"exit": code, "ready": ready})
        set_state(repo_root, rec, "failed", pid=None)
    return code


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3:
        print("usage: python -m specy_road.worker_runner <repo_root> <worker_id> <payload-json>", file=sys.stderr)
        raise SystemExit(2)
    payload = json.loads(argv[2])
    launch = Launch(**payload["launch"])
    raise SystemExit(run(Path(argv[0]), argv[1], launch, resumed=bool(payload.get("resumed"))))


if __name__ == "__main__":
    main()
