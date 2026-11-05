"""Public helpers for ``specy-road worker`` CLI tests (promoted from ``test_worker_cli``)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli


def run_worker_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        worker_cli.main(list(args))
    return e.value.code or 0


def wait_for_worker(repo: Path, wid: str, timeout: float = 10) -> ws.WorkerRecord:
    for _ in range(int(timeout * 10)):
        rec = ws.load_record(repo, wid)
        if rec.pid is None:
            return rec
        time.sleep(0.1)
    raise AssertionError("worker did not finish")
