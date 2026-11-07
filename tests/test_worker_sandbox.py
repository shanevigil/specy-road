"""M22.44: an unattended worker's turn runs in a read-only bwrap sandbox, driven through the public runner.

The repo lives under ``/var/tmp``, not ``/tmp``: the sandbox mounts a private tmpfs on ``/tmp``, which would hide
a ``/tmp`` repo outright and so never test that the read-only root refuses the writes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo

from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.git_workflow_config import worker_sandbox_mode
from specy_road.review_files import reviews_dir
from specy_road.worker_adapters import Launch


def _bwrap_starts() -> bool:
    if not sys.platform.startswith("linux") or shutil.which("bwrap") is None:
        return False
    return subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(not _bwrap_starts(), reason="bwrap is missing or cannot start here")

#: The fake harness: commits, writes READY and a REVIEW at the canonical path, then probes each write and read.
FAKE = r'''
import json, os, subprocess, sys
spec = json.loads(sys.stdin.read())
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-1", "model": "fake"}), flush=True)
open(spec["marker"], "w").write("ran\n")
subprocess.run(["git", "add", spec["marker"]], check=True)
subprocess.run(["git", "commit", "-qm", spec["marker"]], check=True)
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
os.makedirs(spec["reviews"], exist_ok=True)
open(os.path.join(spec["reviews"], "READY-opus.md"), "w").write(
    f"---\nnode_id: M1.1\nagent: opus\nbranch: feature/rm-thing\ncommit: {head}\nbase: {head}\n"
    "changed_paths: []\nverify: []\n---\n")
open(os.path.join(spec["reviews"], "REVIEW-opus.md"), "w").write("---\nverdict: approve\n---\n")
written = []
for p in spec["probes"]:
    try:
        with open(p, "a") as f:
            f.write("probe\n")
        written.append(p)
    except OSError:
        pass
seen = [p for p in spec["hidden"] if os.path.exists(p)] + [k for k in spec["env"] if k in os.environ]
for p in spec["state"]:                     # the harness's own transcript and state stay writable
    with open(p, "a") as f:
        f.write("state\n")
print("PROBE " + json.dumps({"written": written, "seen": seen}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "result": "done", "session_id": "s-1"}), flush=True)
'''

SECRETS = {"SSH_AUTH_SOCK": "/nonexistent/agent.sock", "GH_TOKEN": "gh-dummy", "GITHUB_TOKEN": "ghp-dummy"}


@pytest.fixture
def box(monkeypatch) -> dict:
    """A repo opted in to ``worker_sandbox: bwrap``, a linked worktree on the leaf, and a temporary home."""
    try:
        base = Path(tempfile.mkdtemp(prefix="sr-sandbox-", dir="/var/tmp")).resolve()
    except OSError:
        pytest.skip("/var/tmp is not writable")
    repo = make_review_repo(base)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                "version: 1\nintegration_branch: dev\nremote: origin\nworker_sandbox: bwrap\n", "opt in")
    commit_file(repo, ".gitignore", "work/\n", "ignore work")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    git(repo, "checkout", "-q", "dev")
    wt = base / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    home = base / "home"
    for rel, text in {".ssh/id_ed25519": "key\n", ".config/gh/hosts.yml": "token\n", ".bashrc": "# rc\n",
                      ".claude/settings.json": "{}\n", ".claude/projects/t.jsonl": "", ".claude.json": "{}\n"}.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(text)
    (repo / ".git" / "hooks").mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    yield {"repo": repo, "wt": wt, "home": home, "common": repo / ".git"}
    shutil.rmtree(base, ignore_errors=True)


def _turn(b: dict, rec: ws.WorkerRecord, marker: str, *, resumed: bool) -> int:
    common, home, wt = b["common"], b["home"], b["wt"]
    spec = {"marker": marker, "reviews": str(reviews_dir(b["repo"], "M1.1")),
            "probes": [str(p) for p in (common / "config", common / "hooks" / "pre-commit",
                                        common / "worktrees" / wt.name / "commondir",
                                        common / "worktrees" / wt.name / "gitdir",
                                        b["repo"] / "src" / "a.py", home / ".bashrc", home / ".claude" / "settings.json")],
            "hidden": [str(home / ".ssh" / "id_ed25519"), str(home / ".config" / "gh" / "hosts.yml")],
            "env": list(SECRETS),
            "state": [str(home / ".claude" / "projects" / "t.jsonl"), str(home / ".claude.json")]}
    return wr.run(b["repo"], rec.worker_id, Launch([sys.executable, "-c", FAKE], stdin=json.dumps(spec)),
                  resumed=resumed)


def _snapshot(paths: list[Path]) -> dict[Path, bytes | None]:
    return {p: p.read_bytes() if p.is_file() else None for p in paths}


@pytest.mark.parametrize("turns", [[("launch.txt", False), ("resume.txt", True)]])
def test_a_sandboxed_launch_and_resume_commit_hand_off_ready_and_reach_nothing_else(box, turns) -> None:
    b = box
    common, home, wt = b["common"], b["home"], b["wt"]
    guarded = [common / "config", common / "hooks" / "pre-commit", common / "worktrees" / wt.name / "commondir",
               common / "worktrees" / wt.name / "gitdir", b["repo"] / "src" / "a.py", home / ".bashrc",
               home / ".claude" / "settings.json", home / ".claude.json"]
    before = _snapshot(guarded)
    rec = ws.create_record(b["repo"], "M1.1", "claude-code", "opus", wt, branch="feature/rm-thing")
    reviews = reviews_dir(b["repo"], "M1.1")
    for marker, resumed in turns:
        assert _turn(b, rec, marker, resumed=resumed) == 0
        assert git(wt, "log", "-1", "--format=%s", "feature/rm-thing") == marker      # the commit is on the branch
        assert ws.load_record(b["repo"], rec.worker_id).state == "completed"           # the READY came through
        assert (reviews / "READY-opus.md").is_file() and not (reviews / "REVIEW-opus.md").exists()
        probe = json.loads(next(line for line in reversed(wr.log_path(b["repo"], rec.worker_id).read_text()
                                                          .splitlines()) if line.startswith("PROBE "))[6:])
        assert probe == {"written": [], "seen": []}
        assert _snapshot(guarded) == before
        assert "state" in (home / ".claude" / "projects" / "t.jsonl").read_text()   # the transcript dir is writable
        assert "state" in (ws.workers_dir(b["repo"]) / f"{rec.worker_id}.claude.json").read_text()   # per-worker copy
    launched = [e for e in ws.events_since(b["repo"], rec.worker_id) if e.type == "launched"]
    assert [e.detail["sandbox"] for e in launched] == ["bwrap", "bwrap"]


@pytest.mark.parametrize("case", ["main checkout", "bwrap does not start", "auto without bwrap"])
def test_a_turn_the_sandbox_cannot_hold_stops_unless_auto_finds_no_sandbox(box, case, monkeypatch) -> None:
    b = box
    where = b["repo"] if case == "main checkout" else b["wt"]
    if case == "bwrap does not start":
        fake = b["home"] / "bin"
        fake.mkdir()
        (fake / "bwrap").write_text("#!/bin/sh\necho 'bwrap: setting up uid map: Permission denied' >&2\nexit 1\n")
        (fake / "bwrap").chmod(0o755)
        monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    if case == "auto without bwrap":
        (b["repo"] / "roadmap" / "git-workflow.yaml").write_text(
            "version: 1\nintegration_branch: dev\nremote: origin\nworker_sandbox: auto\n")
        monkeypatch.setenv("PATH", str(b["home"]))   # no bwrap on PATH; the fake harness runs by absolute path
    rec = ws.create_record(b["repo"], "M1.1", "claude-code", "opus", where, branch="feature/rm-thing")
    marker = Path(where) / "ran.txt"
    code = wr.run(b["repo"], rec.worker_id, Launch([sys.executable, "-c", f"open({str(marker)!r}, 'w')"]))
    events = ws.events_since(b["repo"], rec.worker_id)
    if case == "auto without bwrap":
        assert code == 0 and marker.is_file()
        assert "warning: no worker sandbox" in next(e.summary for e in events if e.type == "launched")
        return
    assert code != 0 and not marker.exists() and ws.load_record(b["repo"], rec.worker_id).state == "failed"
    errors = " ".join(e.summary for e in events if e.type == "error")
    assert ("separate --worktree" if case == "main checkout" else "bwrap stopped before the harness started") in errors


@pytest.mark.parametrize("line, mode", [("", "off"), ("worker_sandbox: false\n", "off"),
                                        ("worker_sandbox: off\n", "off"), ("worker_sandbox: auto\n", "auto"),
                                        ("worker_sandbox: bwrap\n", "bwrap")])
def test_worker_sandbox_is_off_unless_the_project_opts_in(tmp_path: Path, line: str, mode: str) -> None:
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        f"version: 1\nintegration_branch: dev\nremote: origin\n{line}")
    assert worker_sandbox_mode(tmp_path) == mode
