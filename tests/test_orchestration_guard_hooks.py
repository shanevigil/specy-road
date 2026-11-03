"""Orchestration guard hooks, avoid lists and pre-push (M8.5)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road import orchestration_role_guard as org
from specy_road.orchestration_guard_adapters import ADAPTERS
from specy_road.specyrd_hooks import install_orchestration_hooks, install_pre_push_hook
from specy_road.specyrd_init import run_init
from specy_road.tool_call_guard import ADAPTERS as SESSION_ADAPTERS
from tests.test_hook_adapters import PAYLOADS
from tests.helpers import script_subprocess_env

REPO = Path(__file__).resolve().parent.parent


def _run_orch(repo: Path, fmt: str, payload: dict, role: str, cmd: str | None = None) -> subprocess.CompletedProcess[str]:
    env = script_subprocess_env()
    env["SPECY_ROAD_ORCHESTRATION_ROLE"] = role
    args = [sys.executable, "-m", "specy_road.cli", "orchestration", "guard", "--format", fmt, "--repo-root", str(repo)]
    if cmd is not None:
        args.extend(["--command", cmd])
    return subprocess.run(
        args,
        input=None if cmd is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
        check=False,
    )


@pytest.mark.parametrize(
    ("role", "command", "blocked"),
    [
        ("reviewer", "git commit -m x --only foo.py", True),
        ("reviewer", "git status", False),
        ("reviewer", "gh pr create", True),
        ("executor", "git commit -m x --only foo.py", False),
        ("executor", "git push origin main", True),
        ("executor", "claude -p --worktree foo", True),
        ("executor", "git status", False),
    ],
)
def test_orchestration_role_rules(role: str, command: str, blocked: bool) -> None:
    v = org.decide_role(command, role=role)
    assert v.denied is blocked


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_orchestration_hook_adapters_block_like_their_harness(tmp_path: Path, fmt: str) -> None:
    repo = tmp_path
    (repo / "roadmap").mkdir()
    blocked_cmd = "git push origin main" if fmt != "generic" else "git push"
    payload = PAYLOADS.get(fmt, PAYLOADS["generic"])(blocked_cmd)
    r = _run_orch(repo, fmt, payload, "executor")
    if fmt == "cursor":
        assert r.returncode == 0
        assert json.loads(r.stdout)["permission"] == "deny"
    else:
        assert r.returncode == 2
        assert "orchestration guard" in r.stderr


def test_claude_print_config_has_on_failure_block() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "orchestration", "guard", "--format", "claude-code",
         "--print-config", "--config-role", "executor"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    hook = data["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook["onFailure"] == "block"
    assert "orchestration guard" in hook["command"]


def test_codex_launch_template_pins_disable_flags() -> None:
    facts = (REPO / "specy_road" / "templates" / "project" / "model-profiles" / "harness-facts.yaml").read_text(
        encoding="utf-8"
    )
    assert "--disable memories --disable multi_agent --disable goals" in facts
    root = REPO / "specy_road" / "templates" / "project" / "model-profiles" / "openai-gpt"
    missing = []
    for path in sorted(root.glob("*.md")):
        cli = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("  cli:"):
                cli = line
                break
        if "--disable memories" not in cli or "--disable multi_agent" not in cli or "--disable goals" not in cli:
            missing.append(path.name)
    assert not missing, missing


def test_every_shipped_profile_lists_orchestration_avoid() -> None:
    from specy_road.model_profiles import list_profiles

    root = REPO / "specy_road" / "templates" / "project"
    missing = []
    for prof in list_profiles(root):
        if prof.path.name == "README.md":
            continue
        text = prof.path.read_text(encoding="utf-8")
        if "## Orchestration: harness features to avoid" not in text:
            missing.append(str(prof.path.relative_to(root)))
    assert not missing, missing


def test_specyrd_init_installs_claude_orchestration_hooks(tmp_path: Path) -> None:
    run_init(
        target=tmp_path,
        agent="claude-code",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
        install_guard_hooks=True,
    )
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "orchestration guard" in cmd


def test_pre_push_refuses_worktree_allows_main(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init"], cwd=main, check=True, capture_output=True)
    wt = main / "work" / ".worktrees" / "leaf"
    wt.mkdir(parents=True)
    subprocess.run(["git", "worktree", "add", str(wt), "-b", "feature/x"], cwd=main, check=True, capture_output=True)
    install_pre_push_hook(main, dry_run=False)
    hook = main / ".git" / "hooks" / "pre-push"
    assert hook.is_file()
    ok = subprocess.run([str(hook)], cwd=main, capture_output=True, text=True, check=False)
    assert ok.returncode == 0
    bad = subprocess.run([str(hook)], cwd=wt, capture_output=True, text=True, check=False)
    assert bad.returncode == 1
    assert "work/.worktrees" in bad.stderr


def test_orchestration_and_session_adapters_share_harness_keys() -> None:
    assert set(ADAPTERS) == set(SESSION_ADAPTERS)
