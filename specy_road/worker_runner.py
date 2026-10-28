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
import time
from dataclasses import asdict
from pathlib import Path

from specy_road.review_files import latest_ready
from specy_road.review_target import same_commit
from specy_road.worker_adapters import Launch, adapter_for
from specy_road.worker_state import (
    WorkerRecord,
    append_event,
    load_record,
    mutate,
    record_path,
    set_state,
    workers_lock,
)


def log_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".log")


def _cmdline(pid: int) -> str | None:
    """The process's command line via ``ps``, or ``None`` when ``ps`` cannot say.

    ``-ww``: without a terminal procps cuts the line at 80 columns, which drops
    the worker id after any realistic repo path.
    """
    try:
        r = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                           check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def pid_alive(pid: int | None, worker_id: str | None = None) -> bool:
    """Whether ``pid`` is a live **wrapper** (for ``worker_id`` when given): a reused pid must not pass for one.

    When ``ps`` cannot say, liveness alone answers; :func:`pid_verified` is
    the stricter form a destructive operation needs.
    """
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    cmd = _cmdline(pid)
    return cmd is None or _is_wrapper(cmd, worker_id)


def _is_wrapper(cmd: str, worker_id: str | None) -> bool:
    return "worker_runner" in cmd and (worker_id is None or f" {worker_id} " in f" {cmd} ")


def pid_verified(pid: int | None, worker_id: str) -> bool:
    """``pid`` is live **and** its command line names this worker's wrapper; unknown is ``False``."""
    if not pid_alive(pid):
        return False
    cmd = _cmdline(pid)
    return bool(cmd) and _is_wrapper(cmd, worker_id)


def spawn(repo_root: Path, rec: WorkerRecord, launch: Launch, *, resumed: bool = False) -> int:
    """Start the wrapper detached and return its pid; the record goes to ``running``."""
    payload = json.dumps({"launch": asdict(launch), "resumed": resumed,
                          "harness_pythonpath": os.environ.get("PYTHONPATH")})
    env = {k: v for k, v in os.environ.items() if k != "SPECY_ROAD_AGENT_ID"}
    # The wrapper must run this very package, not whichever specy_road the
    # interpreter would import from the worker's cwd or an editable install.
    # The harness itself gets the caller's PYTHONPATH back (``run`` restores it
    # from the payload), so the adopter's tests never see ours.
    pkg_parent = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = pkg_parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["SPECY_ROAD_WORKER_ID"] = rec.worker_id   # so the harness's own hooks do not count it as a stranger
    # Under the lock, so the wrapper cannot write its own state before the
    # session id chosen up front is on disk; the id goes in through mutate,
    # which reloads first, so it survives (a bare attribute set did not).
    with workers_lock(repo_root):
        p = subprocess.Popen(  # noqa: S603 — our own module, arguments are not user-shaped
            [sys.executable, "-m", "specy_road.worker_runner", str(repo_root), rec.worker_id, payload],
            cwd=rec.worktree, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )

        def mark(r: WorkerRecord) -> None:
            r.state, r.pid = "running", p.pid
            if launch.session_id and not r.provider_session_id:
                r.provider_session_id = launch.session_id
        mutate(repo_root, rec, mark)
    return p.pid


def run(repo_root: Path, worker_id: str, launch: Launch, *, resumed: bool = False,
        harness_pythonpath: str | None = None) -> int:
    """The wrapper body, in the foreground. Returns the harness's exit code."""
    rec = load_record(repo_root, worker_id)
    adapter = adapter_for(rec.harness)
    log = log_path(repo_root, worker_id)
    started = time.time()
    set_state(repo_root, rec, "running", pid=os.getpid())
    if resumed:
        append_event(repo_root, rec, "resumed", source="broker", summary="resumed with a new prompt")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if harness_pythonpath:
        env["PYTHONPATH"] = harness_pythonpath
    with log.open("a", encoding="utf-8") as raw:
        try:
            proc = subprocess.Popen(  # noqa: S603 — the adapter's documented command
                launch.argv, cwd=rec.worktree, env=env,
                stdin=subprocess.PIPE if launch.stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=raw, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as e:
            append_event(repo_root, rec, "error", source="system", summary=f"cannot start {launch.argv[0]}: {e}")
            set_state(repo_root, rec, "failed", pid=None)
            return 127
        if launch.stdin is not None and proc.stdin:
            try:
                proc.stdin.write(launch.stdin)
                proc.stdin.close()
            except (BrokenPipeError, OSError) as e:   # the harness quit before reading its prompt
                raw.write(f"[wrapper] harness closed stdin early: {e}\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            raw.write(line)
            raw.flush()
            try:
                _consume(repo_root, rec, adapter, line)
            except Exception as e:  # noqa: BLE001 — one bad line must not kill the wrapper
                raw.write(f"[wrapper] could not record a line: {e}\n")
        code = proc.wait()
    return _finish(repo_root, rec, code, started)


def _consume(repo_root: Path, rec: WorkerRecord, adapter, line: str) -> None:
    parsed = adapter.parse(line)
    if parsed is None:
        return
    if parsed.session_id:
        # First seen wins; a later line (which the model controls) cannot move it.
        mutate(repo_root, rec, lambda r: setattr(r, "provider_session_id", r.provider_session_id or parsed.session_id))
    append_event(repo_root, rec, parsed.type, source="worker", summary=parsed.summary, detail=parsed.detail)


def _fresh_ready(repo_root: Path, rec: WorkerRecord, since: float) -> bool:
    """A READY for this node written during this turn; an earlier turn's or attempt's does not count."""
    ready = latest_ready(repo_root, rec.node_id)
    if ready is None or str(ready.data.get("node_id")) != rec.node_id:
        return False
    if rec.branch and str(ready.data.get("branch")) != rec.branch:
        return False   # another attempt's branch, not this worker's
    if not same_commit(Path(rec.worktree), str(ready.data.get("commit") or ""), "HEAD"):
        return False   # a READY for an older commit on this branch: the turn moved past it
    return ready.path.stat().st_mtime >= since - 1


def _finish(repo_root: Path, rec: WorkerRecord, code: int, since: float) -> int:
    rec = load_record(repo_root, rec.worker_id)   # the record may have moved on (handoff, terminate)
    if rec.state == "terminated":
        return code
    ready = _fresh_ready(repo_root, rec, since)
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
    raise SystemExit(run(Path(argv[0]), argv[1], launch, resumed=bool(payload.get("resumed")),
                         harness_pythonpath=payload.get("harness_pythonpath")))


if __name__ == "__main__":
    main()
