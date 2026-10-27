"""Decide whether a shell command is safe to run in a checkout other agents share.

The guard behind ``specy-road session guard`` and the harness hook adapters
(proposal §3.4, §3.5; design note
``docs/design-notes/agent-guidance-and-shared-checkouts.md``, decision 6).

A command is **destructive in a shared tree** when it can move or discard
work that is not the caller's: anything that stashes, resets, switches
branches, discards working-tree changes, rewrites history, force-pushes, or
sweeps every change into a commit. Each ``git`` segment of a chained command
is classified on its own, so ``make test && git stash`` is caught.

The verdict is **deny only when another live session is present** (per
``work/.sessions/``), or when the caller asks for ``always``. Alone in a
tree, these commands are the agent's own business; the rules exist to keep
one session from landing on another.

Harness adapters live here too, one per protocol. Each knows how to find the
command in what its harness sends and how to say allow or deny the way that
harness expects. ``generic`` is the contract the others are built on.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.session_presence import list_sessions

ALLOW = "allow"
DENY = "deny"

_SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
_GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


@dataclass
class Verdict:
    decision: str
    reason: str
    command: str

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW


def _git_subcommand(tokens: list[str]) -> tuple[str | None, list[str]]:
    """``(subcommand, its args)`` for a ``git …`` token list, else ``(None, [])``."""
    i = 0
    while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
        i += 1  # leading VAR=value assignments
    if i >= len(tokens) or tokens[i] != "git":
        return None, []
    i += 1
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] in _GIT_GLOBAL_WITH_ARG:
            i += 2
        else:
            i += 1
    if i >= len(tokens):
        return None, []
    return tokens[i], tokens[i + 1:]


def _short_flags(args: list[str]) -> str:
    """Letters from every clustered short flag (``-am`` → ``am``)."""
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--") and len(a) > 1)


def classify_segment(segment: str) -> str | None:
    """The reason a single command is destructive in a shared tree, else ``None``."""
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return None
    sub, args = _git_subcommand(tokens)
    if sub is None:
        return None
    flags = _short_flags(args)
    positional = [a for a in args if not a.startswith("-")]
    if sub == "stash":
        return "git stash: the stash stack is shared by every session in this checkout"
    if sub == "reset" and any(a in ("--hard", "--merge", "--keep") for a in args):
        return f"git reset {next(a for a in args if a.startswith('--'))}: discards other sessions' uncommitted work"
    if sub == "switch" or (sub == "checkout" and ("--" not in args) and (positional or "b" in flags or "B" in flags or "--orphan" in args)):
        return f"git {sub}: switching branches moves every other session's working tree too; use `git worktree add`"
    if sub == "checkout" and "--" in args:
        return "git checkout -- <paths>: discards working-tree changes that may be another session's"
    if sub == "restore" and ("." in positional or ":/" in positional):
        return "git restore .: discards every session's uncommitted changes"
    if sub == "clean" and ("f" in flags or "--force" in args):
        return "git clean -f: deletes untracked files other sessions are still writing"
    if sub == "rebase":
        return "git rebase: rewrites history under other sessions' feet"
    if sub == "commit" and "--amend" in args:
        return "git commit --amend: rewrites a commit another session may already build on"
    if sub == "commit" and ("a" in flags or "--all" in args):
        return "git commit -a: sweeps every session's tracked changes into your commit; stage by explicit path"
    if sub == "add" and ("A" in flags or "u" in flags or "--all" in args or "--update" in args
                         or any(p in (".", ":/", "-A") for p in positional)):
        return "git add -A/-u/.: stages other sessions' files; `git add <paths>` only"
    if sub == "push" and ("f" in flags or any(a.startswith("--force") for a in args) or any(p.startswith("+") for p in positional)):
        return "git push --force: rewrites the remote branch other sessions pull from"
    return None


def classify(command: str) -> str | None:
    """The first destructive segment's reason, else ``None``."""
    for seg in _SEGMENT_SPLIT.split(command.strip()):
        if seg:
            reason = classify_segment(seg)
            if reason:
                return reason
    return None


def shared_with_others(repo_root: Path, agent: str | None) -> list[str]:
    """Ids of other live sessions in this checkout."""
    return [s.agent for s in list_sessions(repo_root) if s.agent != agent]


def decide(repo_root: Path, command: str, *, agent: str | None, always: bool = False) -> Verdict:
    reason = classify(command)
    if not reason:
        return Verdict(ALLOW, "", command)
    others = shared_with_others(repo_root, agent)
    if not others and not always:
        return Verdict(ALLOW, f"(would deny with another live session: {reason})", command)
    who = f"live sessions: {', '.join(others)}" if others else "guard runs with --always"
    return Verdict(DENY, f"refused in a shared checkout ({who}) — {reason}. "
                         "See the shared-checkout rules in AGENTS.md; `specy-road session list` shows who is here.", command)


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
    """Claude Code and Codex ``PreToolUse``: ``tool_input.command`` of the Bash tool."""
    if payload.get("tool_name") != "Bash":
        return None
    cmd = (payload.get("tool_input") or {}).get("command")
    return str(cmd) if cmd else None


def _pre_tool_use(decision: str, **fields: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, **fields}})


# Verified against https://code.claude.com/docs/en/hooks (2026-10). Exit 2
# blocks and feeds stderr to the model; exit 0 applies JSON on stdout, where
# `additionalContext` reaches the model beside the tool result; any other
# exit code lets the call proceed. Project hooks live in .claude/settings.json.
_CLAUDE_CODE = Adapter(
    "claude-code", _bash_command,
    lambda note: (_pre_tool_use("allow", additionalContext=note) if note else None, None, 0),
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
_CURSOR = Adapter(
    "cursor", lambda p: (str(p.get("command") or "") or None),
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
        "generic", lambda p: (str(p.get("command") or "") or None),
        lambda note: (None, f"session guard: allow {note}" if note else None, 0),
        lambda reason: (None, f"session guard: {reason}", 2),
        '{"command": "<the shell command>"}   # on stdin; exit 2 denies with the reason on stderr',
        "The contract the harness adapters are built on; wrap it for any harness not listed.",
    ),
    "claude-code": _CLAUDE_CODE,
    "codex": _CODEX,
    "cursor": _CURSOR,
}


def read_payload(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
