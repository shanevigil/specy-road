"""The shared-checkout command guard (design note decision 6) and its CLI."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road import session_presence as sp
from specy_road import tool_call_guard as g
from specy_road.bundled_scripts import session_cli


@pytest.mark.parametrize("command, fragment", [
    ("git stash", "stash stack is shared"),
    ("git stash push -u -m x", "stash stack is shared"),
    ("git reset --hard HEAD~1", "discards other sessions"),
    ("git checkout main", "switching branches"),
    ("git checkout -b feature/x", "switching branches"),
    ("git switch dev", "switching branches"),
    ("git checkout -- .", "discards working-tree changes"),
    ("git checkout -- src/a.py", "discards working-tree changes"),
    ("git restore .", "discards other sessions"),
    ("git restore --staged .", "discards other sessions"),
    ("git clean -fd", "deletes untracked files"),
    ("git clean --force", "deletes untracked files"),
    ("git rebase -i HEAD~3", "rewrites history"),
    ("git commit --amend --no-edit", "rewrites a commit"),
    ("git commit -a -m x", "sweeps every session"),
    ("git commit -am x", "sweeps every session"),
    ("git commit --all -m x", "sweeps every session"),
    ("git add -A", "stages other sessions"),
    ("git add .", "stages other sessions"),
    ("git add -u", "stages other sessions"),
    ("git add --all", "stages other sessions"),
    ("git push --force origin main", "rewrites the remote"),
    ("git push -f", "rewrites the remote"),
    ("git push --force-with-lease", "rewrites the remote"),
    ("git push origin +main", "rewrites the remote"),
    ("make test && git stash", "stash stack is shared"),
    ("cd x; git reset --hard", "discards other sessions"),
    ("git -C /tmp/repo checkout main", "switching branches"),
    ("GIT_DIR=.git git rebase main", "rewrites history"),
    ("echo x\ngit stash", "stash stack is shared"),
    ("git reset --hard  # don't", "discards other sessions"),
    ('git commit -m "a; b" -a', "sweeps every session"),
    ("sh -c 'git stash'", "stash stack is shared"),
    ("bash -lc 'cd x && git rebase main'", "rewrites history"),
    ("(git stash)", "stash stack is shared"),
    ("make test & git stash", "stash stack is shared"),
    ("/usr/bin/git stash", "stash stack is shared"),
    ("command git stash", "stash stack is shared"),
    ("env GIT_TRACE=1 git stash", "stash stack is shared"),
    ("sudo -u bob git clean -f", "deletes untracked files"),
    ("git -c alias.s=stash s", "stash stack is shared"),
    ("git -c alias.rh='reset --hard' rh", "discards other sessions"),
    ("git -c alias.x='!git stash' x", "stash stack is shared"),
    ("git commit -m 'x'", "commits whatever another session staged"),
    ("git commit -m 'a; b' --no-verify", "commits whatever another session staged"),
    ("git -c alias.x='!cd /tmp && git reset --hard' x", "discards other sessions"),
])
def test_destructive_commands_are_classified(command: str, fragment: str) -> None:
    reason = g.classify(command)
    assert reason and fragment in reason, (command, reason)


@pytest.mark.parametrize("command", [
    "git add src/a.py docs/x.md",
    "git commit -m 'x' src/a.py",
    "git commit --only src/a.py -m x",
    "git push origin feature/rm-thing",
    "git worktree add ../wt -b feature/x main",
    "git status --porcelain",
    "git diff --cached",
    "git log --oneline -3",
    "git fetch origin",
    "git merge --no-ff feature/x",
    "git restore --staged src/a.py",
    "git reset src/a.py",
    "git checkout",
    "git add -p src/a.py",
    "make test && python -m pytest",
    "echo 'git stash' > notes.txt",
    "gitk",
])
def test_ordinary_commands_pass(command: str) -> None:
    assert g.classify(command) is None, command


def test_unparseable_shell_mentioning_git_is_refused_not_waved_through() -> None:
    assert "could not parse" in (g.classify("git stash 'unterminated") or "")
    assert g.classify("echo 'unterminated") is None


def test_guard_sees_a_worker_running_in_this_checkout(tmp_path: Path, monkeypatch) -> None:
    from tests.review_repo_helpers import make_review_repo

    from specy_road import worker_process as wp
    from specy_road import worker_state as ws

    repo = make_review_repo(tmp_path)
    # The guard matches the wrapper's resolved repo root as a whole argument (review round 6, B11).
    monkeypatch.setattr(wp, "_cmdline", lambda pid: f"python -m specy_road.worker_runner {repo.resolve()} w-0001")
    assert g.decide(repo, "git checkout dev", agent="me").allowed
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=os.getpid())
    v = g.decide(repo, "git checkout dev", agent="me")
    assert not v.allowed and "worker w-0001" in v.reason
    ws.set_state(repo, rec, "idle", pid=None)
    assert g.decide(repo, "git checkout dev", agent="me").allowed


def test_deny_only_with_another_live_session(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    alone = g.decide(repo, "git stash", agent="me")
    assert alone.allowed and "would deny" in alone.reason
    sp.start_session(repo, "alice", paths=["src"])
    shared = g.decide(repo, "git stash", agent="me")
    assert not shared.allowed and "live sessions: alice" in shared.reason
    assert g.decide(repo, "git stash", agent="alice").allowed   # alice is alone
    assert g.decide(repo, "git add src/a.py", agent="me").allowed


def test_always_denies_without_company(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    v = g.decide(repo, "git push --force", agent="me", always=True)
    assert not v.allowed and "--always" in v.reason


def _cli(*args: str, stdin: str = "") -> int:
    import sys
    old = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with pytest.raises(SystemExit) as e:
            session_cli.main(list(args))
    finally:
        sys.stdin = old
    return e.value.code or 0


def test_cli_command_mode_exit_codes(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    assert _cli("session", "guard", "--command", "git stash", "--agent", "me", "--repo-root", str(repo)) == 0
    assert "would deny" in capsys.readouterr().err
    sp.start_session(repo, "alice", paths=["src"])
    assert _cli("session", "guard", "--command", "git stash", "--agent", "me", "--repo-root", str(repo)) == 2
    assert "refused in a shared checkout" in capsys.readouterr().err
    assert _cli("session", "guard", "--command", "git add src/a.py", "--agent", "me", "--repo-root", str(repo)) == 0


def test_cli_claude_code_payload(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    bash = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}, "session_id": "s"})
    assert _cli("session", "guard", "--format", "claude-code", "--agent", "me", "--repo-root", str(repo), stdin=bash) == 2
    assert "discards other sessions" in capsys.readouterr().err
    other = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}})
    assert _cli("session", "guard", "--format", "claude-code", "--agent", "me", "--repo-root", str(repo), stdin=other) == 0
    # Malformed stdin is an internal error, and an internal error denies.
    assert _cli("session", "guard", "--format", "claude-code", "--repo-root", str(repo), stdin="not json") == 2
    assert "internal error" in capsys.readouterr().err


def test_cli_generic_payload(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "alice", paths=["src"])
    assert _cli("session", "guard", "--agent", "me", "--repo-root", str(repo), stdin='{"command": "git rebase main"}') == 2
    assert _cli("session", "guard", "--agent", "me", "--repo-root", str(repo), stdin='{"command": "git log"}') == 0
