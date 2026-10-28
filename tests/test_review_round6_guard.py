"""Review round 6 (`9f3b9df`), guard items: B1, B14, B15, B16, B17, question 4, and two Gemini follow-ups.

Each test reproduces the report's shape first (the command the reviewer ran)
and pins the fail-closed answer. Adapter-level cases run the real
`specy-road session guard --format …` subprocess, as the harness would.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo
from tests.test_hook_adapters import DENY, PAYLOADS, _run

from specy_road import session_presence as sp
from specy_road import tool_call_guard as g
from specy_road.tool_call_guard_adapters import ADAPTERS

ENV_ALIAS = "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='!git stash' git x"


# --- B1: git config supplied through the environment --------------------------

@pytest.mark.parametrize("command", [
    ENV_ALIAS,
    "GIT_CONFIG_PARAMETERS=\"'alias.x=!git stash'\" git x",
    "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0=stash git x",
    "GIT_CONFIG=/tmp/c git x",
    "GIT_CONFIG_GLOBAL=/tmp/c git x",
    "GIT_CONFIG_SYSTEM=/tmp/c git x",
    "git --config-env=alias.x=BODY x",
    "git --config-env alias.x=BODY x",
    "sh -c 'GIT_CONFIG_GLOBAL=/tmp/c git x'",
])
def test_env_supplied_git_config_fails_closed(command: str) -> None:
    reason = g.classify(command)
    assert reason and "cannot see" in reason, (command, reason)


@pytest.mark.parametrize("command", [
    "GIT_TRACE=1 git log",
    "git --config-env=user.name=NAME log",
    "git commit -m 'GIT_CONFIG=x' src/a.py",       # the name inside an argument is not an assignment
    "GIT_CONFIG_GLOBAL=/tmp/c make test",            # no git in the segment
])
def test_env_config_check_leaves_ordinary_commands_alone(command: str) -> None:
    assert g.classify(command) is None, command


@pytest.mark.parametrize("fmt", ["claude-code", "codex", "cursor"])
def test_every_harness_form_denies_env_alias_with_a_live_peer(tmp_path: Path, fmt: str) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    r = _run(repo, fmt, PAYLOADS[fmt](ENV_ALIAS))
    code, channel = DENY[fmt]
    assert r.returncode == code, (fmt, r.stdout, r.stderr)
    text = r.stdout if channel == "stdout" else r.stderr
    assert "refused in a shared checkout" in text and "GIT_CONFIG" in text
    if channel == "stdout":
        assert json.loads(r.stdout)["permission"] == "deny"


# --- B15: process substitution and dynamic git verbs -------------------------

@pytest.mark.parametrize("command, fragment", [
    ("cat <(git stash)", "stash stack is shared"),
    ("cat >(git stash)", "stash stack is shared"),
    ("diff <(git log) <(git reset --hard)", "discards other sessions"),
    ("git $(printf stash)", "shell expansion"),
    ("git ${x:-stash}", "shell expansion"),
    ('git "$x"', "shell expansion"),
    ("git $x", "shell expansion"),
    ("git `printf stash`", "shell expansion"),
    ("cat <(git stash", "unbalanced"),
])
def test_dynamic_shell_forms_fail_closed(command: str, fragment: str) -> None:
    reason = g.classify(command)
    assert reason and fragment in reason, (command, reason)


def test_process_substitution_with_harmless_git_passes() -> None:
    assert g.classify("diff <(git log -3) <(git log -3 origin/main)") is None


# --- B16: valid JSON that is not a judgeable payload ---------------------------

@pytest.mark.parametrize("text", ["[]", '"x"', "3", "null", "true"])
def test_non_object_payload_raises(text: str) -> None:
    with pytest.raises(ValueError, match="not an object"):
        g.read_payload(text)


@pytest.mark.parametrize("fmt", ["claude-code", "codex", "cursor"])
@pytest.mark.parametrize("text", ["[]", '"x"', "3"])
def test_non_object_payload_denies_at_the_adapter(tmp_path: Path, fmt: str, text: str) -> None:
    from tests.helpers import script_subprocess_env
    import sys

    repo = make_review_repo(tmp_path)
    r = subprocess.run([sys.executable, "-m", "specy_road.cli", "session", "guard", "--format", fmt, "--repo-root", str(repo)],
                       input=text, capture_output=True, text=True, env=script_subprocess_env(), check=False)
    code, channel = DENY[fmt]
    assert r.returncode == code, (fmt, text, r.stdout, r.stderr)
    assert "internal error" in (r.stdout if channel == "stdout" else r.stderr)


@pytest.mark.parametrize("payload", [
    {"tool_name": "Bash", "tool_input": {}},
    {"tool_name": "Bash", "tool_input": {"command": None}},
    {"tool_name": "Bash", "tool_input": {"command": ["git", "stash"]}},
    {"tool_name": "Bash"},
])
def test_bash_event_without_a_string_command_is_an_error(payload: dict) -> None:
    for fmt in ("claude-code", "codex"):
        with pytest.raises(ValueError, match="not a string"):
            ADAPTERS[fmt].extract(payload)


def test_cursor_shell_event_without_a_command_is_an_error() -> None:
    with pytest.raises(ValueError, match="not a string"):
        ADAPTERS["cursor"].extract({"hook_event_name": "beforeShellExecution", "cwd": "/tmp"})
    with pytest.raises(ValueError, match="not a string"):
        ADAPTERS["cursor"].extract({"hook_event_name": "beforeShellExecution", "command": 3})


def test_unrelated_tool_events_are_still_ignored() -> None:
    for fmt in ("claude-code", "codex"):
        assert ADAPTERS[fmt].extract({"tool_name": "Read", "tool_input": {"file_path": "x"}}) is None
        assert ADAPTERS[fmt].extract({}) is None
    assert ADAPTERS["cursor"].extract({}) is None
    assert ADAPTERS["cursor"].extract({"hook_event_name": "beforeSubmitPrompt", "prompt": "hi"}) is None


# --- B14 / question 4: a non-denial must not widen the harness's permissions ----

def test_claude_code_non_denials_carry_no_permission_decision() -> None:
    plain = ADAPTERS["claude-code"].on_allow(None)
    assert plain == (None, None, 0)
    out, err, code = ADAPTERS["claude-code"].on_allow("(would deny with another live session: x)")
    assert code == 0 and err is None
    hso = json.loads(out)["hookSpecificOutput"]
    assert "permissionDecision" not in hso and hso["additionalContext"].startswith("(would deny")


def test_codex_non_denials_stay_silent() -> None:
    assert ADAPTERS["codex"].on_allow(None) == (None, None, 0)
    assert ADAPTERS["codex"].on_allow("note") == (None, None, 0)


def test_cursor_non_denial_is_an_explicit_allow_pending_ide_confirmation() -> None:
    """Cursor fails open on empty output, so the answer stays `allow`; runbook §3 confirms its effect in a real IDE."""
    assert json.loads(ADAPTERS["cursor"].on_allow(None)[0]) == {"permission": "allow"}
    assert "unverified" in ADAPTERS["cursor"].notes or "runbook" in ADAPTERS["cursor"].notes


# --- B17: broad commit / add pathspecs ----------------------------------------

@pytest.mark.parametrize("command", [
    "git commit --only . -m swept",
    "git commit --only ./ -m swept",
    "git commit --only :/ -m swept",
    "git commit --only ':(glob)**' -m swept",
    "git commit --only '*' -m x",
    "git commit --only 'src/*.py' -m x",
    "git commit --only .. -m x",
    "git commit --only ../other -m x",
    "git commit --only /abs/path/a.py -m x",
    "git commit -m x -- .",
    "git commit --only --pathspec-from-file=paths.txt -m x",
    "git add 'src/*.py'",
    "git add ..",
    "git add ':(top)src'",
    "git rm -r .",
])
def test_broad_pathspecs_are_refused(command: str) -> None:
    reason = g.classify(command)
    assert reason and "explicit repo-relative files" in reason, (command, reason)


@pytest.mark.parametrize("command", [
    "git commit --only src/a.py -m x",
    "git commit -m x src/a.py docs/b.md",
    "git commit --only src/ -m x",          # a plain directory is scoped: the caller vouches for it
    "git commit -m 'a * b' src/a.py",       # a glob inside -m is a message, not a pathspec
    "git add src/a.py",
    "git add src/",
    "git rm src/a.py",                      # refuses a file with uncommitted changes; stages a deletion like `git add`
])
def test_explicit_pathspecs_pass(command: str) -> None:
    assert g.classify(command) is None, command


# --- Gemini follow-ups: quoted eval, alias expansion vs tree scope -------------

@pytest.mark.parametrize("command, fragment", [
    ('eval "git stash"', "stash stack is shared"),
    ("eval 'git reset --hard'", "discards other sessions"),
    ("eval git stash", "stash stack is shared"),
    ("eval \"$(printf 'git stash')\"", "cannot see"),
    ("sudo eval 'git clean -f'", "deletes untracked files"),
])
def test_eval_is_judged_by_what_it_runs(command: str, fragment: str) -> None:
    reason = g.classify(command)
    assert reason and fragment in reason, (command, reason)


def test_eval_of_harmless_text_passes() -> None:
    assert g.classify('eval "echo hi"') is None
    assert g.classify("eval make test") is None


def test_repo_alias_naming_another_tree_counts_every_session(tmp_path: Path) -> None:
    """`alias.co = -C ../other checkout main` must not be scoped to the caller's worktree."""
    repo = make_review_repo(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    sp.start_session(repo, "alice", paths=["src"], worktree=other)
    assert g.decide(repo, "git checkout main", agent="me").allowed   # alice is in another tree
    subprocess.run(["git", "config", "alias.co", f"-C {other} checkout main"], cwd=repo, check=True)
    v = g.decide(repo, "git co", agent="me")
    assert not v.allowed and "live sessions: alice" in v.reason
