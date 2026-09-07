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
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from specy_road.claude_code_limits import (
    SPEND,
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

#: Re-runs when the command dies without printing anything. A process killed
#: from outside is not a failed implementation, but the same shape could be a
#: genuinely broken tool, so the bound is tight.
MAX_EMPTY_RETRIES = 2

#: Linear backoff between those re-runs: 30s, then 60s.
EMPTY_RETRY_SECONDS = 30


@dataclass(frozen=True)
class ImplementLimits:
    """The bounds one leaf's implement step runs under."""

    max_resumes: int
    max_wait_seconds: int
    grace_seconds: int
    max_empty_retries: int

    @classmethod
    def defaults(cls) -> "ImplementLimits":
        """The module constants as they are *now*.

        Read at call time, not bound as field defaults: a default would fix the
        value at class creation and quietly ignore anyone who patches the
        module constants, which the tests do.
        """
        return cls(
            MAX_RESUMES, MAX_WAIT_SECONDS, GRACE_SECONDS, MAX_EMPTY_RETRIES
        )


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


#: Leading whitespace plus one shell word: quoted runs, backslash escapes, or
#: plain characters. Used only to find where the executable token ends.
_FIRST_TOKEN = re.compile(r"""\s*(?:'[^']*'|"(?:\\.|[^"\\])*"|\\.|[^\s'"\\])+""")


def _resume_command(implement_cmd: str, session_id: str) -> str:
    """The same command again, continuing the session Claude already opened.

    Everything after the executable is spliced, not rebuilt. ``shlex.split``
    followed by ``shlex.quote`` round-trips *text*, not shell syntax, and the
    invocation the docs recommend --
    ``claude -p "$(cat "$SPECY_ROAD_PROMPT")"`` -- came back as the
    single-quoted literal ``'$(cat $SPECY_ROAD_PROMPT)'``. The command runs
    under a shell, so a resumed session was handed 26 characters of shell
    source as its task, exited 0, and looked like ordinary work. The user's
    own flags are kept verbatim, permission mode included; we add ``--resume``
    and never ``--dangerously-skip-permissions``.

    Re-evaluating the substitution on resume is what we want: the prompt file
    is still on disk, because ``finish-this-task`` has not run yet.
    """
    match = _FIRST_TOKEN.match(implement_cmd)
    if not match:  # unreachable: is_claude_cli() already found a first token
        return implement_cmd
    end = match.end()
    return (
        f"{implement_cmd[:end]} --resume {shlex.quote(session_id)}"
        f"{implement_cmd[end:]}"
    )


def seconds_until(
    reset_at: datetime,
    *,
    now: datetime | None = None,
    grace_seconds: int | None = None,
) -> float:
    """Seconds to wait for ``reset_at``, plus grace. Never negative."""
    current = now or datetime.now(timezone.utc)
    grace = GRACE_SECONDS if grace_seconds is None else grace_seconds
    return max(0.0, (reset_at - current).total_seconds() + grace)


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


def _vanished_without_output(code: int, output: str) -> bool:
    """Killed from outside before it managed to say anything.

    Both conditions matter. Empty output alone would swallow a task that
    failed and explained itself in silence -- a linter exiting 1, a ``set -e``
    script -- and turn one honest failure into three pointless runs. A
    signal-shaped code alone would retry a real crash that already printed a
    traceback. Together they describe only "something outside the run killed
    it": ``sh -c`` reports a signalled child as ``128 + signal``, and when the
    shell execs a single simple command directly the same kill arrives as a
    negative ``returncode``.
    """
    return not output.strip() and (code < 0 or code >= 128)


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


def _emit(emitter, event: str, **fields) -> None:
    """Emit when there is an emitter. Keeps the call sites flat."""
    if emitter is not None:
        emitter.emit(event, **fields)


def _retry_after_vanishing(
    code: int,
    attempt: int,
    cfg: ImplementLimits,
    node_id: str,
    emitter,
    wait,
) -> int | None:
    """Back off, then let the caller run again. An int means stop and say why."""
    if attempt > cfg.max_empty_retries:
        return _fail(
            f"grind-session: the implement command exited {code} without "
            f"printing anything, {cfg.max_empty_retries + 1} times in a row. "
            "Something outside the run is killing it -- an OOM kill, a machine "
            "that slept, a closed terminal -- so this is not a task failure "
            "and there is nothing in the output to act on. Re-run when the "
            "environment is stable (see 'caffeinate' and 'tmux' in "
            "docs/grind-session.md)."
        )
    delay = EMPTY_RETRY_SECONDS * attempt
    _emit(
        emitter,
        "implementer_vanished",
        node_id=node_id,
        rc=code,
        attempt=attempt,
        max_retries=cfg.max_empty_retries,
        retry_in_seconds=int(delay),
    )
    wait(delay)
    return None


def _wait_out_limit(
    verdict,
    repo_root: Path,
    cfg: ImplementLimits,
    waits: int,
    node_id: str,
    emitter,
    wait,
) -> tuple[int | None, str | None]:
    """Sleep until the stated reset. ``(exit code, session id)``.

    An exit code means stop and say why; a session id means resume it.
    """
    if waits > cfg.max_resumes:
        return _fail(
            f"grind-session: still rate-limited after {cfg.max_resumes} waits; "
            "stopping rather than looping. Re-run when the quota recovers."
        ), None
    session_id = verdict.session_id or latest_session_id(repo_root)
    if not session_id:
        return _fail(
            "grind-session: hit a timed Claude session limit but could not "
            "find the session id to resume, so the work so far would be "
            "abandoned. Claude Code's output format may have changed.\n"
            f"  saw: {verdict.evidence}"
        ), None
    delay = seconds_until(verdict.reset_at, grace_seconds=cfg.grace_seconds)
    if delay > cfg.max_wait_seconds:
        return _fail(
            f"grind-session: the stated reset is {delay / 3600:.1f} hours "
            f"away, beyond the {cfg.max_wait_seconds / 3600:g}h this loop "
            "waits unattended. Raise --max-limit-wait-hours (or "
            "grind_session_max_limit_wait_hours in roadmap/git-workflow.yaml) "
            "if that is what you want, or re-run after it lifts."
        ), None
    _emit(
        emitter,
        "usage_limited",
        node_id=node_id,
        reset_at=verdict.reset_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        wait_seconds=int(delay),
        attempt=waits,
    )
    _notify(
        "specy-road grind-session",
        f"Claude limit hit on {node_id or 'this leaf'}; resuming in "
        f"{int(delay // 60)} min.",
    )
    wait(delay)
    return None, session_id


def run_implement_hook(
    implement_cmd: str,
    env: dict,
    repo_root: Path,
    *,
    emitter=None,
    node_id: str = "",
    run_shell=None,
    sleep=None,
    limits: ImplementLimits | None = None,
) -> int:
    """Run the implement hook, waiting out Claude's timed limits if it is Claude.

    ``run_shell`` is the generic runner every non-Claude hook keeps using, so
    that path retains its inherited streams and its exact current behaviour.

    Two bounded categories, counted separately so neither eats the other's
    budget: a stated limit is waited out and the session resumed, and a
    process killed from outside before it printed anything is simply run
    again.
    """
    if not is_claude_cli(implement_cmd):
        return run_shell(implement_cmd, env, repo_root)

    # Resolved here, not as default arguments: a default binds at import and
    # would ignore anyone who patches the module's clock or its bounds.
    wait = sleep if sleep is not None else time.sleep
    cfg = limits if limits is not None else ImplementLimits.defaults()
    command = implement_cmd
    waits = vanishings = 0
    while True:  # both counters only rise, and both are bounded
        code, output = _run_capturing(command, env, repo_root)
        if code == 0:
            return 0
        if _vanished_without_output(code, output):
            vanishings += 1
            stop = _retry_after_vanishing(
                code, vanishings, cfg, node_id, emitter, wait
            )
            if stop is not None:
                return stop
            command = implement_cmd  # a fresh run, never a guessed resume
            continue
        verdict = classify_limit(output)
        refusal = _limit_refusal(verdict, node_id)
        if refusal is not None:
            return refusal
        if not verdict.is_waitable:
            return code  # an ordinary failure; the loop reports it as always
        waits += 1
        stop, session_id = _wait_out_limit(
            verdict, repo_root, cfg, waits, node_id, emitter, wait
        )
        if stop is not None:
            return stop
        command = _resume_command(implement_cmd, session_id)
