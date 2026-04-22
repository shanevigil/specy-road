"""Re-entry guard for ``specy-road start-milestone-session``.

Calling the script a second time on a parent that already carries an
``active`` (or ``pending_mr``) ``milestone_execution`` must refuse cleanly
with the documented hint pointing at ``reconcile-milestone-status``.
The test stages a real git repo so the script's git sync path can run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from tests.helpers import REPO, script_subprocess_env


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo)


def _stage_dogfood_with_git(tmp_path: Path) -> Path:
    """Copy dogfood + init a git repo so start-milestone-session can fast-forward."""
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", str(bare)])

    src = REPO / "tests" / "fixtures" / "specy_road_dogfood"
    work = tmp_path / "repo"
    shutil.copytree(src, work)
    _git(work, "init", "-q", "-b", "dev")
    _git(work, "config", "user.email", "t@e.com")
    _git(work, "config", "user.name", "T")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init dogfood copy")
    _git(work, "push", "-q", "-u", "origin", "dev")
    return work


def _set_codename_for(repo_root: Path, node_id: str, codename: str) -> None:
    """Force a known codename on a parent so start-milestone-session can branch from it."""
    for chunk in (repo_root / "roadmap" / "phases").glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        nodes = doc["nodes"] if isinstance(doc, dict) else doc
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == node_id:
                n["codename"] = codename
                chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
                return
    raise AssertionError(f"unknown node id {node_id!r}")


def _attach_active_lock_to(repo_root: Path, parent_id: str) -> None:
    for chunk in (repo_root / "roadmap" / "phases").glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        nodes = doc["nodes"] if isinstance(doc, dict) else doc
        changed = False
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == parent_id:
                n["milestone_execution"] = {
                    "state": "active",
                    "rollup_branch": f"feature/rm-{n.get('codename') or 'tmp'}",
                    "integration_branch": "dev",
                    "remote": "origin",
                }
                changed = True
        if changed:
            chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            return
    raise AssertionError(f"could not find chunk for {parent_id!r}")


def _run_start(repo: Path, parent_id: str) -> subprocess.CompletedProcess[str]:
    script = (
        REPO / "specy_road" / "bundled_scripts" / "start_milestone_session.py"
    )
    env = script_subprocess_env()
    return subprocess.run(
        [
            sys.executable,
            str(script),
            parent_id,
            "--repo-root",
            str(repo),
            "--base",
            "dev",
            "--remote",
            "origin",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )


def test_start_milestone_session_refuses_when_already_active(tmp_path: Path) -> None:
    """A second start on an active parent must exit non-zero with a clear hint."""
    repo = _stage_dogfood_with_git(tmp_path)
    # M0 has child phases — fine for a parent. Tag with active milestone.
    _set_codename_for(repo, "M0", "phase-zero")
    _attach_active_lock_to(repo, "M0")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "tag active milestone_execution on M0")
    _git(repo, "push", "-q", "origin", "dev")

    r = _run_start(repo, "M0")
    assert r.returncode != 0, (
        f"expected non-zero exit on re-entry, got 0\n"
        f"--stdout--\n{r.stdout}\n--stderr--\n{r.stderr}"
    )
    err = r.stderr
    assert "milestone_execution" in err
    # Documented hint must point at reconcile-milestone-status.
    assert "reconcile-milestone-status" in err
    # No traceback should leak — the script must surface a clean error.
    assert "Traceback" not in err
