"""The per-worker wrapper: runs the harness, turns its output into events, records the exit (slice 7b).

``worker delegate`` does not wait for a worker. It spawns this module as a
detached process (``start_new_session``, no inherited stdio) and returns the
worker id; the wrapper is what outlives the coordinator's command. It runs
the adapter's command in the worktree, writes every raw output line to
``work/.workers/<id>.log``, appends the lines the adapter understands to the
event log, remembers the harness's session id the moment it appears, and
sets the final state from the exit code. There is no daemon above it
(design note D3): the record and the log are the whole of its interface.
When ``track_worker_logs`` opts in, each turn ends by mirroring the logs into
the worker's own checkout, where finish-this-task commits them with the leaf.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from specy_road.git_workflow_config import WORKER_LOGS_REL, track_worker_logs
from specy_road.orchestration_role_env import harness_env
from specy_road.runtime_paths import project_prefix
from specy_road.worker_adapter_parsers import USAGE_FIELDS, init_model
from specy_road.worker_adapters import ClaudeCode, Launch, adapter_for
from specy_road.worker_exit import exit_event
from specy_road.worker_lease import release_lease
from specy_road.worker_models import launch_model, turn_models, usage_event
from specy_road.worker_process import (  # noqa: F401 — pid_alive/pid_verified re-exported for existing callers
    argv_too_long,
    new_token,
    pid_alive,
    pid_verified,
    ready_fingerprints,
    start_token,
)
from specy_road.worker_runner_ready import all_ready_fingerprints, fresh_ready
from specy_road.worker_state import (
    FLAG_STALLED,
    WorkerError,
    WorkerRecord,
    _now,
    append_event,
    events_path,
    events_since,
    load_record,
    mutate,
    record_path,
    require_writer,
    set_state,
    workers_dir,
    workers_lock,
)
from specy_road.worker_turn_check import PAUSED_BY_LIMIT, TurnWatch, close_turn
from specy_road.worker_usage_delta import turn_usage


def queue_worker_message(repo_root: Path, rec: WorkerRecord, text: str) -> WorkerRecord:
    if not rec.provider_session_id:
        raise WorkerError(f"{rec.worker_id} has no native session id yet; nothing to queue for")
    with workers_lock(repo_root):
        rec = load_record(repo_root, rec.worker_id)
        require_writer(rec)
        prior = rec.queued_message
        mutate(repo_root, rec, lambda r: setattr(r, "queued_message", f"{prior}\n\n{text}" if prior else text))
    verb = "appended" if prior else "queued"
    append_event(repo_root, load_record(repo_root, rec.worker_id), "message_queued", source="orchestrator",
                 authority="orchestrator", summary=f"{verb}: {' '.join(text.split())[:300]}")
    return load_record(repo_root, rec.worker_id)


def deliver_queued_message(repo_root: Path, worker_id: str, *, offline: bool = False) -> WorkerRecord | None:
    from specy_road.worker_ops import _send  # noqa: PLC0415 — ops imports spawn from this module

    with workers_lock(repo_root):   # process_alive and spawn as one transition, like message()
        rec = load_record(repo_root, worker_id)
        text = rec.queued_message
        if not text or rec.state == "terminated":
            return None
        mutate(repo_root, rec, lambda r: setattr(r, "queued_message", None))
        try:
            return _send(repo_root, rec, text, "message", offline)
        except WorkerError as e:
            rec = load_record(repo_root, worker_id)
            if rec.state != "terminated":
                mutate(repo_root, rec, lambda r: setattr(r, "queued_message", text))
            append_event(repo_root, rec, "error", source="system", summary=f"queued message not delivered: {e}")
            raise


#: ``last_output_at`` is written at most this often: each write is a mutate under the workers lock.
OUTPUT_MARK_SECONDS = 5.0


def log_path(repo_root: Path, worker_id: str) -> Path:
    return record_path(repo_root, worker_id).with_suffix(".log")


def mirror_dir(repo_root: Path, rec: WorkerRecord) -> Path:
    """``work/worker-logs/<NODE_ID>/`` in the worker's own checkout: the leaf's branch is checked out there."""
    return Path(rec.worktree) / project_prefix(repo_root) / WORKER_LOGS_REL / rec.node_id


def mirror_logs(repo_root: Path, rec: WorkerRecord) -> None:
    """Bring the tracked copies up to date per ``track_worker_logs``; nothing at all when ``off``.

    Called when a turn ends, not per line: a copy in the worktree during the turn
    would be an untracked change under the executor's own clean-tree check.
    """
    mode = track_worker_logs(repo_root)
    if mode == "off":
        return
    d = mirror_dir(repo_root, rec)
    pairs = [(events_path(repo_root, rec.worker_id), d / f"{rec.worker_id}.events.jsonl")]
    if mode == "full":
        pairs.append((log_path(repo_root, rec.worker_id), d / f"{rec.worker_id}.log"))
    for src, dst in pairs:
        try:
            _copy_tail(src, dst)
        except OSError as e:   # the audit copy must never fail the turn it records
            with log_path(repo_root, rec.worker_id).open("a", encoding="utf-8") as raw:
                raw.write(f"[wrapper] could not mirror {src.name}: {e}\n")


def _copy_tail(src: Path, dst: Path) -> None:
    """Append what ``src`` holds past ``dst``'s length: both only grow, so the copy stays byte-identical."""
    have = dst.stat().st_size if dst.is_file() else 0
    if not src.is_file() or src.stat().st_size <= have:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as s, dst.open("ab") as d:
        s.seek(have)
        shutil.copyfileobj(s, d)


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
    with workers_lock(repo_root):   # held by the launching caller already; re-entered so the pair stays one step
        set_state(repo_root, rec, "failed", pid=None)
        release_lease(repo_root, rec.worker_id)
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
    watch = TurnWatch(repo_root, rec)   # the post-run check's starting git state, before the harness can move it
    before_all = all_ready_fingerprints(repo_root, rec.node_id)
    set_state(repo_root, rec, "running", pid=os.getpid())
    if resumed:
        append_event(repo_root, rec, "resumed", source="broker", summary="resumed with a new prompt")
    env = harness_env(os.environ, "executor", harness_pythonpath=harness_pythonpath, harness=rec.harness)
    env.update(launch.env or {})   # the adapter's own (Codex: the profile's CODEX_HOME)
    with log.open("a", encoding="utf-8") as raw:
        log_start = raw.tell()   # this turn's part of the log starts here (the harness writes stderr into it)
        try:
            proc = subprocess.Popen(  # noqa: S603 — the adapter's documented command
                launch.argv, cwd=rec.worktree, env=env,
                stdin=subprocess.PIPE if launch.stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=raw, text=True, encoding="utf-8", errors="replace",
            )
        except OSError as e:
            # The turn ends here too: nothing reported, so nulls; no `launched` event names its model.
            _append_usage(repo_root, rec, {"requested_model": launch_model(launch.argv), "observed_model": None})
            watch.failed = f"cannot start {launch.argv[0]}: {e}"   # a failed turn: the post-run check runs here too
            close_turn(repo_root, rec, watch)   # (M8.2); the record still ends `failed` below
            append_event(repo_root, rec, "error", source="system", summary=f"cannot start {launch.argv[0]}: {e}",
                         detail={"exit": 127})   # the wrapper's exit record: this error ends the turn
            mirror_logs(repo_root, rec)
            with workers_lock(repo_root):   # failed and its lease gone in one step: a resume cannot fall between
                set_state(repo_root, rec, "failed", pid=None)
                release_lease(repo_root, rec.worker_id)
            return 127
        def seen(r: WorkerRecord) -> None:
            r.harness_pid, r.harness_start, r.pgid = proc.pid, start_token(proc.pid), os.getpgid(0)
            # A new turn is a new silence: measured from the launch, not the last turn's output.
            r.last_output_at = _now()
            r.flags = [f for f in r.flags if f != FLAG_STALLED]
        mutate(repo_root, rec, seen)
        watch.proc = proc
        append_event(repo_root, rec, "launched", source="system", summary=f"started {launch.argv[0]} (pid {proc.pid})",
                     detail={"argv0": launch.argv[0], "harness": rec.harness, "resumed": resumed,
                             "model": launch_model(launch.argv)})   # the model the harness is told, if any
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
                usage_logged = _consume(repo_root, rec, adapter, line, launch, watch) or usage_logged
            except Exception as e:  # noqa: BLE001 — one bad line must not kill the wrapper
                raw.write(f"[wrapper] could not record a line: {e}\n")
        code = proc.wait()
    # A Claude result always carries usage, so none means no result line: a limit is then only in the transcript.
    if code != 0 and not usage_logged and isinstance(adapter, ClaudeCode):
        _transcript_limit(repo_root, rec, adapter, launch, watch)
    return _finish(repo_root, rec, code, before, before_all, usage_logged, watch, log_start)


def _transcript_limit(repo_root: Path, rec: WorkerRecord, adapter: ClaudeCode, launch: Launch, watch: TurnWatch) -> None:
    """Record a usage limit the session transcript names, for the post-run check to pause on."""
    parsed = adapter.transcript_limit(launch.session_id or load_record(repo_root, rec.worker_id).provider_session_id)
    if parsed:
        append_event(repo_root, rec, parsed.type, source="worker", authority="worker_suggestion",
                     summary=parsed.summary, detail=parsed.detail)
        watch.observe(parsed)


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


def _consume(repo_root: Path, rec: WorkerRecord, adapter, line: str, launch: Launch, watch: TurnWatch) -> bool:
    """Append the events ``line`` records; True when one of them carried the turn's usage."""
    logged = False
    # One line can record more than one event (Claude's init: `started`, then a launch-mode mismatch).
    for parsed in adapter.parse_events(line, launch):
        if parsed.session_id:
            # First seen wins; a later line (which the model controls) cannot move it.
            mutate(repo_root, rec, lambda r: setattr(r, "provider_session_id", r.provider_session_id or parsed.session_id))
        model = init_model(line) if parsed.type == "started" else None   # the model the harness says it runs
        # Parsed from the harness's stdout, which the model controls: a claim, not a fact the wrapper observed.
        append_event(repo_root, rec, parsed.type, source="worker", authority="worker_suggestion",
                     summary=parsed.summary, detail={**(parsed.detail or {}), "model": model} if model else parsed.detail)
        watch.observe(parsed)   # what the post-run check and the retry watchdog read
        if parsed.usage is not None:
            _append_usage(repo_root, rec, parsed.usage)
            logged = True
    return logged


def _append_usage(repo_root: Path, rec: WorkerRecord, usage: dict) -> None:
    """The turn's ``usage`` event; running session totals become this turn's, the version comes from ``started``."""
    events = events_since(repo_root, rec.worker_id)
    # A turn that never launched sets its own models; a running session total becomes this turn's share.
    detail = turn_usage({**dict.fromkeys(USAGE_FIELDS), **turn_models(events), **usage}, events)
    if detail["harness_version"] is None:
        detail["harness_version"] = next((str(e.detail["version"]) for e in reversed(events) if e.type == "started"
                                          and e.source == "worker" and (e.detail or {}).get("version")), None)
    # Parsed from the harness's output, like the line it came from.
    append_event(repo_root, rec, "usage", source="worker", authority="worker_suggestion",
                 **usage_event(repo_root, detail))


def _finish(repo_root: Path, rec: WorkerRecord, code: int, before: list[str], before_all: list[str],
            usage_logged: bool, watch: TurnWatch, log_start: int = 0) -> int:
    rec = load_record(repo_root, rec.worker_id)   # the record may have moved on (handoff, terminate)
    if rec.state == "terminated":
        close_turn(repo_root, rec, watch, pause=False)   # the check still runs; a terminated worker is not paused
        return code
    if not usage_logged:   # one usage event per turn: a harness that reported none gets nulls, not zeros
        _append_usage(repo_root, rec, {})
    ready = fresh_ready(repo_root, rec, before)
    watch.exited(code)   # the check runs before the exit event: a failed exit is one of its findings
    paused = close_turn(repo_root, rec, watch)   # the post-run check (M8.2): a usage limit pauses, whatever the exit code
    exit_event(repo_root, rec, code, ready, before_all=before_all, log=log_path(repo_root, rec.worker_id),
               log_start=log_start)
    _exit_state(repo_root, rec, PAUSED_BY_LIMIT if paused   # a limit wins over READY and over the exit code
                else ("completed" if ready else "idle") if code == 0 else "failed")
    return code


def _exit_state(repo_root: Path, rec: WorkerRecord, state: str) -> None:
    """The harness has been waited for: no pid, harness pid or group is left to signal.

    The turn's last event is written, so the logs are mirrored first: whoever waits
    for the record to clear its pid finds the copy complete.
    """
    mirror_logs(repo_root, rec)

    def fn(r: WorkerRecord) -> None:
        r.state = state
        r.pid = r.pgid = r.harness_pid = r.harness_start = None
    with workers_lock(repo_root):   # a resume (which acquires under this lock) sees failed only once the lease is gone
        mutate(repo_root, rec, fn)
        if state == "failed":   # the slot lease follows the record: idle and completed keep it
            release_lease(repo_root, rec.worker_id)
    _deliver_queued(repo_root, rec.worker_id)


def _deliver_queued(repo_root: Path, worker_id: str) -> None:
    try:
        deliver_queued_message(repo_root, worker_id)
    except WorkerError:
        pass   # the failure is on the record; the coordinator sees it on the next sync


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
