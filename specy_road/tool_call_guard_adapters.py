"""The harness hook adapters behind ``specy-road session guard --format`` (split from tool_call_guard for the file limit)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# --- harness adapters ---------------------------------------------------------

@dataclass(frozen=True)
class Adapter:
    """One harness's hook protocol, as three answers.

    ``extract`` finds the command in the stdin payload (``None`` = nothing to
    judge). ``on_allow(note)`` and ``on_deny(reason)`` give ``(stdout, stderr,
    exit)`` the way that harness reads them; ``note`` is the allow-with-warning
    text, or ``None`` for a plain allow. ``config`` is the project-level
    snippet; ``notes`` the caveats. Every fact is cited inline, and an
    adapter ships only for a verified contract. An internal error is answered
    with ``on_deny``: the guard never fails open quietly.
    """

    name: str
    extract: Any
    on_allow: Any
    on_deny: Any
    config: str
    notes: str


def _bash_command(payload: dict[str, Any]) -> str | None:
    """Claude Code and Codex ``PreToolUse``: ``tool_input.command`` of the Bash tool; other tools are not ours to judge."""
    if payload.get("tool_name") != "Bash":
        return None
    return _string_command((payload.get("tool_input") or {}).get("command"), shell_event=True)


def _cursor_command(payload: dict[str, Any]) -> str | None:
    """Cursor ``beforeShellExecution``: ``command`` at top level."""
    return _string_command(payload.get("command"), shell_event=payload.get("hook_event_name") == "beforeShellExecution")


def _string_command(cmd: Any, *, shell_event: bool = False) -> str | None:
    """A command is a string; on a matched shell event a missing or non-string one is an error, answered with a deny."""
    if isinstance(cmd, str):
        return cmd or None
    if cmd is None and not shell_event:
        return None
    raise ValueError(f"command is {type(cmd).__name__}, not a string; refusing to guess what runs")


def _context_only(note: str | None) -> str | None:
    """Claude Code: a non-denial carries no ``permissionDecision``, so the harness's own permission policy still applies."""
    if not note:
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}})


# Verified against https://code.claude.com/docs/en/hooks (2026-10). Exit 2
# blocks and feeds stderr to the model; exit 0 applies JSON on stdout, where
# `additionalContext` reaches the model beside the tool result; any other
# exit code lets the call proceed. `permissionDecision: "allow"` skips the
# permission prompt, so a non-denial never emits one (review round 6, B14).
# Project hooks live in .claude/settings.json.
_CLAUDE_CODE = Adapter(
    "claude-code", _bash_command,
    lambda note: (_context_only(note), None, 0),
    lambda reason: (None, f"session guard: {reason}", 2),
    """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "specy-road session guard --format claude-code", "timeout": 30}
        ]
      }
    ]
  }
}""",
    "Put the snippet in .claude/settings.json (committed) or .claude/settings.local.json. Hooks run in "
    "`claude -p`; `claude --bare` skips every hook; whether bypassPermissions runs PreToolUse hooks is "
    "not stated in the docs. Exit codes other than 0 and 2 fail open, so an internal error exits 2.",
)

# Verified against https://learn.chatgpt.com/docs/hooks (2026-10): the same
# stdin shape as Claude Code; exit 2 + stderr denies; exit 0 with no output is
# the documented allow, and keys Codex does not support mark the hook failed,
# so an allow stays silent. Hook definitions must be trusted (`/hooks`) or run
# with --dangerously-bypass-hook-trust. Non-2 non-zero exits: unverified.
_CODEX = Adapter(
    "codex", _bash_command,
    lambda note: (None, None, 0),
    lambda reason: (None, f"session guard: {reason}", 2),
    """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "specy-road session guard --format codex", "timeout": 30,
           "statusMessage": "specy-road shared-checkout guard"}
        ]
      }
    ]
  }
}""",
    "Put the snippet in .codex/hooks.json (or [hooks] in .codex/config.toml); project hooks load only "
    "when the project's .codex/ layer is trusted, and each hook definition must be trusted in `/hooks` "
    "or run with --dangerously-bypass-hook-trust. Hooks fire under `codex exec`; the IDE extension is "
    "unverified. Allows are silent by design: Codex marks a hook failed on keys it does not support.",
)

# Verified against https://cursor.com/docs/hooks (2026-10): stdin carries the
# command at top level; the answer is JSON on stdout with snake_case keys;
# exit 2 also denies. Empty output on exit 0 counts as a hook failure, which
# fails OPEN unless failClosed is set, so every answer is explicit and the
# snippet sets failClosed: true. The command runs from the project root.
# A non-denial answers `allow` (the schema is allow|deny|ask); whether that
# bypasses Cursor's own prompt is unverified — runbook §3 checks it in a real IDE.
_CURSOR = Adapter(
    "cursor", _cursor_command,
    lambda note: (json.dumps({"permission": "allow", **({"agent_message": note} if note else {})}), None, 0),
    lambda reason: (json.dumps({"permission": "deny", "agent_message": reason,
                                "user_message": "specy-road: refused in a shared checkout"}), None, 0),
    """{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {"command": "specy-road session guard --format cursor", "timeout": 30, "failClosed": true, "matcher": ""}
    ]
  }
}""",
    "Put the snippet in .cursor/hooks.json. failClosed: true makes a crash or timeout block instead of "
    "fail open. Cursor's CLI (`agent`) runs beforeShellExecution; whether it fires in `agent -p` and "
    "under auto-run is unverified (community reports say deny holds, ask is ignored).",
)

ADAPTERS: dict[str, Adapter] = {
    "generic": Adapter(
        "generic", lambda p: _string_command(p.get("command")),
        lambda note: (None, f"session guard: allow {note}" if note else None, 0),
        lambda reason: (None, f"session guard: {reason}", 2),
        '{"command": "<the shell command>"}   # on stdin; exit 2 denies with the reason on stderr',
        "The contract the harness adapters are built on; wrap it for any harness not listed.",
    ),
    "claude-code": _CLAUDE_CODE,
    "codex": _CODEX,
    "cursor": _CURSOR,
}


