"""Orchestration guard hooks, avoid lists and pre-push (M8.5)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road import orchestration_role_guard as org
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.orchestration_guard_adapters import ADAPTERS
from specy_road.review_delegate import delegate
from specy_road.review_files import reviews_dir
from specy_road.specyrd_hooks import install_orchestration_hooks, install_pre_push_hook
from specy_road.specyrd_init import run_init
from specy_road.tool_call_guard import ADAPTERS as SESSION_ADAPTERS
from specy_road.worker_adapters import Launch
from tests.helpers import script_subprocess_env
from tests.review_repo_helpers import make_review_repo
from tests.test_hook_adapters import PAYLOADS

REPO = Path(__file__).resolve().parent.parent

_HOOK_PROBE = """\
import json, os, shlex, subprocess, sys
from pathlib import Path
spec = json.loads(Path(sys.argv[1]).read_text())
payload = json.dumps({
    "session_id": "abc", "transcript_path": "/tmp/t.jsonl", "cwd": ".",
    "permission_mode": "default", "hook_event_name": "PreToolUse",
    "tool_name": "Bash", "tool_use_id": "toolu_1",
    "tool_input": {"command": spec["judged"], "description": "x", "timeout": 120000},
})
env = os.environ.copy()
r = subprocess.run(shlex.split(spec["hook_cmd"]), input=payload, capture_output=True,
                   text=True, env=env, check=False)
Path(spec["out"]).write_text(json.dumps({
    "code": r.returncode, "stderr": r.stderr,
    "role": env.get("SPECY_ROAD_ORCHESTRATION_ROLE"),
}))
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s1"}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "result": "ok", "session_id": "s1"}), flush=True)
"""


def _put_specy_road_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bindir = tmp_path / "sr-bin"
    bindir.mkdir()
    script = bindir / "specy-road"
    script.write_text(
        "#!/bin/sh\n"
        f"export PYTHONPATH={shlex.quote(str(REPO))}\n"
        f"exec {shlex.quote(sys.executable)} -m specy_road.cli \"$@\"\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | 0o111)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")


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
        ("reviewer", "git -C . commit -m x --only foo.py", True),
        ("reviewer", "GIT_EDITOR=true git commit -m x --only foo.py", True),
        ("reviewer", "git status", False),
        ("reviewer", "gh pr create", True),
        ("reviewer", "gh --repo o/r pr create", True),
        ("executor", "git commit -m x --only foo.py", False),
        ("executor", "git push origin main", True),
        ("executor", "gh --repo o/r pr create", True),
        ("executor", "claude -p --worktree foo", True),
        ("executor", "claude --cloud", True),
        ("executor", "claude -p --cloud foo", True),
        ("executor", "codex exec --cloud", True),
        ("executor", "agent -w foo", True),
        ("executor", "git status", False),
        ("executor", "grep -w foo", False),
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


def test_claude_launch_template_pins_env_switches() -> None:
    facts = (REPO / "specy_road" / "templates" / "project" / "model-profiles" / "harness-facts.yaml").read_text(
        encoding="utf-8"
    )
    assert "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p" in facts
    root = REPO / "specy_road" / "templates" / "project" / "model-profiles" / "anthropic-claude"
    missing = []
    for path in sorted(root.glob("*.md")):
        cli = next((line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("  cli:")), "")
        if "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1" not in cli or "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1" not in cli:
            missing.append(path.name)
    assert not missing, missing


def _avoid_list_gaps(rel: str, text: str, family: str) -> list[str]:
    if "## Orchestration: harness features to avoid" not in text:
        return [f"{rel}: heading"]
    fam = family.lower()
    if "anthropic" in fam or "claude" in fam:
        if "CLAUDE_CODE_DISABLE_AUTO_MEMORY=1" not in text:
            return [f"{rel}: claude memory switch"]
        return []
    if "openai" in fam or "gpt" in fam:
        return [] if "--disable memories" in text else [f"{rel}: codex --disable"]
    if "cursor" in fam or "composer" in fam:
        if "--plan" not in text or "persist" not in text:
            return [f"{rel}: cursor persist/plan"]
        return []
    if "memory off" not in text or "--plan" not in text or "worktree" not in text:
        return [f"{rel}: generic exact switches"]
    return []


def test_every_shipped_profile_lists_orchestration_avoid() -> None:
    from specy_road.model_profiles import list_profiles

    root = REPO / "specy_road" / "templates" / "project"
    missing = []
    for prof in list_profiles(root):
        if prof.path.name == "README.md":
            continue
        text = prof.path.read_text(encoding="utf-8")
        rel = str(prof.path.relative_to(root))
        missing.extend(_avoid_list_gaps(rel, text, str(prof.data.get("family") or "")))
    assert not missing, missing


def _pretool_commands(settings: dict) -> list[str]:
    cmds: list[str] = []
    for matcher in settings.get("hooks", {}).get("PreToolUse", []):
        for hook in matcher.get("hooks", []):
            cmds.append(hook["command"])
    return cmds


def test_installed_hook_denies_through_launch_without_injected_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECY_ROAD_ORCHESTRATION_ROLE", raising=False)
    _put_specy_road_on_path(tmp_path, monkeypatch)
    probe = tmp_path / "hook_probe.py"
    probe.write_text(_HOOK_PROBE, encoding="utf-8")
    exec_repo = make_review_repo(tmp_path / "exec")
    install_orchestration_hooks(exec_repo, "claude-code", dry_run=False)
    cmd = _pretool_commands(json.loads((exec_repo / ".claude" / "settings.json").read_text(encoding="utf-8")))[0]
    assert cmd == "specy-road orchestration guard --format claude-code"
    push_out, push_spec = tmp_path / "push.json", tmp_path / "push_spec.json"
    push_spec.write_text(json.dumps({"hook_cmd": cmd, "out": str(push_out), "judged": "git push origin main"}))
    rec = ws.create_record(exec_repo, "M1.1", "claude-code", "opus", exec_repo)
    wr.run(exec_repo, rec.worker_id, Launch([sys.executable, str(probe), str(push_spec)]))
    push = json.loads(push_out.read_text(encoding="utf-8"))
    assert push["role"] == "executor" and push["code"] == 2
    commit_out, commit_spec = tmp_path / "commit.json", tmp_path / "commit_spec.json"
    commit_spec.write_text(json.dumps({
        "hook_cmd": cmd, "out": str(commit_out), "judged": "git commit -m x --only foo.py",
    }))
    cli = f"{sys.executable} {probe} {commit_spec} {{prompt}}"
    roster = (
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        f"  - {{id: opus, family: anthropic, roles: [reviewer], harness: claude-code, channels: {{cli: '{cli}'}}}}\n"
    )
    rev_repo = make_review_repo(tmp_path / "rev", orchestration=roster)
    (reviews_dir(rev_repo, "M1.1")).mkdir(parents=True)
    (reviews_dir(rev_repo, "M1.1") / "PACKET.md").write_text("# Review packet\n")
    delegate(rev_repo, "M1.1", "opus", retries=0)
    commit = json.loads(commit_out.read_text(encoding="utf-8"))
    assert commit["role"] == "reviewer" and commit["code"] == 2


def test_specyrd_init_installs_one_claude_orchestration_hook(tmp_path: Path) -> None:
    run_init(
        target=tmp_path,
        agent="claude-code",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
        install_guard_hooks=True,
    )
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmds = _pretool_commands(settings)
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd == "specy-road orchestration guard --format claude-code"
    assert "SPECY_ROAD_ORCHESTRATION_ROLE=" not in cmd
    allow = _run_orch(tmp_path, "claude-code", PAYLOADS["claude-code"]("git commit -m x --only foo.py"), "executor")
    deny = _run_orch(tmp_path, "claude-code", PAYLOADS["claude-code"]("git commit -m x --only foo.py"), "reviewer")
    assert allow.returncode == 0
    assert deny.returncode == 2


def test_codex_hook_in_fresh_worktree_denies_reviewer_commit(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init"], cwd=main, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=main, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True, capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=main, check=True, capture_output=True)
    wt = main / "work" / ".worktrees" / "leaf"
    subprocess.run(["git", "worktree", "add", str(wt), "-b", "feature/x"], cwd=main, check=True, capture_output=True)
    install_orchestration_hooks(wt, "codex", dry_run=False)
    hooks = json.loads((wt / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    cmds = _pretool_commands(hooks)
    assert cmds == ["specy-road orchestration guard --format codex"]
    readme = (REPO / "specy_road" / "templates" / "specyrd" / "hooks" / "README.md").read_text(encoding="utf-8")
    assert "--dangerously-bypass-hook-trust" in readme
    r = _run_orch(wt, "codex", PAYLOADS["codex"]("git commit -m x --only foo.py"), "reviewer")
    assert r.returncode == 2
    assert "orchestration guard" in r.stderr


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
