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
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from specy_road.review_target import same_commit
from specy_road.worker_adapter_parsers import USAGE_FIELDS, usage_text
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
    FLAG_STALLED,
    WorkerError,
    WorkerRecord,
    _now,
    append_event,
    events_since,
    load_record,
    mutate,
    record_path,
    set_state,
    workers_dir,
    workers_lock,
)


#: ``last_output_at`` is written at most this often: each write is a mutate under the workers lock.
OUTPUT_MARK_SECONDS = 5.0


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
    # from the payload), so the adopter's tests never see ours. ``-P`` keeps
    # the cwd (a worktree that may hold an older specy_road) off sys.path for
    # this interpreter only; PYTHONSAFEPATH would leak into the harness.
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
                [sys.executable, "-P", "-m", "specy_road.worker_runner", str(Path(repo_root).resolve()), rec.worker_id,
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
        harness_pythonpath: str | None = None, clock: Callable[[], float] = time.monotonic) -> int:
    """The wrapper body, in the foreground. Returns the harness's exit code.

    ``clock`` is read once per stdout line to throttle ``last_output_at`` writes.
    """
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
    env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)   # a caller's setting must not override the profile's effort_by_role
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
            _append_usage(repo_root, rec, {})   # the turn ends here too: nothing reported, so nulls
            append_event(repo_root, rec, "error", source="system", summary=f"cannot start {launch.argv[0]}: {e}",
                         detail={"exit": 127})   # the wrapper's exit record: this error ends the turn
            set_state(repo_root, rec, "failed", pid=None)
            return 127
        def seen(r: WorkerRecord) -> None:
            r.harness_pid, r.harness_start, r.pgid = proc.pid, start_token(proc.pid), os.getpgid(0)
            # A new turn is a new silence: measured from the launch, not the last turn's output.
            r.last_output_at = _now()
            r.flags = [f for f in r.flags if f != FLAG_STALLED]
        mutate(repo_root, rec, seen)
        append_event(repo_root, rec, "launched", source="system", summary=f"started {launch.argv[0]} (pid {proc.pid})",
                     detail={"argv0": launch.argv[0], "harness": rec.harness, "resumed": resumed})
        if launch.stdin is not None and proc.stdin:
            try:
                proc.stdin.write(launch.stdin)
                proc.stdin.close()
            except (BrokenPipeError, OSError) as e:   # the harness quit before reading its prompt
                raw.write(f"[wrapper] harness closed stdin early: {e}\n")
        assert proc.stdout is not None
        first, marked, usage_logged = True, None, False
        for line in proc.stdout:
            raw.write(line)
            raw.flush()
            if first:
                first = False
                append_event(repo_root, rec, "first_output", source="system", summary="first stdout line read")
            try:
                marked = _output_seen(repo_root, rec, marked, clock())
                usage_logged = _consume(repo_root, rec, adapter, line, launch) or usage_logged
            except Exception as e:  # noqa: BLE001 — one bad line must not kill the wrapper
                raw.write(f"[wrapper] could not record a line: {e}\n")
        code = proc.wait()
    return _finish(repo_root, rec, code, before, usage_logged)


def _output_seen(repo_root: Path, rec: WorkerRecord, marked: float | None, now: float) -> float | None:
    """Write ``last_output_at`` and drop ``stalled`` unless the last write is under five seconds old
    and the record is not flagged ``stalled``.

    A threshold under the window can flag a worker between two writes; its next
    line must still clear the flag, and writes the time too, so the next sweep
    measures a new silence from this line. ``marked`` and ``now`` are clock
    readings; returns the reading of the last write.
    """
    if (marked is not None and now - marked < OUTPUT_MARK_SECONDS
            and FLAG_STALLED not in load_record(repo_root, rec.worker_id).flags):
        return marked

    def fn(r: WorkerRecord) -> None:
        r.last_output_at = _now()
        r.flags = [f for f in r.flags if f != FLAG_STALLED]
    mutate(repo_root, rec, fn)
    return now


def _consume(repo_root: Path, rec: WorkerRecord, adapter, line: str, launch: Launch) -> bool:
    """Append the events ``line`` records; True when one of them carried the turn's usage."""
    logged = False
    # One line can record more than one event (Claude's init: `started`, then a launch-mode mismatch).
    for parsed in adapter.parse_events(line, launch):
        if parsed.session_id:
            # First seen wins; a later line (which the model controls) cannot move it.
            mutate(repo_root, rec, lambda r: setattr(r, "provider_session_id", r.provider_session_id or parsed.session_id))
        # Parsed from the harness's stdout, which the model controls: a claim, not a fact the wrapper observed.
        append_event(repo_root, rec, parsed.type, source="worker", authority="worker_suggestion",
                     summary=parsed.summary, detail=parsed.detail)
        if parsed.usage is not None:
            _append_usage(repo_root, rec, parsed.usage)
            logged = True
    return logged


def _append_usage(repo_root: Path, rec: WorkerRecord, usage: dict) -> None:
    """The turn's ``usage`` event; a running session cost becomes this turn's, the version comes from ``started``."""
    detail = {**dict.fromkeys(USAGE_FIELDS), **usage}
    events = events_since(repo_root, rec.worker_id)
    total = detail.get("session_cost_usd")
    if total is not None:
        prev = next((e.detail["session_cost_usd"] for e in reversed(events) if e.type == "usage"
                     and (e.detail or {}).get("session_cost_usd") is not None), None)
        # A lower total than the last one is a new session (a custom command without one): it counts whole.
        detail["cost_usd"] = round(total - prev, 6) if prev is not None and prev <= total else total
    if detail["harness_version"] is None:
        detail["harness_version"] = next((str(e.detail["version"]) for e in reversed(events) if e.type == "started"
                                          and e.source == "worker" and (e.detail or {}).get("version")), None)
    # Parsed from the harness's output, like the line it came from.
    append_event(repo_root, rec, "usage", source="worker", authority="worker_suggestion",
                 summary=f"usage: {usage_text(detail)}", detail=detail)


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


def _finish(repo_root: Path, rec: WorkerRecord, code: int, before: list[str], usage_logged: bool) -> int:
    rec = load_record(repo_root, rec.worker_id)   # the record may have moved on (handoff, terminate)
    if rec.state == "terminated":
        return code
    if not usage_logged:   # one usage event per turn: a harness that reported none gets nulls, not zeros
        _append_usage(repo_root, rec, {})
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
