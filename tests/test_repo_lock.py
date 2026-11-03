"""Repository lock for pickup, finish and abort in a shared checkout (M11.74)."""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import time
from pathlib import Path

import pytest

from specy_road.repo_lock import lock_root, pickup_finish_lock


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
