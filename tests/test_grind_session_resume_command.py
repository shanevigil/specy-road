"""The resumed command must be the operator's command, not a rebuild of it.

``shlex.split`` + ``shlex.quote`` round-trips text rather than shell syntax, so
the invocation ``docs/grind-session.md`` recommends came back with its command
substitution single-quoted and inert. The first attempt was always fine, so
only a genuine resume after a real usage limit was affected -- and then Claude
silently received the literal string ``$(cat $SPECY_ROAD_PROMPT)`` as its task.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

import specy_road.bundled_scripts.grind_session_implement as gsi
from tests.test_grind_session_implement import (  # noqa: F401 - autouse fixture
    LIMIT,
    SESSION,
    _empty_claude_home,
    _limit_text,
)

#: The invocation the docs recommend -- the one the round-trip destroyed.
CLAUDE_SUBST = (
    'claude -p --permission-mode acceptEdits "$(cat "$SPECY_ROAD_PROMPT")"'
)


def test_the_splice_keeps_a_command_substitution_intact() -> None:
    resumed = gsi._resume_command(CLAUDE_SUBST, SESSION)
    assert resumed == (
        f"claude --resume {SESSION} -p --permission-mode acceptEdits "
        '"$(cat "$SPECY_ROAD_PROMPT")"'
    )
    # The specific corruption: the substitution wrapped in single quotes.
    assert "'$(cat" not in resumed


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("claude", "claude --resume ID"),
        ("claude -p x", "claude --resume ID -p x"),
        ("  claude -p x", "  claude --resume ID -p x"),
        ("/opt/homebrew/bin/claude -p x", "/opt/homebrew/bin/claude --resume ID -p x"),
        ('"/opt/my tools/claude" -p x', '"/opt/my tools/claude" --resume ID -p x'),
        ("claude -p `cat f`", "claude --resume ID -p `cat f`"),
        ("claude -p 'go' && echo done", "claude --resume ID -p 'go' && echo done"),
    ],
)
def test_the_splice_handles_odd_executables(command: str, expected: str) -> None:
    assert gsi._resume_command(command, "ID") == expected


def test_the_resume_flag_precedes_the_users_own_flags() -> None:
    """Pins the position asserted by the existing loop-level resume test."""
    resumed = gsi._resume_command(CLAUDE_SUBST, SESSION)
    assert resumed.index("--resume") < resumed.index("-p")


def test_the_resumed_command_really_expands_the_prompt_file(
    tmp_path: Path, monkeypatch
) -> None:
    """End-to-end through the real runner, with a fake `claude` on disk.

    This is what the existing fixture cannot catch: it takes an actual shell
    to show that the resumed attempt reads the file rather than passing its
    own source text along.
    """
    prompt = tmp_path / "prompt.md"
    prompt.write_text("IMPLEMENT M9.9 EXACTLY\n", encoding="utf-8")
    args_log = tmp_path / "args.log"
    stamp = tmp_path / "stamp"
    limit_msg = tmp_path / "limit.txt"
    limit_msg.write_text(_limit_text(), encoding="utf-8")

    fake = tmp_path / "bin" / "claude"
    fake.parent.mkdir()
    fake.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" >> "$ARGS_LOG"\n'
        'if [ -f "$STAMP" ]; then exit 0; fi\n'
        ': > "$STAMP"\n'
        'cat "$LIMIT_MSG"\n'
        "exit 1\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    monkeypatch.setattr(gsi, "_notify", lambda *_a, **_k: None)
    env = {
        "PATH": os.environ["PATH"],
        "SPECY_ROAD_PROMPT": str(prompt),
        "ARGS_LOG": str(args_log),
        "STAMP": str(stamp),
        "LIMIT_MSG": str(limit_msg),
    }
    command = f'{fake} -p "$(cat "$SPECY_ROAD_PROMPT")"'
    assert gsi.is_claude_cli(command)

    code = gsi.run_implement_hook(
        command, env, tmp_path, sleep=lambda _s: None, node_id="M9.9"
    )
    assert code == 0

    log = args_log.read_text(encoding="utf-8")
    # Both the first attempt and the resume got the file's contents ...
    assert log.count("IMPLEMENT M9.9 EXACTLY") == 2
    # ... and neither got the shell source as a literal argument.
    assert "$(cat" not in log
    assert "$SPECY_ROAD_PROMPT" not in log
    assert "--resume" in log
