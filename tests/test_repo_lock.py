"""Repository lock for pickup, finish and abort in a shared checkout (M11.74)."""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import time
from pathlib import Path

import pytest

from specy_road.repo_lock import RepoLockTimeout, _new_ticket, _ticket_pid, lock_root, pickup_finish_lock
from specy_road.worker_process import start_token


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "f").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
    return repo


def _counter_worker(repo: Path, shared: mp.Value, lock: mp.Lock) -> None:
    with pickup_finish_lock(repo, operation="test-worker"):
        with lock:
            cur = shared.value
        time.sleep(0.15)
        with lock:
            shared.value = cur + 1


def test_two_concurrent_callers_serialize(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    shared = mp.Value("i", 0)
    lock = mp.Lock()
    p1 = mp.Process(target=_counter_worker, args=(repo, shared, lock))
    p2 = mp.Process(target=_counter_worker, args=(repo, shared, lock))
    p1.start()
    p2.start()
    p1.join(timeout=30)
    p2.join(timeout=30)
    assert p1.exitcode == 0 and p2.exitcode == 0
    assert shared.value == 2


def test_stale_holder_from_killed_process_is_cleared(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    root = lock_root(repo)
    holder = root / "holder"
    holder.write_text("pid=999999999\noperation=do-next-available-task\n", encoding="utf-8")
    (root / "queue" / "0000000000000000000-999999999").touch()
    with pickup_finish_lock(repo, operation="finish-this-task", timeout=5):
        assert holder.is_file()
        text = holder.read_text(encoding="utf-8")
        assert f"pid={os.getpid()}" in text
    assert not holder.exists()


def test_permission_denied_holder_is_not_stolen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _git_repo(tmp_path)
    root = lock_root(repo)
    holder = root / "holder"
    holder.write_text("pid=1\noperation=do-next-available-task\n", encoding="utf-8")
    (root / "queue" / "0000000000000000000-1").touch()

    def no_signal(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "kill", no_signal)
    with pytest.raises(RepoLockTimeout):
        with pickup_finish_lock(repo, operation="finish-this-task", timeout=1):
            pytest.fail("acquired a lock held by a process we cannot signal")
    assert holder.read_text(encoding="utf-8").startswith("pid=1")


def test_a_reused_pid_does_not_keep_a_dead_holder_or_ticket(tmp_path: Path) -> None:
    """The holder's pid is alive again (here: our parent), but it started at another time: stale."""
    repo = _git_repo(tmp_path)
    root = lock_root(repo)
    holder = root / "holder"
    other = os.getppid()
    holder.write_text(f"pid={other}\noperation=do-next-available-task\nstart=Mon Jan  1 00:00:00 2001\n",
                      encoding="utf-8")
    (root / "queue" / f"0000000000000000000-{other}").write_text("Mon Jan  1 00:00:00 2001", encoding="utf-8")
    with pickup_finish_lock(repo, operation="finish-this-task", timeout=5):
        text = holder.read_text(encoding="utf-8")
        assert f"pid={os.getpid()}" in text
        assert f"start={start_token(os.getpid())}" in text
    assert not holder.exists() and not list((root / "queue").iterdir())


def test_a_live_holder_with_its_own_start_time_is_kept_and_the_timeout_names_the_file(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    root = lock_root(repo)
    holder = root / "holder"
    other = os.getppid()
    holder.write_text(f"pid={other}\noperation=do-next-available-task\nstart={start_token(other)}\n",
                      encoding="utf-8")
    with pytest.raises(RepoLockTimeout) as e:
        with pickup_finish_lock(repo, operation="finish-this-task", timeout=0.5):
            pytest.fail("acquired a lock its live holder still holds")
    assert str(holder) in str(e.value)


def test_the_fallback_ticket_name_ends_with_this_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue = lock_root(_git_repo(tmp_path)) / "queue"
    monkeypatch.setattr(time, "monotonic_ns", lambda: 7)
    first, second = _new_ticket(queue), _new_ticket(queue)   # the second name collides, then falls back
    assert first != second and _ticket_pid(second.name) == _ticket_pid(first.name) == os.getpid()
