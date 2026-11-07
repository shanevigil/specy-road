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
from collections.abc import Callable
from pathlib import Path

from specy_road.git_subprocess import git_text
from specy_road.review_files import list_ready
from specy_road.worker_state import (
    FLAG_ORPHAN,
    WorkerError,
    WorkerRecord,
    add_flag,
    append_event,
    mutate,
    set_state,
    workers_lock,
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
        r = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,stat="], capture_output=True, text=True, check=False,
                           timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in r.stdout.splitlines():   # a zombie awaits its parent's wait(): not a member left alive
        parts = line.split()
        if len(parts) == 3 and parts[1] == str(pgid) and parts[0].isdigit() and not parts[2].startswith("Z"):
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
    from specy_road.worker_lease import release_lease   # noqa: PLC0415 — worker_lease imports this module
    with workers_lock(repo_root):   # failed and its lease gone in one step, as in the wrapper
        set_state(repo_root, rec, "failed", pid=None)
        release_lease(repo_root, rec.worker_id)
    return True


def process_alive(rec: WorkerRecord, repo_root: Path | None = None) -> bool:
    """The wrapper or the group is alive, or a terminate could not list the group's escaped descendants yet."""
    return bool(rec.descendants_unchecked) or wrapper_alive(rec, repo_root) or harness_alive(rec)


def kill_group(rec: WorkerRecord, repo_root: Path | None = None, *, grace: float = 5.0) -> None:
    """SIGTERM the recorded process group, escalate to SIGKILL, and confirm it is gone.

    Signals only a group whose identity is confirmed: a live wrapper must
    verify by command line and token, otherwise the harness pid must match
    its recorded start time. Membership alone is not identity: once the
    group is gone its id can be a new session leader's (pre-release review),
    and the verified process must be in the recorded group now (re-review N3).
    The group's descendants outside it (a command in a session of its own)
    get each signal with the group (D6, M22.20; :class:`_Descendants`). The
    record carries ``descendants_unchecked`` (saved when ``repo_root`` is
    given) from the start of that pass until it ends with every listing read
    and no survivor, so a failed or interrupted pass is repeated by the next
    call, even with the group gone (M22.20).
    """
    if rec.descendants_unchecked and rec.pgid and not _group_members(rec.pgid) and not wrapper_alive(rec, repo_root):
        _end_with_descendants(rec, repo_root, rec.pgid, grace)   # the group went with the last terminate
        return
    if wrapper_alive(rec, repo_root) and not wrapper_verified(rec, repo_root):
        raise WorkerError(f"pid {rec.pid} cannot be verified as {rec.worker_id}'s wrapper (ps unavailable or "
                          "another command line); refusing to signal it")
    verified = rec.pid if wrapper_verified(rec, repo_root) else rec.harness_pid if _harness_verified(rec) else None
    pgid = os.getpgid(int(verified)) if verified else None
    if pgid is None or pgid != (rec.pgid or pgid):
        raise WorkerError(f"{rec.worker_id}: neither its wrapper (by token) nor its harness pid {rec.harness_pid or '-'} "
                          f"(by start time) is alive in process group {rec.pgid}, so that group may be another "
                          f"program's now; refusing to signal it. Check `ps -A -o pid,pgid,lstart,command`, kill what "
                          f"in group {rec.pgid} is this worker's by hand, then run `worker terminate {rec.worker_id}` again")
    _end_with_descendants(rec, repo_root, pgid, grace, confirmed=True)


def _end_with_descendants(rec: WorkerRecord, repo_root: Path | None, pgid: int, grace: float, *,
                          confirmed: bool = False) -> None:
    """End the group and its escaped descendants together; clear the record's mark only when all is confirmed."""
    found = _Descendants(pgid, {rec.pgid, rec.pid, rec.harness_pid})
    _mark_unchecked(rec, repo_root, True)
    found.live()   # the snapshot, before the first signal; end_group's own listing rechecks each pid's start
    if not end_group(pgid, grace, confirmed=confirmed, outside=found.live):
        raise WorkerError(f"{rec.worker_id}: process group {pgid} is still alive after SIGKILL")
    live = found.live()
    if found.failed:
        raise WorkerError(f"{rec.worker_id}: process group {pgid} is gone, but `{' '.join(_INVENTORY)}` could not "
                          "list its descendants outside the group at every step; run `worker terminate` again to "
                          "repeat that pass, or check for them by hand")
    if live:
        raise WorkerError(f"{rec.worker_id}: pid(s) {', '.join(map(str, live))} outside its process group "
                          "are still alive after SIGKILL")
    _mark_unchecked(rec, repo_root, False)


def _mark_unchecked(rec: WorkerRecord, repo_root: Path | None, unchecked: bool) -> None:
    value = True if unchecked else None
    if rec.descendants_unchecked == value:
        return
    if repo_root is None:
        rec.descendants_unchecked = value
    else:
        mutate(repo_root, rec, lambda r: setattr(r, "descendants_unchecked", value))


def end_group(pgid: int, grace: float = 5.0, *, confirmed: bool = False,
              outside: Callable[[], list[int] | None] | None = None) -> bool:
    """SIGTERM process group ``pgid``, SIGKILL it after ``grace`` seconds, and wait up to 2 s more; ``True`` when no
    member is left (a group already gone is success). Never the caller's own group. A signal goes only while ``ps``
    lists a member (a gone group's id can be reused); ``confirmed``: the caller verified a member itself
    (:func:`kill_group`), so the first signal needs no listing. ``outside``: called at every step for the pids
    outside the group to signal with it (``None``: it cannot say, so the wait goes on); the caller checks them
    afterwards. Used by :func:`kill_group` and by the reviewer runners (M22.16), whose reviewer runs in a session
    of its own."""
    if pgid <= 1 or pgid == os.getpgrp():
        return False
    check = outside or list
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 2.0)):
        group = confirmed or bool(_group_members(pgid))
        confirmed = False
        rest = check()
        if not group and rest == []:
            return True
        _signal(pgid if group else None, rest or [], sig)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if not _group_members(pgid) and check() == []:
                return True
            time.sleep(0.1)
    return not _group_members(pgid)


def _signal(pgid: int | None, pids: list[int], sig: int) -> None:
    """``sig`` to group ``pgid`` (when given) and to each of ``pids``; one already gone is no error."""
    targets = [(os.killpg, pgid, f"process group {pgid}")] if pgid else []
    targets += [(os.kill, pid, f"pid {pid} outside the process group") for pid in pids]
    for send, target, what in targets:
        try:
            send(target, sig)
        except ProcessLookupError:
            pass
        except OSError as e:
            raise WorkerError(f"cannot signal {what}: {e}") from None


_INVENTORY = ["ps", "-A", "-ww", "-o", "pid=,ppid=,pgid=,stat=,lstart="]


def _process_table() -> list[tuple[int, int, int, str, str]] | None:
    """``(pid, ppid, pgid, stat, lstart)`` of every process; ``None`` when ``ps`` fails, times out or a line does not
    parse.

    ``lstart`` is the rest of the line, stripped, as :func:`start_token` reads it.
    """
    try:
        r = subprocess.run(_INVENTORY, capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 4)
        if not parts:
            continue
        if len(parts) != 5 or not all(p.isdigit() for p in parts[:3]):
            return None
        rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3], parts[4].strip()))
    return rows


class _Descendants:
    """The group's descendants outside it, listed again at every step of one terminate pass (M22.20).

    A harness's tool can start a command in a session of its own (Cursor's shell
    tool does), so ``killpg`` never reaches it (D6). The rule, at every listing:
    walk parent links from the group's members, from each pid already found that
    still runs with its start time, and from each recorded pid no process holds
    now (a process still naming it as parent was not re-parented yet; a held one
    is a reused pid). Every process reached outside the group joins with its
    start time, so a child forked during the grace by one already found is
    signalled at the next step. A pid counts as running only with that start
    time (a changed start is a reused pid) and not as a zombie. Limit: a process
    re-parented before any listing reached it is out of reach.
    """

    def __init__(self, pgid: int, recorded: set[int | None]) -> None:
        self.pgid, self.recorded = pgid, {p for p in recorded if p and p > 1}
        self.known: dict[int, str] = {}
        self.failed = False   # some listing in this pass could not be read

    def live(self) -> list[int] | None:
        """List again, add what the walk reaches, and return the found pids still running; ``None``: ``ps`` failed."""
        rows = _process_table()
        if rows is None:
            self.failed = True
            return None
        children: dict[int, list[int]] = {}
        for pid, ppid, _, _, _ in rows:
            children.setdefault(ppid, []).append(pid)
        info = {pid: (pg, start) for pid, _, pg, _, start in rows}
        todo = [pid for pid, (pg, _) in info.items() if pg == self.pgid]
        todo += self._running(rows) + [p for p in self.recorded if p not in info]
        seen = set(todo)
        while todo:
            for child in children.get(todo.pop(), []):
                if child not in seen:
                    seen.add(child)
                    todo.append(child)
                    if info[child][0] != self.pgid:
                        self.known.setdefault(child, info[child][1])
        return self._running(rows)

    def _running(self, rows: list[tuple[int, int, int, str, str]]) -> list[int]:
        return sorted(pid for pid, _, _, stat, start in rows
                      if self.known.get(pid) == start and not stat.startswith("Z"))


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
