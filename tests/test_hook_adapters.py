"""Run each registered hook adapter exactly as its harness will (proposal §3.5).

A harness hook is a subprocess fed a JSON payload on stdin; what it reads,
which exit code blocks, and which channel the model sees differ per harness.
These tests drive `specy-road session guard --format <adapter>` as a real
subprocess with the payload shape each adapter documents, so an adapter that
drifts from its harness's contract fails here rather than in someone's IDE.
Parametrised over the adapter table: a new adapter is covered when added.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import script_subprocess_env
from tests.review_repo_helpers import make_review_repo

from specy_road import session_presence as sp
from specy_road.tool_call_guard import ADAPTERS

REPO = Path(__file__).resolve().parent.parent

#: The stdin each harness sends for a shell command, as documented.
def _pre_tool_use(cmd: str) -> dict:
    return {
        "session_id": "abc", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp", "permission_mode": "default",
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "toolu_1",
        "tool_input": {"command": cmd, "description": "x", "timeout": 120000},
    }


PAYLOADS = {
    "generic": lambda cmd: {"command": cmd},
    "claude-code": _pre_tool_use,
    "codex": _pre_tool_use,
    "cursor": lambda cmd: {"conversation_id": "c", "generation_id": "g", "hook_event_name": "beforeShellExecution",
                           "workspace_roots": ["/tmp"], "command": cmd, "cwd": "/tmp", "sandbox": False},
}

#: How each harness reads a deny and an allow, per its docs.
DENY = {   # (exit code, where the reason appears)
    "generic": (2, "stderr"), "claude-code": (2, "stderr"), "codex": (2, "stderr"), "cursor": (0, "stdout"),
}
EXPLICIT_ALLOW = {"cursor"}   # must print JSON on every allow: empty output is a failure there


def _run(repo: Path, fmt: str, payload: dict, *extra: str) -> subprocess.CompletedProcess[str]:
    env = script_subprocess_env()
    env["SPECY_ROAD_AGENT_ID"] = "me"
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "session", "guard", "--format", fmt, *extra, "--repo-root", str(repo)],
        input=json.dumps(payload), capture_output=True, text=True, env=env, cwd=REPO, check=False,
    )


def test_every_adapter_has_a_documented_payload() -> None:
    assert set(ADAPTERS) == set(PAYLOADS)


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_deny_answers_the_way_the_harness_reads_it(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    r = _run(repo, fmt, PAYLOADS[fmt]("git reset --hard"))
    code, channel = DENY[fmt]
    assert r.returncode == code
    text = r.stdout if channel == "stdout" else r.stderr
    assert "refused in a shared checkout" in text and "live sessions: alice" in text
    if channel == "stdout":
        assert json.loads(r.stdout)["permission"] == "deny"


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_allow_exits_zero_and_speaks_only_when_the_harness_needs_it(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    r = _run(repo, fmt, PAYLOADS[fmt]("git add src/a.py && git commit -m x"))
    assert r.returncode == 0 and "session guard" not in r.stderr
    if fmt in EXPLICIT_ALLOW:
        assert json.loads(r.stdout) == {"permission": "allow"}
    else:
        assert r.stdout == ""


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_an_unjudgeable_payload_allows(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    for payload in ({}, {"tool_name": "Read", "tool_input": {"file_path": "x"}}):
        r = _run(repo, fmt, payload)
        assert r.returncode == 0, (fmt, payload, r.stderr)
        if fmt in EXPLICIT_ALLOW:
            assert json.loads(r.stdout) == {"permission": "allow"}


def test_cursor_allow_with_warning_carries_an_agent_message(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    r = _run(repo, "cursor", PAYLOADS["cursor"]("git stash"))
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["permission"] == "allow" and "would deny" in out["agent_message"]


def test_codex_allow_with_warning_stays_silent(tmp_path: Path) -> None:
    """Codex marks a hook failed on keys it does not support, so no note goes out."""
    repo = make_review_repo(tmp_path)
    r = _run(repo, "codex", PAYLOADS["codex"]("git stash"))
    assert r.returncode == 0 and r.stdout == ""


@pytest.mark.parametrize("fmt", ["claude-code", "codex", "cursor"])
def test_config_snippets_are_valid_json_naming_the_guard(tmp_path: Path, fmt: str) -> None:
    r = _run(tmp_path, fmt, {}, "--print-config")
    assert r.returncode == 0
    assert f"session guard --format {fmt}" in json.dumps(json.loads(r.stdout.split("\n# ", 1)[0]))


def test_claude_code_allow_with_warning_is_json_the_model_sees(tmp_path: Path) -> None:
    """Alone in the tree the call proceeds, with the warning as additionalContext."""
    repo = make_review_repo(tmp_path)
    r = _run(repo, "claude-code", PAYLOADS["claude-code"]("git stash"))
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "allow"
    assert "would deny" in out["additionalContext"]


def test_internal_errors_fail_closed(tmp_path: Path, monkeypatch, capsys) -> None:
    """Claude Code treats any exit code other than 0 and 2 as 'proceed'."""
    from specy_road.bundled_scripts import session_cli

    def boom(*_a, **_k):
        raise RuntimeError("sessions dir unreadable")

    monkeypatch.setattr(session_cli, "decide", boom)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(PAYLOADS["claude-code"]("ls"))))
    with pytest.raises(SystemExit) as e:
        session_cli.main(["session", "guard", "--format", "claude-code", "--repo-root", str(tmp_path)])
    assert e.value.code == 2
    assert "refusing rather than failing open" in capsys.readouterr().err


def test_internal_errors_fail_closed_for_cursor_too(tmp_path: Path, monkeypatch, capsys) -> None:
    from specy_road.bundled_scripts import session_cli

    monkeypatch.setattr(session_cli, "decide", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(PAYLOADS["cursor"]("ls"))))
    with pytest.raises(SystemExit) as e:
        session_cli.main(["session", "guard", "--format", "cursor", "--repo-root", str(tmp_path)])
    assert e.value.code == 0
    assert json.loads(capsys.readouterr().out)["permission"] == "deny"
