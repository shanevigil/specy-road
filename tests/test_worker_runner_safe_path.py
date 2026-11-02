"""The wrapper imports the specy_road that launched it, not the worktree's copy (M10.16).

A leaf branch that predates a change to the runner's arguments carries an
older ``specy_road/worker_runner.py``; started with ``cwd`` in that worktree,
``python -m`` would import it first. The wrapper runs with ``-P``, which
only that interpreter sees: the harness keeps its environment and flags.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.test_worker_cli import _repo, wait_for_worker

from specy_road import worker_adapters as wa
from specy_road import worker_runner as wr
from specy_road import worker_state as ws


def test_a_broken_runner_in_the_worktree_is_not_imported(tmp_path: Path, monkeypatch) -> None:
    repo, _ = _repo(tmp_path)
    stale = repo / "specy_road"
    stale.mkdir()
    (stale / "__init__.py").write_text("")
    (stale / "worker_runner.py").write_text("raise RuntimeError('the worktree runner was imported')\n")
    seen = tmp_path / "harness-env.json"
    probe = tmp_path / "probe.py"
    probe.write_text("import json, os, sys\n"
                     f"open({str(seen)!r}, 'w').write(json.dumps({{'env': os.environ.get('PYTHONSAFEPATH'), "
                     "'flag': sys.flags.safe_path}))\n"
                     "print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 'safe'}), flush=True)\n")
    monkeypatch.delenv("PYTHONSAFEPATH", raising=False)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    wr.spawn(repo, rec, wa.Launch([sys.executable, str(probe)]))
    final = wait_for_worker(repo, rec.worker_id)
    assert final.state == "idle" and final.provider_session_id == "safe"
    assert "safe" in wr.log_path(repo, rec.worker_id).read_text(encoding="utf-8")
    last = ws.events_since(repo, rec.worker_id)[-1]
    assert last.type == "completion" and last.detail["exit"] == 0
    assert json.loads(seen.read_text()) == {"env": None, "flag": False}   # nothing safe-path reaches the harness
