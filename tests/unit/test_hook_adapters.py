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
from tests.support.review import make_review_repo

from specy_road.orchestration.guard import session_presence as sp
from specy_road.orchestration.guard.tool_call_guard import ADAPTERS
from tests.support.extracted.hook_adapters import DENY, PAYLOADS, REPO, pre_tool_use, run
from specy_road.orchestration.guard import tool_call_guard_adapters as tga





EXPLICIT_ALLOW = {"cursor"}   # must print JSON on every allow: empty output is a failure there




def test_every_adapter_has_a_documented_payload() -> None:
    assert set(ADAPTERS) == set(PAYLOADS)


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_deny_answers_the_way_the_harness_reads_it(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    r = run(repo, fmt, PAYLOADS[fmt]("git reset --hard"))
    code, channel = DENY[fmt]
    assert r.returncode == code
    text = r.stdout if channel == "stdout" else r.stderr
    assert "refused in a shared checkout" in text and "live sessions: alice" in text
    if channel == "stdout":
        assert json.loads(r.stdout)["permission"] == "deny"
    if fmt == "claude-code":   # Cursor runs .claude/settings.json hooks as tool "Shell"
        r = run(repo, fmt, {**PAYLOADS[fmt]("git reset --hard"), "tool_name": "Shell"})
        assert r.returncode == 2 and "refused in a shared checkout" in r.stderr


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_allow_exits_zero_and_speaks_only_when_the_harness_needs_it(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    r = run(repo, fmt, PAYLOADS[fmt]("git add src/a.py && git commit --only src/a.py -m x"))
    assert r.returncode == 0 and "session guard" not in r.stderr
    if fmt in EXPLICIT_ALLOW:
        assert json.loads(r.stdout) == {"permission": "allow"}
    else:
        assert r.stdout == ""


@pytest.mark.parametrize("fmt", sorted(ADAPTERS))
def test_an_unjudgeable_payload_allows(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    for payload in ({}, {"tool_name": "Read", "tool_input": {"file_path": "x"}}):
        r = run(repo, fmt, payload)
        assert r.returncode == 0, (fmt, payload, r.stderr)
        if fmt in EXPLICIT_ALLOW:
            assert json.loads(r.stdout) == {"permission": "allow"}


def test_cursor_allow_with_warning_carries_an_agent_message(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    r = run(repo, "cursor", PAYLOADS["cursor"]("git stash"))
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["permission"] == "allow" and "would deny" in out["agent_message"]


def test_codex_allow_with_warning_stays_silent(tmp_path: Path) -> None:
    """Codex marks a hook failed on keys it does not support, so no note goes out."""
    repo = make_review_repo(tmp_path)
    r = run(repo, "codex", PAYLOADS["codex"]("git stash"))
    assert r.returncode == 0 and r.stdout == ""


@pytest.mark.parametrize("fmt", ["claude-code", "codex", "cursor"])
def test_config_snippets_are_valid_json_naming_the_guard(tmp_path: Path, fmt: str) -> None:
    r = run(tmp_path, fmt, {}, "--print-config")
    assert r.returncode == 0
    assert f"session guard --format {fmt}" in json.dumps(json.loads(r.stdout))
    assert r.stderr.startswith("# Put the snippet in ")


def test_claude_code_allow_with_warning_is_json_the_model_sees(tmp_path: Path) -> None:
    """Alone in the tree the call proceeds, with the warning as additionalContext and no permissionDecision.

    `permissionDecision: "allow"` would skip Claude Code's own permission prompt (review round 6, B14).
    """
    repo = make_review_repo(tmp_path)
    r = run(repo, "claude-code", PAYLOADS["claude-code"]("git stash"))
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and "permissionDecision" not in out
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



# --- Sol F4 ---------------------------------------------------------------------

def test_a_non_string_hook_command_is_an_error_not_an_allow() -> None:
    with pytest.raises(ValueError, match="not a string"):
        tga.ADAPTERS["cursor"].extract({"command": ["git", "stash"]})
    with pytest.raises(ValueError, match="not a string"):
        tga.ADAPTERS["claude-code"].extract({"tool_name": "Bash", "tool_input": {"command": {"x": 1}}})
    assert tga.ADAPTERS["cursor"].extract({"command": ""}) is None
