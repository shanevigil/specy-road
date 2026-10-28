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

from specy_road.review_target import same_commit
from specy_road.worker_adapters import Launch, adapter_for
from specy_road.worker_process import (  # noqa: F401 — pid_alive/pid_verified re-exported for existing callers
    argv_too_long,
    branch_mismatch,
    new_ready,
    new_token,
    pid_alive,
    pid_verified,
    ready_fingerprints,
    start_token,
)
from specy_road.worker_state import (
    WorkerError,
    WorkerRecord,
    append_event,
    load_record,
    mutate,
    record_path,
    set_state,
    workers_dir,
    workers_lock,
)


def log_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".log")


def _payload_file(repo_root: Path, rec: WorkerRecord, token: str, payload: str) -> Path:
    """The launch payload (argv, the prompt on stdin) in a 0600 file: a brief must never travel in argv."""
    d = workers_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rec.worker_id}.launch-{token}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    return path


def _refuse(repo_root: Path, rec: WorkerRecord, why: str) -> None:
    append_event(repo_root, rec, "error", source="system", summary=why[:500])
    set_state(repo_root, rec, "failed", pid=None)
    raise WorkerError(f"{rec.worker_id}: {why}")


def spawn(repo_root: Path, rec: WorkerRecord, launch: Launch, *, resumed: bool = False) -> int:
    """Start the wrapper detached and return its pid; the record goes to ``running``."""
    why = argv_too_long(launch.argv)
    if why:
        _refuse(repo_root, rec, why)
    token = new_token()
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
        path = _payload_file(repo_root, rec, token, payload)
        try:
            p = subprocess.Popen(  # noqa: S603 — our own module, arguments are not user-shaped
                [sys.executable, "-m", "specy_road.worker_runner", str(Path(repo_root).resolve()), rec.worker_id,
                 token, str(path)],
                cwd=rec.worktree, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
            )
        except OSError:
            path.unlink(missing_ok=True)
            raise

        def mark(r: WorkerRecord) -> None:
            r.state, r.pid, r.pgid, r.wrapper_token = "running", p.pid, p.pid, token
            r.harness_pid = r.harness_start = None
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
    # The turn's checkpoint: a completion needs a READY that is not one of these.
    before = ready_fingerprints(repo_root, rec.node_id)
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
        def seen(r: WorkerRecord) -> None:
            r.harness_pid, r.harness_start, r.pgid = proc.pid, start_token(proc.pid), os.getpgid(0)
        mutate(repo_root, rec, seen)
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
    return _finish(repo_root, rec, code, before)


def _consume(repo_root: Path, rec: WorkerRecord, adapter, line: str) -> None:
    parsed = adapter.parse(line)
    if parsed is None:
        return
    if parsed.session_id:
        # First seen wins; a later line (which the model controls) cannot move it.
        mutate(repo_root, rec, lambda r: setattr(r, "provider_session_id", r.provider_session_id or parsed.session_id))
    # Parsed from the harness's stdout, which the model controls: a claim, not a fact the wrapper observed.
    append_event(repo_root, rec, parsed.type, source="worker", authority="worker_suggestion",
                 summary=parsed.summary, detail=parsed.detail)


def _fresh_ready(repo_root: Path, rec: WorkerRecord, before: list[str]) -> bool:
    """A READY for this node that appeared or changed during this turn, on the branch actually checked out.

    ``before`` is the fingerprint list taken at turn start (:func:`ready_fingerprints`):
    an earlier turn's or attempt's READY is in it and does not count, however
    its mtime reads.
    """
    ready = new_ready(repo_root, rec.node_id, before)
    if ready is None or str(ready.data.get("node_id")) != rec.node_id:
        return False
    if rec.branch and str(ready.data.get("branch")) != rec.branch:
        return False   # another attempt's branch, not this worker's
    why = branch_mismatch(Path(rec.worktree), rec.branch)
    if why:
        append_event(repo_root, rec, "error", source="system", summary=f"READY {ready.path.name} ignored: {why}")
        return False
    if not same_commit(Path(rec.worktree), str(ready.data.get("commit") or ""), "HEAD"):
        return False   # a READY for an older commit on this branch: the turn moved past it
    return True


def _finish(repo_root: Path, rec: WorkerRecord, code: int, before: list[str]) -> int:
    rec = load_record(repo_root, rec.worker_id)   # the record may have moved on (handoff, terminate)
    if rec.state == "terminated":
        return code
    ready = _fresh_ready(repo_root, rec, before)
    if code == 0:
        append_event(repo_root, rec, "completion", source="worker",
                     summary=f"exit 0; READY file {'present' if ready else 'missing'}", detail={"exit": 0, "ready": ready})
        _exit_state(repo_root, rec, "completed" if ready else "idle")
    else:
        append_event(repo_root, rec, "error", source="worker", summary=f"exit {code}; see {log_path(repo_root, rec.worker_id).name}",
                     detail={"exit": code, "ready": ready})
        _exit_state(repo_root, rec, "failed")
    return code


def _exit_state(repo_root: Path, rec: WorkerRecord, state: str) -> None:
    """The harness has been waited for: no pid, harness pid or group is left to signal."""
    def fn(r: WorkerRecord) -> None:
        r.state = state
        r.pid = r.pgid = r.harness_pid = r.harness_start = None
    mutate(repo_root, rec, fn)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 4:
        print("usage: python -m specy_road.worker_runner <repo_root> <worker_id> <token> <payload-file>", file=sys.stderr)
        raise SystemExit(2)
    path = Path(argv[3])
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.unlink(missing_ok=True)   # read once; the prompt text does not stay on disk twice
    launch = Launch(**payload["launch"])
    raise SystemExit(run(Path(argv[0]), argv[1], launch, resumed=bool(payload.get("resumed")),
                         harness_pythonpath=payload.get("harness_pythonpath")))


if __name__ == "__main__":
    main()
