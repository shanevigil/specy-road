"""``CLAUDE_CONFIG_DIR`` selects the account whose transcripts and memory specy-road reads."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from specy_road import harness_instruction_files as hif
from specy_road.bundled_scripts import grind_session_implement as gsi
from specy_road.claude_config import claude_projects_dir
from specy_road.worker_adapter_claude import ClaudeCode

ROOT = Path(__file__).resolve().parent.parent
SID = "7f1c0000-0000-4000-8000-000000000001"


def _account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home with no transcripts, and an account directory selected by the variable."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "home"))
    account = tmp_path / "accounts" / "work" / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(account))
    return account


def test_the_default_is_the_home_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert claude_projects_dir() == tmp_path / ".claude" / "projects"


def test_an_empty_variable_means_the_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "")
    assert claude_projects_dir() == tmp_path / ".claude" / "projects"


def test_the_variable_selects_the_account(tmp_path, monkeypatch) -> None:
    account = _account(tmp_path, monkeypatch)
    assert claude_projects_dir() == account / "projects"


def test_an_explicit_home_ignores_the_variable(tmp_path, monkeypatch) -> None:
    _account(tmp_path, monkeypatch)
    assert claude_projects_dir(tmp_path / "x") == tmp_path / "x" / ".claude" / "projects"


def test_grind_finds_the_session_in_the_selected_account(tmp_path, monkeypatch) -> None:
    project = _account(tmp_path, monkeypatch) / "projects" / "-repo-app"
    project.mkdir(parents=True)
    (project / "right-session.jsonl").write_text("{}", encoding="utf-8")
    assert gsi.latest_session_id(Path("/repo/app")) == "right-session"


def test_memory_comes_from_the_selected_account(tmp_path, monkeypatch) -> None:
    account = _account(tmp_path, monkeypatch)
    top = tmp_path / "app"  # not a git checkout: the directory is its own main worktree
    top.mkdir()
    memory = account / "projects" / re.sub(r"[^A-Za-z0-9]", "-", top.as_posix()) / "memory" / "MEMORY.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("note\n", encoding="utf-8")
    assert hif.claude_memory_file(top) == memory


def test_a_transcript_limit_is_read_from_the_selected_account(tmp_path, monkeypatch) -> None:
    project = _account(tmp_path, monkeypatch) / "projects" / "-repo-app"
    project.mkdir(parents=True)
    entry = {"type": "assistant", "message": {"content": [{"type": "text", "text": "You've hit your usage limit"}]}}
    (project / f"{SID}.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    assert ClaudeCode.transcript_limit(SID).type == "usage_limited"


@pytest.mark.parametrize("wrapper", ["claude-worker.sh", "fable-worker.sh"])
@pytest.mark.parametrize("exists,flag", [(True, "--resume"), (False, "--session-id")])
def test_the_wrappers_look_in_the_selected_account(tmp_path, wrapper, exists, flag) -> None:
    script = ROOT / "sr" / "tools" / wrapper
    if not script.is_file():
        pytest.skip("sr/ is not on this line")
    home, account = tmp_path / "home", tmp_path / "account"
    fake = home / ".local" / "bin" / "claude"
    fake.parent.mkdir(parents=True)
    fake.write_text('#!/bin/sh\necho "$@"\n', encoding="utf-8")
    fake.chmod(0o755)
    project = (account if exists else home / ".claude") / "projects" / "-repo"
    project.mkdir(parents=True)
    (project / f"{SID}.jsonl").write_text("{}", encoding="utf-8")
    prompt = tmp_path / "prompt"
    prompt.write_text("go", encoding="utf-8")
    env = {**os.environ, "HOME": str(home), "CLAUDE_CONFIG_DIR": str(account),
           "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}"}
    out = subprocess.run(["sh", str(script), SID, str(prompt)], cwd=ROOT, env=env,
                         capture_output=True, text=True, check=True).stdout
    assert f"{flag} {SID}" in out
