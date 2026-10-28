"""Process identity and liveness for workers: the wrapper, its harness, and their process group.

A worker record names three processes: the detached wrapper (``pid``), the
harness it ran (``harness_pid``), and the process group both live in
(``pgid``, the wrapper's own pid since it is a session leader). A pid alone
is not an identity — it is reused — so the wrapper carries a random token in
its argv (``wrapper_token``) and the harness's recorded start time
(``harness_start``, from ``ps -o lstart=``) must still match. Liveness here
is what ``delegate``, ``status``, ``handoff`` and ``terminate`` ask:
:func:`wrapper_alive` for "is the turn still running", :func:`harness_alive`
for "did the harness outlive its wrapper" (review round 6, B9), and
:func:`kill_group` for "make the whole group go away and confirm it".

Also here: the READY fingerprint a turn is judged against (B3) and the
checked-out-branch check (B12), both used by the wrapper and by the resume
and reclaim paths.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import signal
import subprocess
import time
from pathlib import Path

from specy_road.git_subprocess import git_text
from specy_road.review_files import list_ready
from specy_road.worker_state import (
    FLAG_ORPHAN,
    WorkerError,
    WorkerRecord,
    add_flag,
    append_event,
    set_state,
)

#: A launch whose prompt travels in argv (Cursor, ``<prompt>`` commands) is
#: refused above this many bytes of arguments rather than failing with E2BIG.
ARGV_LIMIT = 100 * 1024


def new_token() -> str:
    return secrets.token_hex(8)


def _ps(fields: str, pid: int) -> str | None:
    """``ps -o <fields>`` for ``pid``: the line, ``""`` when ps found no such process, ``None`` when ps cannot say.

    ``-ww``: without a terminal procps cuts the line at 80 columns, which drops
    the worker id after any realistic repo path (found by the cloud pre-release
    run on Linux; BSD ``ps`` accepts the flag too).
    """
    try:
        r = subprocess.run(["ps", "-ww", "-o", fields, "-p", str(pid)], capture_output=True, text=True,
                           check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode not in (0, 1):
        return None
    return r.stdout.strip()


def _cmdline(pid: int) -> str | None:
    """The process's command line via ``ps``: ``""`` for no such process, ``None`` when ``ps`` cannot say."""
    return _ps("command=", pid)


def start_token(pid: int) -> str | None:
    """The process's start time (``ps -o lstart=``): with the pid, an identity a reused pid cannot share."""
    return _ps("lstart=", pid) or None


def _exists(pid: int | None) -> bool | None:
    """``True`` alive as our user, ``False`` gone (or a zombie), ``None`` alive but not ours (``PermissionError``)."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    stat = _ps("stat=", pid)
    if stat == "" or (stat and stat.startswith("Z")):
        return False   # ps found nothing, or a zombie awaiting its parent's wait()
    return True


def _is_wrapper(cmd: str, worker_id: str | None, repo_root: str | None = None, token: str | None = None) -> bool:
    """Whole-argument match: the module, the worker id, and (when known) the resolved repo root and token."""
    args = cmd.split()
    if not any(a.endswith("worker_runner") or a == "specy_road.worker_runner" for a in args):
        return False
    if worker_id is not None and worker_id not in args:
        return False
    if token is not None and token not in args:
        return False
    return repo_root is None or f" {repo_root} " in f" {cmd} "


def pid_alive(pid: int | None, worker_id: str | None = None, *, repo_root: Path | None = None,
              token: str | None = None) -> bool:
    """Whether ``pid`` is a live wrapper (for ``worker_id``, ``repo_root`` and ``token`` when given).

    A pid our user cannot signal is another user's process, so a reused pid:
    it counts only when ``ps`` shows our wrapper's command line. When ``ps``
    cannot say, liveness alone answers; :func:`pid_verified` is the stricter form.
    """
    exists = _exists(pid)
    if exists is False:
        return False
    cmd = _cmdline(int(pid))  # type: ignore[arg-type]
    root = str(Path(repo_root).resolve()) if repo_root else None
    if cmd is None:
        return exists is True   # ps cannot say: liveness alone, and only as our own user
    return _is_wrapper(cmd, worker_id, root, token)


def pid_verified(pid: int | None, worker_id: str, *, repo_root: Path | None = None, token: str | None = None) -> bool:
    """``pid`` is live **and** its command line names this worker's wrapper; unknown is ``False``."""
    if _exists(pid) is False:
        return False
    cmd = _cmdline(int(pid))  # type: ignore[arg-type]
    root = str(Path(repo_root).resolve()) if repo_root else None
    return bool(cmd) and _is_wrapper(cmd, worker_id, root, token)


def wrapper_alive(rec: WorkerRecord, repo_root: Path | None = None) -> bool:
    """The record's wrapper is running: pid, worker id and token (when the record has one) all match."""
    return pid_alive(rec.pid, rec.worker_id, repo_root=repo_root, token=rec.wrapper_token)


def wrapper_verified(rec: WorkerRecord, repo_root: Path | None = None) -> bool:
    return pid_verified(rec.pid, rec.worker_id, repo_root=repo_root, token=rec.wrapper_token)


def _group_members(pgid: int | None) -> list[int]:
    if not pgid:
        return []
    try:
        r = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == str(pgid) and parts[0].isdigit():
            out.append(int(parts[0]))
    return out


def harness_alive(rec: WorkerRecord) -> bool:
    """The harness (or anything else in the worker's process group) outlived the wrapper.

    The harness pid counts only with its recorded start time; other group
    members count by membership (the group id is the wrapper's pid, which a
    new session leader could reuse only after the whole group is gone).
    """
    if rec.harness_pid and _exists(rec.harness_pid) is not False:
        if rec.harness_start is None or start_token(rec.harness_pid) == rec.harness_start:
            return True
    return any(p != rec.pid for p in _group_members(rec.pgid))


def _harness_verified(rec: WorkerRecord) -> bool:
    """The recorded harness pid is alive with its recorded start time: unknown is ``False``."""
    return bool(rec.harness_pid and rec.harness_start and _exists(rec.harness_pid) is True
                and start_token(rec.harness_pid) == rec.harness_start)


def wrapper_gone(repo_root: Path, rec: WorkerRecord) -> bool:
    """A ``running``/``starting`` record with no live wrapper: closed (``failed``) so the leaf is free again.

    Not while its harness or process group is still alive: then the leaf
    stays owned, the record is flagged ``wrapper_gone_harness_alive`` (one
    ``error`` event says so), and ``terminate`` is the way out.
    """
    if rec.state not in ("running", "starting") or wrapper_alive(rec, repo_root):
        return False
    if harness_alive(rec):
        if FLAG_ORPHAN not in rec.flags:
            append_event(repo_root, rec, "error", source="system",
                         summary=f"wrapper pid {rec.pid or '-'} is gone but harness pid {rec.harness_pid or '-'} "
                                 f"(group {rec.pgid or '-'}) is still alive; the leaf stays owned — "
                                 "`worker terminate` kills the group")
            add_flag(repo_root, rec, FLAG_ORPHAN)
        return False
    append_event(repo_root, rec, "error", source="system",
                 summary=f"wrapper pid {rec.pid or '-'} is gone without recording an exit; marked failed")
    set_state(repo_root, rec, "failed", pid=None)
    return True


def process_alive(rec: WorkerRecord, repo_root: Path | None = None) -> bool:
    return wrapper_alive(rec, repo_root) or harness_alive(rec)


def kill_group(rec: WorkerRecord, repo_root: Path | None = None, *, grace: float = 5.0) -> None:
    """SIGTERM the recorded process group, escalate to SIGKILL, and confirm it is gone.

    Signals only a group whose identity is confirmed: a live wrapper must
    verify by command line and token, otherwise the harness pid must match
    its recorded start time. Membership alone is not identity: once the
    group is gone its id can be a new session leader's (pre-release review).
    """
    if wrapper_alive(rec, repo_root) and not wrapper_verified(rec, repo_root):
        raise WorkerError(f"pid {rec.pid} cannot be verified as {rec.worker_id}'s wrapper (ps unavailable or "
                          "another command line); refusing to signal it")
    if not (wrapper_verified(rec, repo_root) or _harness_verified(rec)):
        raise WorkerError(f"{rec.worker_id}: neither its wrapper (by token) nor its harness pid {rec.harness_pid or '-'} "
                          f"(by start time) is alive, so process group {rec.pgid} may be another program's now; "
                          f"refusing to signal it. Check `ps -A -o pid,pgid,lstart,command`, kill what in group "
                          f"{rec.pgid} is this worker's by hand, then run `worker terminate {rec.worker_id}` again")
    pgid = rec.pgid or (os.getpgid(int(rec.pid)) if rec.pid and _exists(rec.pid) else None)
    if not pgid:
        return
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        except OSError as e:
            raise WorkerError(f"cannot signal process group {pgid}: {e}") from None
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if not _group_members(pgid):
                return
            time.sleep(0.1)
    if _group_members(pgid):
        raise WorkerError(f"{rec.worker_id}: process group {pgid} is still alive after SIGKILL")


# --- READY fingerprint (B3) and the checked-out branch (B12) ---------------

def _fingerprint(path: Path) -> str:
    return f"{path.name}:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def ready_fingerprints(repo_root: Path, node_id: str) -> list[str]:
    """``name:sha256`` of every valid READY for the node right now: the turn's starting checkpoint."""
    return sorted(_fingerprint(r.path) for r in list_ready(repo_root, node_id) if r.ok)


def new_ready(repo_root: Path, node_id: str, before: list[str]):
    """The latest valid READY that is new or changed since ``before``; ``None`` when every one was already there.

    Chosen among the new ones only: a pre-existing file with a later (or
    future) mtime must not hide the one this turn wrote.
    """
    fresh = [r for r in list_ready(repo_root, node_id) if r.ok and _fingerprint(r.path) not in before]
    if not fresh:
        return None
    return max(fresh, key=lambda r: (r.path.stat().st_mtime, r.path.name))


def branch_mismatch(worktree: Path, branch: str | None) -> str | None:
    """Why the worktree is not on the worker's branch, or ``None`` when it is (or no branch is recorded)."""
    if not branch:
        return None
    actual = git_text(["branch", "--show-current"], Path(worktree))
    if actual == branch:
        return None
    return f"{worktree} has {actual or 'a detached HEAD'} checked out, not the worker's branch {branch}"


def require_branch(rec: WorkerRecord) -> None:
    """Refuse a resume or reclaim when the worktree moved off the worker's branch; reconcile by hand first."""
    why = branch_mismatch(Path(rec.worktree), rec.branch)
    if why:
        raise WorkerError(f"{rec.worker_id}: {why}; check out the branch (or `worker terminate`) first")


def argv_too_long(argv: list[str]) -> str | None:
    size = sum(len(a.encode("utf-8")) + 1 for a in argv)
    if size <= ARGV_LIMIT:
        return None
    return (f"the launch command carries {size // 1024} KiB of arguments (limit {ARGV_LIMIT // 1024} KiB): "
            "this harness takes the prompt as an argument; shorten the brief or use a {prompt}-file command")
