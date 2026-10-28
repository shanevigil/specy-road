"""A harness killed by a signal under a live wrapper (sandbox runbook §5 step 9b (ii)).

The wrapper records an ``error`` event and marks the worker ``failed``; a
failed worker is closed, so ``resume`` refuses it. The exit code is ``-9``
where the adapter's ``sh -c`` execs the harness (bash, macOS) and ``137``
where it forks it (dash, the Debian/Ubuntu ``/bin/sh``).
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

from tests.test_worker_cli import _repo

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws

KILLED = '''
import json, os, signal
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-killed", "model": "fake"}), flush=True)
os.kill(os.getpid(), signal.SIGKILL)
'''


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="POSIX signals")
def test_a_killed_harness_leaves_the_worker_failed(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    script = tmp_path / "killed.py"
    script.write_text(KILLED)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("go")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    launch = wa.adapter_for("claude-code").launch(prompt, repo, "opus", f"{sys.executable} {script} {{prompt}}")
    code = wr.run(repo, rec.worker_id, launch)
    assert code in (-signal.SIGKILL, 128 + signal.SIGKILL)
    after = ws.load_record(repo, rec.worker_id)
    assert after.state == "failed" and after.pid is None and after.provider_session_id == "s-killed"
    err = [e for e in ws.events_since(repo, rec.worker_id) if e.type == "error"]
    assert len(err) == 1 and err[0].source == "worker" and err[0].detail["exit"] == code
    with pytest.raises(ws.WorkerError, match="is failed; delegate again instead"):
        ops.resume(repo, rec.worker_id)
