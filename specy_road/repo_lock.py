"""FIFO repository lock for pickup, finish and abort in a shared checkout.

The lock lives under ``<git-common-dir>/specy-road/repo-lock/`` so every
worktree of one clone shares one queue. Waiters take numbered tickets, acquire
in order, and stale holders or queue entries whose pid is gone are cleared. A pid
is reused (and the files survive a reboot), so each also records its process's
start time (:func:`worker_process.start_token`); a live pid that started at
another time is a different process, and its entry is stale too.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from specy_road.git_subprocess import git_text

DEFAULT_TIMEOUT_S = 7200.0
_POLL_S = 0.25
_WAIT_LOG_INTERVAL_S = 60.0


class RepoLockTimeout(SystemExit):
    """Raised when ``pickup_finish_lock`` waits longer than ``timeout``."""


def lock_root(repo_root: Path) -> Path:
    common = git_text(["rev-parse", "--git-common-dir"], repo_root)
    if not common:
        raise SystemExit(f"error: cannot resolve git common dir from {repo_root}")
    root = Path(repo_root, common) / "specy-road" / "repo-lock"
    root.mkdir(parents=True, exist_ok=True)
    (root / "queue").mkdir(exist_ok=True)
    return root


def _start_token(pid: int) -> str | None:
    from specy_road.worker_process import start_token   # lazy: worker_process pulls in the worker modules

    return start_token(pid)


def _pid_alive(pid: int, start: str | None = None) -> bool:
    """``pid`` runs, and, when ``start`` was recorded, is the process that started then."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    now = _start_token(pid) if start else None
    return not (start and now and now != start)   # ps cannot say: trust the pid


def ticket_pid(name: str) -> int | None:
    try:
        return int(name.rsplit("-", 1)[-1])
    except ValueError:
        return None


def _read_holder(path: Path) -> tuple[int, str, str | None] | None:
    """``(pid, operation, start token or None)`` from the holder file."""
    if not path.is_file():
        return None
    pid: int | None = None
    operation, start = "?", None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("pid="):
            try:
                pid = int(line.removeprefix("pid=").strip())
            except ValueError:
                pid = None
        elif line.startswith("operation="):
            operation = line.removeprefix("operation=").strip() or "?"
        elif line.startswith("start="):
            start = line.removeprefix("start=").strip() or None
    return (pid, operation, start) if pid is not None else None


def _clear_stale_holder(holder: Path) -> None:
    info = _read_holder(holder)
    if info and not _pid_alive(info[0], info[2]):
        with contextlib.suppress(OSError):
            holder.unlink()


def _prune_dead_tickets(queue: Path, *, keep: Path) -> None:
    for ticket in queue.iterdir():
        if not ticket.is_file() or ticket == keep:
            continue
        pid = ticket_pid(ticket.name)
        with contextlib.suppress(OSError):
            if pid is not None and not _pid_alive(pid, ticket.read_text(encoding="utf-8").strip() or None):
                ticket.unlink()


def new_ticket(queue: Path) -> Path:
    """A queue entry named ``<monotonic ns>-…-<own pid>`` (the pid last: :func:`ticket_pid` reads it), holding
    this process's start token."""
    ticket = queue / f"{time.monotonic_ns():019d}-{os.getpid()}"
    try:
        ticket.touch(exist_ok=False)
    except FileExistsError:
        ticket = queue / f"{time.monotonic_ns():019d}-{os.getppid()}-{os.getpid()}"
        ticket.touch(exist_ok=False)
    ticket.write_text(_start_token(os.getpid()) or "", encoding="utf-8")
    return ticket


def _sorted_tickets(queue: Path) -> list[Path]:
    return sorted(p for p in queue.iterdir() if p.is_file())


def _try_acquire(holder: Path, ticket: Path, operation: str) -> bool:
    _clear_stale_holder(holder)
    if holder.exists():
        return False
    queue = ticket.parent
    tickets = _sorted_tickets(queue)
    if not tickets or tickets[0].name != ticket.name:
        return False
    try:
        with holder.open("x", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\noperation={operation}\nticket={ticket.name}\n"
                    f"start={_start_token(os.getpid()) or ''}\n")
    except FileExistsError:
        return False
    return True


def _wait_message(holder: Path) -> str:
    info = _read_holder(holder)
    if not info:
        return "another pickup, finish or abort holds the repository lock"
    pid, operation, _start = info
    return (
        f"repository lock held by pid {pid} ({operation}); "
        "waiting for pickup, finish or abort to finish"
    )


@contextlib.contextmanager
def pickup_finish_lock(
    repo_root: Path,
    *,
    operation: str,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Iterator[None]:
    """Exclusive lock before branch switches or registry commits in a shared checkout."""
    root = lock_root(repo_root)
    queue = root / "queue"
    holder = root / "holder"
    ticket = new_ticket(queue)
    deadline = time.monotonic() + timeout
    last_log = 0.0
    try:
        while True:
            _prune_dead_tickets(queue, keep=ticket)
            if _try_acquire(holder, ticket, operation):
                break
            now = time.monotonic()
            if now >= deadline:
                msg = _wait_message(holder)
                raise RepoLockTimeout(
                    f"error: timed out after {int(timeout)}s waiting for the repository lock "
                    f"({msg}). If that process is gone, delete {holder}."
                )
            if now - last_log >= _WAIT_LOG_INTERVAL_S or last_log == 0.0:
                print(_wait_message(holder), file=sys.stderr)
                last_log = now
            time.sleep(_POLL_S)
        yield
    finally:
        with contextlib.suppress(OSError):
            ticket.unlink()
        info = _read_holder(holder)
        if info and info[0] == os.getpid():
            with contextlib.suppress(OSError):
                holder.unlink()
