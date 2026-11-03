"""M11.56: delegate and message/resume create the main checkout's ``work/reviews/<ID>`` before a launch names it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git
from tests.test_worker_cli import wait_for_worker
from tests.test_worker_m310_reconcile_status import nested_project

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.review_files import reviews_dir

# A default-command harness that refuses a missing allowed directory, as Cursor's `agent` does for `--add-dir`.
STRICT = '''
import json, os, sys
argv = sys.argv[1:]
for i, a in enumerate(argv):
    if a in ("--add-dir", "--workspace") and not os.path.isdir(argv[i + 1]):
        print(f"Workspace directory does not exist: {argv[i + 1]}", file=sys.stderr)
        sys.exit(1)
sid = argv[argv.index("--resume") + 1] if "--resume" in argv else argv[argv.index("--session-id") + 1] if "--session-id" in argv else "s1"
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid, "model": "fake"}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "result": "done", "session_id": sid}), flush=True)
'''

ROSTER = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
          "  - {id: cur, family: openai, roles: [executor], harness: cursor}\n"
          "  - {id: cc, family: anthropic, roles: [executor], harness: claude-code}\n"
          "policy: {max_workers: 2}\n")


@pytest.fixture
def strict_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("agent", "claude"):
        exe = bin_dir / name
        exe.write_text(f"#!{sys.executable}\n{STRICT}")
        exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin")


@pytest.mark.parametrize("model", ["cur", "cc"])
def test_a_fresh_leaf_launches_and_resumes_with_no_reviews_dir_yet(tmp_path: Path, strict_path, model: str) -> None:
    top, project = nested_project(tmp_path, ROSTER)
    git(top, "checkout", "-q", "dev")   # the worker gets a linked worktree, so the default command names the dir
    handoff = reviews_dir(project, "M1.1")
    assert not handoff.exists()
    rec, created = ops.delegate(project, "M1.1", model, offline=True)
    assert created and Path(rec.worktree) != top and handoff.is_dir()
    rec = wait_for_worker(project, rec.worker_id)
    assert rec.state == "idle" and rec.provider_session_id, [e.summary for e in ws.events_since(project, rec.worker_id)]
    handoff.rmdir()   # gone again before a resume: message recreates it
    ops.message(project, rec.worker_id, "go on\n", offline=True)
    rec = wait_for_worker(project, rec.worker_id)
    assert rec.state == "idle" and handoff.is_dir(), [e.summary for e in ws.events_since(project, rec.worker_id)]
