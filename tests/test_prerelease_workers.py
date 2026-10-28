"""Regressions from the pre-release review of the worker layer (2026-10-28).

``terminate`` signals a process group only while this worker's wrapper (by its
token) or its harness (by its start time) vouches for it: a group id outlives
nothing, and a new session leader can reuse it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road import worker_ops as ops
from specy_road import worker_process as wp
from specy_road import worker_state as ws


def _gone_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
@pytest.mark.parametrize("harness_alive", [False, True])
def test_terminate_never_signals_a_reused_process_group(tmp_path: Path, harness_alive: bool) -> None:
    # Re-review N3: a live, verified harness vouches only for the group it is in now.
    repo = make_review_repo(tmp_path)
    stranger = _sleeper()
    live = _sleeper() if harness_alive else None
    try:
        rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
        wrapper = _gone_pid()
        harness = live.pid if live else _gone_pid()
        start = wp.start_token(harness) if live else "Thu Jan  1 00:00:00 2026"

        def stale(r: ws.WorkerRecord) -> None:   # the wrapper gone; the group id on record now the stranger's
            r.state, r.pid, r.wrapper_token, r.pgid = "running", wrapper, "tok", stranger.pid
            r.harness_pid, r.harness_start = harness, start
        ws.mutate(repo, rec, stale)
        with pytest.raises(ws.WorkerError, match="refusing to signal"):
            ops.terminate(repo, rec.worker_id)
        assert stranger.poll() is None and ws.load_record(repo, rec.worker_id).state == "running"
    finally:
        for p in (stranger, live):
            if p:
                p.kill()
                p.wait()
