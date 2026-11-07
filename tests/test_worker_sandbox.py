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
for p in spec["create"]:                    # steering the user does not have: the worker may make its own
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write("planted\n")
for p in spec["state"]:                     # transcripts, auth and seeded copies stay writable
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
    for rel, text in {".ssh/id_ed25519": "key\n", ".config/gh/hosts.yml": "token\n", ".bashrc": "# rc\n"}.items():
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(text)
    (repo / ".git" / "hooks").mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    yield {"repo": repo, "wt": wt, "home": home, "common": repo / ".git"}
    shutil.rmtree(base, ignore_errors=True)


#: Per harness, paths under the temporary home: the user's files; steering the user has (writes refused) and
#: lacks (creating it must not reach the home); transcripts and auth (writes reach the user's file); seeded
#: configuration (writable, but a per-worker copy). Codex's profile home links its auth.json to ~/.codex.
HARNESSES = {
    "claude-code": {"env": {}, "files": [".claude/settings.json", ".claude/projects/t.jsonl", ".claude/.credentials.json",
                                         ".claude.json", ".cache/claude-cli-nodejs/log"],
                    "refused": [".claude/settings.json"],
                    "create": [".claude/settings.local.json", ".claude/hooks/h.sh", ".claude/skills/s/SKILL.md",
                               ".claude/CLAUDE.md", ".cache/claude-cli-nodejs/log"],
                    "through": [".claude/projects/t.jsonl", ".claude/.credentials.json"], "seeded": [".claude.json"]},
    "cursor": {"env": {}, "files": [".cursor/hooks.json", ".cursor/cli-config.json", ".cursor/chats/c.db",
                                    ".config/cursor/auth.json"],
               "refused": [".cursor/hooks.json"],
               "create": [".cursor/mcp.json", ".cursor/rules/r.mdc", ".cursor/skills/s/SKILL.md",
                          ".config/cursor/cli.json"],
               "through": [".cursor/chats/c.db", ".config/cursor/auth.json"], "seeded": [".cursor/cli-config.json"]},
    "codex": {"env": {"CODEX_HOME": "codex-home"}, "files": ["codex-home/config.toml", "codex-home/sessions/s.jsonl",
                                                            ".codex/auth.json"],
              "refused": ["codex-home/config.toml"],
              "create": ["codex-home/AGENTS.md", "codex-home/hooks/h", "codex-home/skills/s/SKILL.md"],
              "through": ["codex-home/sessions/s.jsonl", "codex-home/auth.json"], "seeded": []},
}


def _harness_home(home: Path, harness: str) -> dict:
    h = HARNESSES[harness]
    for rel in h["files"]:
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text("user\n")
    if harness == "codex":
        (home / "codex-home" / "auth.json").symlink_to(home / ".codex" / "auth.json")
    return {k: str(home / v) for k, v in h["env"].items()}


def _turn(b: dict, rec: ws.WorkerRecord, marker: str, env: dict, *, resumed: bool) -> int:
    common, home, wt, h = b["common"], b["home"], b["wt"], HARNESSES[rec.harness]
    spec = {"marker": marker, "reviews": str(reviews_dir(b["repo"], "M1.1")),
            "probes": [str(p) for p in (common / "config", common / "hooks" / "pre-commit",
                                        common / "worktrees" / wt.name / "commondir",
                                        common / "worktrees" / wt.name / "gitdir",
                                        common / "worktrees" / wt.name / "config.worktree", wt / ".git", b["repo"] / "src" / "a.py", home / ".bashrc",
                                        *(home / r for r in h["refused"]))],
            "hidden": [str(home / ".ssh" / "id_ed25519"), str(home / ".config" / "gh" / "hosts.yml")],
            "env": list(SECRETS),
            "create": [str(home / r) for r in h["create"]],
            "state": [str(home / r) for r in h["through"] + h["seeded"]]}
    return wr.run(b["repo"], rec.worker_id, Launch([sys.executable, "-c", FAKE], stdin=json.dumps(spec), env=env),
                  resumed=resumed)


def _snapshot(paths: list[Path]) -> dict[Path, bytes | str | None]:
    """Each path and its parent: bytes for a file, ``dir`` for a directory, ``None`` when absent."""
    return {q: q.read_bytes() if q.is_file() else "dir" if q.is_dir() else None for p in paths for q in (p, p.parent)}


@pytest.mark.parametrize("harness", list(HARNESSES))
def test_a_sandboxed_launch_and_resume_commit_hand_off_ready_and_reach_nothing_else(box, harness) -> None:
    b = box
    common, home, wt, h = b["common"], b["home"], b["wt"], HARNESSES[harness]
    env = _harness_home(home, harness)
    guarded = [common / "config", common / "hooks" / "pre-commit", common / "worktrees" / wt.name / "commondir",
               common / "worktrees" / wt.name / "gitdir", wt / ".git", b["repo"] / "src" / "a.py", home / ".bashrc",
               *(home / r for r in h["refused"] + h["create"] + h["seeded"])]
    before = _snapshot(guarded)
    rec = ws.create_record(b["repo"], "M1.1", harness, "opus", wt, branch="feature/rm-thing")
    reviews = reviews_dir(b["repo"], "M1.1")
    for turn, (marker, resumed) in enumerate([("launch.txt", False), ("resume.txt", True)], 1):
        assert _turn(b, rec, marker, env, resumed=resumed) == 0
        assert git(wt, "log", "-1", "--format=%s", "feature/rm-thing") == marker      # the commit is on the branch
        assert ws.load_record(b["repo"], rec.worker_id).state == "completed"           # the READY came through
        assert (reviews / "READY-opus.md").is_file() and not (reviews / "REVIEW-opus.md").exists()
        probe = json.loads(next(line for line in reversed(wr.log_path(b["repo"], rec.worker_id).read_text()
                                                          .splitlines()) if line.startswith("PROBE "))[6:])
        assert probe == {"written": [], "seen": []}
        assert _snapshot(guarded) == before        # shared steering, created or not, and seeded config untouched
        assert (common / "worktrees" / wt.name / "config.worktree").read_bytes() == b""   # git reads it as no config
        for r in h["through"]:                     # transcripts and auth reach the user's files
            assert (home / r).read_text().count("state") == turn
    launched = [e for e in ws.events_since(b["repo"], rec.worker_id) if e.type == "launched"]
    assert [e.detail["sandbox"] for e in launched] == ["bwrap", "bwrap"]
@pytest.mark.parametrize("case", ["main checkout", "worktree without its gitdir file", "bwrap does not start",
                                  "auto without bwrap"])
def test_a_turn_the_sandbox_cannot_hold_stops_unless_auto_finds_no_sandbox(box, case, monkeypatch) -> None:
    b = box
    where = b["repo"] if case == "main checkout" else b["wt"]
    if case == "worktree without its gitdir file":   # absent, it could not be held read-only
        (b["common"] / "worktrees" / b["wt"].name / "gitdir").unlink()
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
    assert ("bwrap stopped before the harness started" if case == "bwrap does not start" else "separate --worktree") in errors


@pytest.mark.parametrize("line, mode", [("", "off"), ("worker_sandbox: false\n", "off"),
                                        ("worker_sandbox: off\n", "off"), ("worker_sandbox: auto\n", "auto"),
                                        ("worker_sandbox: bwrap\n", "bwrap")])
def test_worker_sandbox_is_off_unless_the_project_opts_in(tmp_path: Path, line: str, mode: str) -> None:
    (tmp_path / "roadmap").mkdir()
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        f"version: 1\nintegration_branch: dev\nremote: origin\n{line}")
    assert worker_sandbox_mode(tmp_path) == mode
