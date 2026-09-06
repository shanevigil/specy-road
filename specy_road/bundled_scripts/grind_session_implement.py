"""The implement step: run the hook, and survive a Claude timed session limit.

Generic hooks are unchanged — one run, and a non-zero exit stops the session.
The exception is a hook that *is* the Claude CLI, which can return non-zero
simply because the account's session limit was reached. That is not a failed
implementation, and an unattended overnight grind should not end on it: wait for
the stated reset, resume the same Claude session, and carry on.

Everything vendor-specific lives in :mod:`specy_road.claude_code_limits`. What
this module owns is the policy — wait only for a limit that says when it lifts,
cap the resumes, and stop loudly rather than guess.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from specy_road.claude_code_limits import (
    SPEND,
    TIMED,
    UNRECOGNIZED,
    classify_limit,
    unrecognized_message,
)

#: Slack after the stated reset, because clocks disagree by a little.
GRACE_SECONDS = 120

#: How many times one leaf may wait out a limit before we call it stuck.
MAX_RESUMES = 3

#: Longest single wait. A reset further out than this is a person's call.
MAX_WAIT_SECONDS = 6 * 60 * 60


def is_claude_cli(implement_cmd: str) -> bool:
    """Whether this hook is the Claude CLI, and so can be waited out.

    Deliberately narrow: the first token's basename must be ``claude``. A
    wrapper script, Cursor's agent, or anything else keeps the generic path,
    because we have no idea what their exit codes mean.
    """
    try:
        parts = shlex.split(implement_cmd)
    except ValueError:
        return False
    return bool(parts) and os.path.basename(parts[0].strip()) == "claude"


def _run_capturing(cmd: str, env: dict, repo_root: Path) -> tuple[int, str]:
    """Run the hook, echo its output to stderr, and keep a copy to classify.

    stderr, never stdout: in ``--json`` mode stdout is the event stream, and the
    whole point of capturing is that we have to read what Claude said.
    """
    proc = subprocess.run(
        cmd, shell=True, cwd=repo_root, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    output = proc.stdout or ""
    if output:
        sys.stderr.write(output)
        sys.stderr.flush()
    return proc.returncode, output


def _resume_command(implement_cmd: str, session_id: str) -> str:
    """The same command again, continuing the session Claude already opened.

    The user's own flags are kept verbatim, permission mode included. We add
    ``--resume``; we never add ``--dangerously-skip-permissions``.
    """
    parts = shlex.split(implement_cmd)
    return " ".join(
        [shlex.quote(parts[0]), "--resume", shlex.quote(session_id)]
        + [shlex.quote(p) for p in parts[1:]]
    )


def seconds_until(reset_at: datetime, *, now: datetime | None = None) -> float:
    """Seconds to wait for ``reset_at``, plus grace. Never negative."""
    current = now or datetime.now(timezone.utc)
    return max(0.0, (reset_at - current).total_seconds() + GRACE_SECONDS)


def latest_session_id(repo_root: Path) -> str | None:
    """Newest Claude transcript for this repo, when Claude printed no id.

    Claude Code stores transcripts per project under ``~/.claude/projects``, in a
    directory named for the project path with separators replaced. Matching on
    the repo root beats trusting whichever session was globally most recent.
    """
    root = Path.home() / ".claude" / "projects"
    if not root.is_dir():
        return None
    wanted = str(repo_root).replace("/", "-")
    dirs = [
        d for d in root.iterdir()
        if d.is_dir() and d.name.strip("-") == wanted.strip("-")
    ]
    transcripts = [t for d in dirs for t in d.glob("*.jsonl")]
    if not transcripts:
        return None
    return max(transcripts, key=lambda p: p.stat().st_mtime).stem or None


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _notify(title: str, message: str) -> None:
    """Best-effort macOS banner. A missing osascript is not an error."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f"display notification {message!r} with title {title!r}"],
            capture_output=True, check=False, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _limit_refusal(verdict, node_id: str) -> int | None:
    """The stop-now cases, each said out loud. None means "keep going"."""
    if verdict.kind == UNRECOGNIZED:
        return _fail(unrecognized_message(verdict))
    if verdict.kind == SPEND:
        return _fail(
            "grind-session: the implement command hit a spend limit, which has "
            "no reset time to wait for. Add credits, then re-run.\n"
            f"  saw: {verdict.evidence}"
        )
    return None


def run_implement_hook(
    implement_cmd: str,
    env: dict,
    repo_root: Path,
    *,
    emitter=None,
    node_id: str = "",
    run_shell=None,
    sleep=None,
) -> int:
    """Run the implement hook, waiting out Claude's timed limits if it is Claude.

    ``run_shell`` is the generic runner every non-Claude hook keeps using, so
    that path retains its inherited streams and its exact current behaviour.
    """
    if not is_claude_cli(implement_cmd):
        return run_shell(implement_cmd, env, repo_root)

    # Resolved here, not as a default argument: a default binds at import and
    # would ignore anyone who patches the module's clock.
    wait = sleep if sleep is not None else time.sleep
    command = implement_cmd
    for attempt in range(MAX_RESUMES + 1):
        code, output = _run_capturing(command, env, repo_root)
        if code == 0:
            return 0
        verdict = classify_limit(output)
        refusal = _limit_refusal(verdict, node_id)
        if refusal is not None:
            return refusal
        if not verdict.is_waitable:
            return code  # an ordinary failure; the loop reports it as always
        if attempt >= MAX_RESUMES:
            return _fail(
                f"grind-session: still rate-limited after {MAX_RESUMES} waits; "
                "stopping rather than looping. Re-run when the quota recovers."
            )
        session_id = verdict.session_id or latest_session_id(repo_root)
        if not session_id:
            return _fail(
                "grind-session: hit a timed Claude session limit but could not "
                "find the session id to resume, so the work so far would be "
                "abandoned. Claude Code's output format may have changed.\n"
                f"  saw: {verdict.evidence}"
            )
        delay = seconds_until(verdict.reset_at)
        if delay > MAX_WAIT_SECONDS:
            return _fail(
                f"grind-session: the stated reset is {delay / 3600:.1f} hours "
                f"away, beyond the {MAX_WAIT_SECONDS // 3600}h this loop waits "
                "unattended. Re-run after it lifts."
            )
        if emitter is not None:
            emitter.emit(
                "usage_limited",
                node_id=node_id,
                reset_at=verdict.reset_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                wait_seconds=int(delay),
                attempt=attempt + 1,
            )
        _notify(
            "specy-road grind-session",
            f"Claude limit hit on {node_id or 'this leaf'}; resuming in "
            f"{int(delay // 60)} min.",
        )
        wait(delay)
        command = _resume_command(implement_cmd, session_id)
    return 1
