"""The shared-checkout command guard (design note decision 6) and its CLI."""

from __future__ import annotations

import io
import json
import os
import shlex
from pathlib import Path

import pytest

from tests.support.guard_cases import (
    DESTRUCTIVE,
    MORE_DESTRUCTIVE_SHAPES,
    MORE_WRAPPER_SHAPES,
    OPAQUE_REFUSED,
    OPAQUE_WITHOUT_GIT,
    ORDINARY,
    PATH_PREFIXES,
    WRAPPER_SPELLINGS,
)
from tests.support.review import make_review_repo

from specy_road.orchestration.guard import session_presence as sp
from specy_road.orchestration.guard import tool_call_guard as g
from specy_road.bundled_scripts import session_cli
from tests.support.review import git
from specy_road.orchestration.guard import tool_call_guard as tg
from specy_road.orchestration.workers import worker_process as wp
from specy_road.orchestration.workers import worker_state as ws


@pytest.mark.parametrize("command, fragment", DESTRUCTIVE)
def test_destructive_commands_are_classified(command: str, fragment: str) -> None:
    reason = g.classify(command)
    assert reason and fragment in reason, (command, reason)


@pytest.mark.parametrize("command", ORDINARY)
def test_ordinary_commands_pass(command: str) -> None:
    assert g.classify(command) is None, command


def test_unparseable_shell_mentioning_git_is_refused_not_waved_through() -> None:
    assert "could not parse" in (g.classify("git stash 'unterminated") or "")
    assert g.classify("echo 'unterminated") is None


def test_guard_sees_a_worker_running_in_this_checkout(tmp_path: Path, monkeypatch) -> None:
    from tests.support.review import make_review_repo

    from specy_road.orchestration.workers import worker_process as wp
    from specy_road.orchestration.workers import worker_state as ws

    repo = make_review_repo(tmp_path)
    # The guard matches the wrapper's resolved repo root as a whole argument (review round 6, B11).
    monkeypatch.setattr(wp, "cmdline", lambda pid: f"python -m specy_road.worker_runner {repo.resolve()} w-0001")
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


@pytest.mark.parametrize("text", ["", "agent: bob\nbranch: feature/x\n", "agent: [bob\n"])
def test_a_record_that_will_not_load_counts_as_a_live_session(tmp_path: Path, capsys, text: str) -> None:
    """Empty, cut short before its expiry, or broken YAML: the guard cannot rule the peer out, so it denies."""
    repo = make_review_repo(tmp_path)
    sp.start_session(repo, "bob", paths=["src"])
    sp.session_path(repo, "bob").write_text(text, encoding="utf-8")
    assert _cli("session", "guard", "--command", "git stash", "--agent", "me", "--repo-root", str(repo)) == 2
    assert "bob.yaml (unreadable; fix or delete it)" in capsys.readouterr().err


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



# --- B3, B6, F17 ----------------------------------------------------------------

# One test per finding: a completed worker still owns its leaf; lifecycle transitions are one
# transaction each; the guard refuses shell shapes it cannot follow and `git -C` into another
# tree, and denies a bare commit; an embedded placeholder is refused; the default session id is
# stable across processes and `touch` keeps the paths; a skipped skill is never adopted or
# overwritten; a stale worktree directory is refused; the GUI reports the v2 session and requires
# a reject reason; op ids bind their arguments; signing without a roster key is refused early; a
# foreign skill link is left alone; a dead wrapper frees the leaf; terminate refuses an
# unverifiable pid and does not signal an adopted session; READY binds to the branch; a profile
# path cannot escape the repo; `--harness` cannot override the roster; a plan with no coordinator
# says so; search results are delimited; the verifier's byte cap is a cap.

@pytest.mark.parametrize("command", OPAQUE_REFUSED)
def test_opaque_shapes_and_bare_commits_are_refused(command: str) -> None:
    assert tg.classify(command), command



@pytest.mark.parametrize("command", OPAQUE_WITHOUT_GIT)
def test_opaque_shapes_without_git_pass(command: str) -> None:
    assert tg.classify(command) is None



def test_git_dash_c_into_another_tree_counts_that_trees_session(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    assert tg.decide(repo, "git checkout -b feature/x", agent="bob").allowed       # alice is elsewhere
    assert not tg.decide(repo, f"git -C {wt} reset --hard", agent="bob").allowed   # but this reaches her



# --- Gemini F1 / Sol B1 -----------------------------------------------------------

# One test per finding: reconcile judges the worker's whole lifetime; READY must be at the
# worktree's HEAD; routing reads the roster from the integration branch; the guard follows env -S,
# nested $(), attached -C, --git-dir, long wrapper options, timeout, xargs-from-stdin and
# configured aliases, and refuses a non-string hook command; a dead wrapper fails on
# message/handoff; a skipped skill gets no link and a foreign directory is never removed; the
# nested AGENTS.md report carries its prefix; rounds are persisted; a malformed custom cli raises;
# event sequences survive a crash; adopt is atomic; hook prompts are verbatim; the verifier pins
# its address; round one hides the roadmap digest; an invalid profile is a staffing error; a
# mismatched slug is refused.

@pytest.mark.parametrize("command", MORE_WRAPPER_SHAPES)
def test_more_wrapper_shapes_are_classified(command: str) -> None:
    assert tg.classify(command), command



def test_attached_dash_c_git_dir_and_config_aliases_reach_the_right_tree(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    sp.start_session(repo, "alice", paths=["src"], worktree=wt)
    git(repo, "config", "alias.s", "stash")
    git(repo, "config", "alias.boom", "!git reset --hard")
    assert not tg.decide(repo, f"git -C{wt} reset --hard", agent="bob").allowed
    assert not tg.decide(repo, f"git --git-dir={wt}/.git commit -m x", agent="bob").allowed
    assert not tg.decide(repo, "git s", agent="bob").allowed
    assert "reset --hard" in (tg.classify(tg.expand_config_aliases(repo, "git boom")) or "")   # bang alias expanded
    assert not tg.decide(repo, "git boom", agent="bob", always=True).allowed
    assert tg.decide(repo, "git -C . status", agent="bob").allowed



# One test per finding: a prompt containing `<prompt>` cannot break out of the shell quoting; the
# session id chosen up front survives the spawn; a completed worker can take a review `block` as a
# message and a turn's READY is judged against that turn; a linked worktree gets the brief; the
# guard scopes tree-only commands to this worktree and sees `checkout -f`, `restore <path>`, brace
# groups, `eval` and `$(…)`; an op id is bound to its target; handoff refuses a closed worker;
# hook prompts are attributed by line, not by second; adopt refuses a duplicate; reconcile treats
# an unbuildable prompt as a contract change; Codex resume keeps its sandbox; reviews_root stays
# inside a nested project; the CGNAT range is off-host.

def test_tree_only_commands_ignore_sessions_in_other_worktrees(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    sp.start_session(repo, "alice", paths=["src"], worktree=repo)
    assert tg.decide(wt, "git checkout -b feature/rm-other", agent="bob").allowed
    assert not tg.decide(repo, "git checkout -b feature/rm-other", agent="bob").allowed
    assert not tg.decide(wt, "git stash", agent="bob").allowed          # the stash stack is repo-wide



def test_a_worker_does_not_count_itself(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    # The guard matches the wrapper's resolved repo root as a whole argument (review round 6, B11).
    monkeypatch.setattr(wp, "cmdline", lambda pid: f"python -m specy_road.worker_runner {repo.resolve()} w-0001")
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.set_state(repo, rec, "running", pid=os.getpid())
    assert not tg.decide(repo, "git checkout dev", agent="me").allowed
    monkeypatch.setenv("SPECY_ROAD_WORKER_ID", "w-0001")
    assert tg.decide(repo, "git checkout dev", agent="me").allowed
    monkeypatch.delenv("SPECY_ROAD_WORKER_ID")
    ws.set_state(repo, rec, "running", pid=999999)              # a dead pid is not a live worker
    assert tg.decide(repo, "git checkout dev", agent="me").allowed



@pytest.mark.parametrize("command", MORE_DESTRUCTIVE_SHAPES)
def test_more_destructive_shapes_are_classified(command: str) -> None:
    assert tg.classify(command), command



def test_staged_restore_of_a_path_is_fine() -> None:
    assert tg.classify("git restore --staged src/a.py") is None



def test_malformed_hook_stdin_denies() -> None:
    with pytest.raises(ValueError):
        tg.read_payload("not json")


# Long options of GNU coreutils 9.4 env. A prefix of split-string that matches one name is unambiguous.
ENV_LONG_NAMES = (
    "ignore-environment", "null", "unset", "chdir", "split-string", "block-signal",
    "default-signal", "ignore-signal", "list-signal-handling", "debug", "help", "version",
)


def param_rows(fn: object) -> list:
    marks = getattr(fn, "pytestmark", [])
    if not isinstance(marks, list):
        marks = [marks]
    rows: list = []
    for mark in marks:
        if mark.name == "parametrize":
            rows.extend(mark.args[1])
    return rows


def command_text(row: object) -> str:
    return row[0] if isinstance(row, tuple) else str(row)


def see_through_forms(command: str) -> list[str]:
    """Opener, brace group, ``if``, subshell, assignment prefix, and sudo."""
    return [
        f"! {command}",
        "{ " + command + "; }",
        f"if true; then {command}; fi",
        f"({command})",
        f"FOO=1 {command}",
        f"sudo {command}",
    ]


def split_string_prefixes() -> list[str]:
    target = "split-string"
    return [
        target[:length] for length in range(1, len(target) + 1)
        if sum(name.startswith(target[:length]) for name in ENV_LONG_NAMES) == 1
    ]


def env_split_forms(command: str) -> list[str]:
    """``-S`` separate, clustered, attached, and every unambiguous ``--split-string`` prefix.

    A ``GIT_CONFIG*`` command is also run as ``env -S '-i <row>'`` (and ``-v``, ``--``,
    ``-u HOME``, with and without ``sudo``). An option in front of other rows is a
    different class: the split is re-tokenized, so shell syntax such as ``if`` does
    not keep its bare reason.
    """
    quoted = shlex.quote(command)
    forms = [f"env -S {quoted}", f"env -vS {quoted}", f"env -S{quoted}", f"env -vS{quoted}"]
    for prefix in split_string_prefixes():
        forms.append(f"env --{prefix} {quoted}")
        forms.append(f"env --{prefix}={quoted}")
    if "GIT_CONFIG" in command:
        for opt in ("-i ", "-v ", "-- ", "-u HOME "):
            inner = shlex.quote(opt + command)
            forms.append(f"env -S {inner}")
            forms.append(f"sudo env -S {inner}")
    return forms


# ``timeout``'s first positional is a duration, so the guarded command stays the next word.
_PATH_WRAPPERS = (
    ("command", ""),
    ("env", ""),
    ("sudo", ""),
    ("nohup", ""),
    ("exec", ""),
    ("time", ""),
    ("nice", ""),
    ("xargs", ""),
    ("timeout", "10 "),
    ("doas", ""),
    ("ionice", ""),
)


def path_qualified_forms(command: str) -> list[str]:
    """``/usr/bin/<w>``, ``/bin/<w>`` and ``./<w>`` around ``command`` for each wrapper."""
    return [
        f"{prefix}{name} {gap}{command}"
        for name, gap in _PATH_WRAPPERS
        for prefix in PATH_PREFIXES
    ]


def path_qualified_env_forms(command: str) -> list[str]:
    """Each split-string spelling with a path-qualified ``env`` or ``sudo``, and a subshell around ``env``."""
    forms = []
    for form in env_split_forms(command):
        for prefix in PATH_PREFIXES:
            spelled = f"{prefix}{form}"
            forms.append(spelled)
            if form.startswith("env"):
                forms.append(f"({spelled})")
    return forms


def wrapper_option_forms(command: str) -> list[str]:
    """Each wrapper option, with a value where it takes one, bare and path-qualified."""
    forms = []
    for name, gap, spellings in WRAPPER_SPELLINGS:
        for spelling in spellings:
            body = f"{name} {spelling} {gap}{command}"
            forms.append(body)
            for prefix in PATH_PREFIXES:
                forms.append(f"{prefix}{body}")
    return forms


def assert_named_option_forms() -> None:
    """The commands this leaf names keep the bare command's reason."""
    for wrapped, bare_command in named_option_forms():
        assert g.classify(wrapped) == g.classify(bare_command), (wrapped, g.classify(wrapped))


def named_option_forms() -> list[tuple[str, str]]:
    """Commands named for this leaf, each beside the bare command it must match."""
    stash = "git stash"
    return [
        ("sudo -n git stash", stash),
        ("command -p git stash", stash),
        ("time -p git stash", stash),
        ("doas -n git stash", stash),
        ("xargs -r git stash", stash),
        ("xargs -t git stash", stash),
        ("ionice -t git stash", stash),
        ("/usr/bin/sudo -n git reset --hard", "git reset --hard"),
        ("( sudo -n git stash )", stash),
        ("sudo -nu bob git stash", stash),
        ("sudo -ubob git stash", stash),
        ("sudo --user=bob git stash", stash),
        ("sudo -- git stash", stash),
        ("sudo -n -- git stash", stash),
        ("command -- git stash", stash),
        ("timeout -- 10 git stash", stash),
        ("xargs -- git stash", stash),
    ]


def destructive_commands() -> list[str]:
    tables = (
        test_destructive_commands_are_classified,
        test_opaque_shapes_and_bare_commits_are_refused,
        test_more_wrapper_shapes_are_classified,
        test_more_destructive_shapes_are_classified,
    )
    return [command_text(row) for table in tables for row in param_rows(table)]


def test_env_split_escapes_and_pre_leaf_refusals() -> None:
    """GNU ``-S`` escapes, and every pre-leaf ``env -S`` refusal, stay refused or match.

    ``\\_`` and an embedded tab, newline, form feed, vertical tab or carriage return read
    as ``git stash``. ``\\c`` ends the string and a leading ``#`` comments it out, so what
    remains is classified. An unknown escape is refused. Forms the pre-leaf guard
    refused are still refused.
    """
    stash = g.classify("git stash")
    same = (
        "env -S 'git\\_stash'", "env -vS 'git\\_stash'", "env -S'git\\_stash'",
        "env --split 'git\\_stash'", "env --s 'git\\_stash'", "env --spl='git\\_stash'",
        "env -S 'git\\tstash'", "env -S 'git\\nstash'", "env -S 'git\\fstash'",
        "env -S 'git\\vstash'", "env -S 'git\\rstash'", "env -S 'git\tstash'",
        "env -S 'git stash\\c --hard'",
    )
    for command in same:
        assert g.classify(command) == stash, (command, g.classify(command))
    literal = (
        "env -S \"git'\\_stash'\"", "env -S '\"git\\_stash\"'", "env -S 'git\\\\_stash'",
        "env -S 'gi\\ct stash'", "env -S '# git stash'",
    )
    for command in literal:
        assert g.classify(command) is None, (command, g.classify(command))
    unknown = (
        "env -S 'git\\x20stash'", "env -S '\\gitstash'",
        "env -S -S '${CMD} stash'", "env -S --split '${CMD} stash'",
        "env --split -S '${CMD} stash'", "env -vS -S '${DIR}'",
        "env -S -S 'git\\x20stash'", "sudo env -S -S '${CMD} stash'",
        "(env -S -S 'git\\x20stash')", "env -S -S -S '${CMD} stash'",
        "env -i -S -S '${CMD} stash'",
    )
    for command in unknown:
        reason = g.classify(command)
        assert reason and "cannot see" in reason, (command, reason)
    refused_before = (
        'env -S "git stash"', '(env -S "git stash")', 'sudo env -S "git stash"',
        'FOO=1 env -S "git stash"', 'env -vS "git stash"', 'env -iS "git stash"',
        'env -S"git stash"', 'env -vS"git stash"', '(env -vS "git stash")',
        'sudo env -iS "git stash"', 'FOO=1 env -S"git stash"', 'FOO=1 env -vS"git stash"',
        "env -S 'git\\_stash'", "env -S 'git\\x20stash'", "env -S 'git\\tstash'",
        "env -S 'git\\nstash'",
    )
    for command in refused_before:
        assert g.classify(command), command


def test_wrappers_keep_the_bare_verdict_and_reason() -> None:
    """Every wrapper, including each env split-string spelling, keeps the bare reason.

    ``-S`` separate, clustered and attached, and every unambiguous prefix of ``--split-string``
    (with ``=`` and with a separate value) match the bare command. A path-qualified wrapper
    (``/usr/bin/<w>``, ``/bin/<w>``, ``./<w>``) matches that same bare reason, including
    ``/usr/bin/env -S``, a subshell around it, ``/bin/env --split=`` and ``/usr/bin/sudo``.
    Each wrapper's own options, with a value where one is required, do too, bare and
    path-qualified: ``sudo -n``, ``command -p``, ``time -p``, ``doas -n``, ``xargs -r``,
    ``xargs -t``, ``ionice -t``. Short options cluster and take an attached or separate
    value, and ``--`` ends that wrapper's options.
    A ``GIT_CONFIG*`` row also matches through ``env -S '-i <row>'`` and the same option
    with ``-v``, ``--``, ``-u HOME``, and ``sudo``. Ordinary commands stay allowed through
    those forms. A split string whose command needs runtime state (``$HOME``, ``${DIR}``,
    or an unknown escape) is refused as opaque.
    """
    stash = g.classify("git stash")
    examples = (
        'env --split "git stash"', 'env --s "git stash"',
        'env --split="git stash"', 'env --spl="git stash"',
        '/usr/bin/env -S "git stash"', '(/usr/bin/env -S "git stash")',
        '/bin/env --split="git stash"', '/usr/bin/sudo env -S "git stash"',
    )
    for example in examples:
        assert g.classify(example) == stash, (example, g.classify(example))
    assert_named_option_forms()
    for command in destructive_commands():
        bare = g.classify(command)
        assert bare, command
        wrapped_forms = (
            *see_through_forms(command),
            *env_split_forms(command),
            *path_qualified_forms(command),
            *path_qualified_env_forms(command),
            *wrapper_option_forms(command),
        )
        for wrapped in wrapped_forms:
            assert g.classify(wrapped) == bare, (wrapped, g.classify(wrapped), bare)
    needs_runtime = (
        "echo $HOME",
        "ls ${DIR}",
        "$HOME/bin/pytest -q",
        "${PYTHON:-python} -m pytest",
    )
    ordinary = [command_text(row) for row in param_rows(test_ordinary_commands_pass)]
    for command in ordinary:
        assert g.classify(command) is None, command
        for wrapped in (
            *see_through_forms(command), *path_qualified_forms(command), *wrapper_option_forms(command),
        ):
            assert g.classify(wrapped) is None, (wrapped, g.classify(wrapped))
        if command in needs_runtime:
            continue
        for wrapped in (*env_split_forms(command), *path_qualified_env_forms(command)):
            assert g.classify(wrapped) is None, (wrapped, g.classify(wrapped))
    for command in needs_runtime:
        for wrapped in (*env_split_forms(command), *path_qualified_env_forms(command)):
            reason = g.classify(wrapped)
            assert reason and "cannot see" in reason, (wrapped, reason)


def test_unlisted_wrapper_option_is_opaque() -> None:
    """An option a wrapper does not list, before a word that could be git, is never allowed."""
    hidden = (
        "sudo --not-a-sudo-option git stash",
        "sudo -Q git stash",
        "command -x git stash",
        "doas -Q git stash",
        "nohup -x git stash",
        "exec -x git stash",
        "time --not-time git stash",
        "nice --not-nice git stash",
        "ionice -Q git stash",
        "xargs -Q git stash",
        "timeout --not-timeout 10 git stash",
        "env --not-an-env-option git stash",
        "/usr/bin/sudo -Q git reset --hard",
        "( sudo -Q git stash )",
        "sudo -n --not-a-sudo-option git stash",
        "sudo -Q $X",
    )
    for command in hidden:
        reason = g.classify(command)
        assert reason and "does not list" in reason, (command, reason)
    for command in ("sudo --not-a-sudo-option ls /tmp", "command -x echo hi", "nice --not-nice ls"):
        assert g.classify(command) is None, (command, g.classify(command))


def test_split_string_options_are_parsed_before_the_command() -> None:
    """An option inside ``-S`` consumes its value, so that word is not the command.

    A ``NAME=VALUE`` word after that option stays in the command, so ``GIT_CONFIG*``
    keeps the env-config refusal, directly and inside the split string.
    """
    stash = g.classify("git stash")
    consumed = (
        "env -S '--unset git stash'", "env -S '--chdir git stash'", "env -S '-u git stash'",
        "env -S '--un git stash'", "env -S '--ch git stash'", "env -S '-C git status'",
        "sudo env -S '--unset git stash'", "(env -S '--chdir git stash')",
        "FOO=1 env -S '-u git stash'", "env --split '--unset git stash'",
        "env -S --unset git stash",
    )
    for command in consumed:
        assert g.classify(command) is None, (command, g.classify(command))
    runs = (
        "env -S '-u HOME git stash'", "env -S '--unset=HOME git stash'",
        "env -S '--debug git stash'", "env -S '--default-signal git stash'",
        "env -S '-- git stash'", "env -S '--ch /tmp git stash'",
        "env -S '-uHOME git stash'", "env -S 'FOO=1 git stash'",
    )
    for command in runs:
        assert g.classify(command) == stash, (command, g.classify(command))
    config = g.classify("GIT_CONFIG_GLOBAL=/tmp/c git x")
    held = (
        "env -i GIT_CONFIG_GLOBAL=/tmp/c git x",
        "env -v GIT_CONFIG_PARAMETERS=x git status",
        "env -- GIT_CONFIG_GLOBAL=/tmp/c git x",
        "env -u HOME GIT_CONFIG_GLOBAL=/tmp/c git x",
        "env --unset=HOME GIT_CONFIG_PARAMETERS=x git status",
        "env -C /tmp GIT_CONFIG_GLOBAL=/tmp/c git x",
        "env -iv GIT_CONFIG_GLOBAL=/tmp/c git x",
        "env --ignore-environment GIT_CONFIG_PARAMETERS=x git status",
        "env -S '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
        'env -S "-i GIT_CONFIG_GLOBAL=/tmp/c git x"',
        "env -S '-v GIT_CONFIG_PARAMETERS=x git status'",
        "env -S '-- GIT_CONFIG_GLOBAL=/tmp/c git x'",
        "env -S '-u HOME GIT_CONFIG_GLOBAL=/tmp/c git x'",
        "env -S '--unset=HOME GIT_CONFIG_PARAMETERS=x git status'",
        "env -S '-C /tmp GIT_CONFIG_GLOBAL=/tmp/c git x'",
        "env -S '-iv GIT_CONFIG_GLOBAL=/tmp/c git x'",
        "env -S '--ignore-environment GIT_CONFIG_GLOBAL=/tmp/c git x'",
        "env -vS '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
        'env --split-string="-i GIT_CONFIG_GLOBAL=/tmp/c git x"',
        "sudo env -S '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
        "(env -S '-C /tmp GIT_CONFIG_PARAMETERS=x git status')",
        "env -S -S '-i GIT_CONFIG_GLOBAL=/tmp/c git x'",
    )
    for command in held:
        assert g.classify(command) == config, (command, g.classify(command))
