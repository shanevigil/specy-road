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
from specy_road import worker_state as ws


def _gone_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
def test_terminate_never_signals_a_reused_process_group(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
        wrapper, harness = _gone_pid(), _gone_pid()

        def stale(r: ws.WorkerRecord) -> None:   # wrapper and harness gone; their group id now the stranger's
            r.state, r.pid, r.wrapper_token, r.pgid = "running", wrapper, "tok", stranger.pid
            r.harness_pid, r.harness_start = harness, "Thu Jan  1 00:00:00 2026"
        ws.mutate(repo, rec, stale)
        with pytest.raises(ws.WorkerError, match="refusing to signal"):
            ops.terminate(repo, rec.worker_id)
        assert stranger.poll() is None and ws.load_record(repo, rec.worker_id).state == "running"
    finally:
        stranger.kill()
        stranger.wait()
