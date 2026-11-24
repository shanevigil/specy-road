"""``specy-road orchestration guard``: deny git, gh, worktree and cloud commands by role.

Used by ``specy-road orchestration guard`` and the checked-in harness hook
snippets ``specyrd init`` can install. Unlike
:mod:`specy_road.orchestration.guard.tool_call_guard`, these rules apply
whenever ``SPECY_ROAD_ORCHESTRATION_ROLE`` (or ``--role``) is ``reviewer`` or
``executor``, not only when another session is live. The harness hook adapters
below turn a verdict into each harness's answer and print its hook snippet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from typing import Any

from specy_road.orchestration import (
    _SHELLS,
    _SUBSTITUTION,
    _UNBALANCED,
    _bash_command,
    _cursor_command,
    _git_subcommand,
    _opaque,
    _string_command,
    _unwrap,
    print_answer,
    read_payload,
    split_segments,
)
from specy_road.orchestration import tool_call_guard_shapes as shapes
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

ROLE_CHOICES = frozenset({"reviewer", "executor"})

_GH_VALUE_FLAGS = frozenset({"-R", "--repo"})
_GH_WORD = re.compile(r"\bgh\b")
#: A segment that names either tool is inspected even when a parser cannot follow it.
_MENTIONS = re.compile(r"\b(?:git|gh)\b")
_EXPANSION = re.compile(r"[$`]")
_SHELL_C = ("-c", "-lc", "-ic", "-ec", "-xc")
_WORKTREE = re.compile(
    r"(?<![\w-])(?:--worktree|--worktree-base)\b|(?<![\w-])git\s+worktree\b"
    r"|(?<![\w-])codex\s+(?:exec\s+)?(?:--worktree\b|--cloud\b|fork\b|cloud\b)"
    r"|(?<![\w-])claude\b[^|;&\n]*--(?:cloud|worktree)\b"
    r"|(?<![\w-])agent\b[^|;&\n]*(?:(?<![\w-])-w(?![\w-])|--worktree\b)"
    r"|(?<![\w-])(?:agent\s+persist|/goal\b|/split-to-prs\b|/autopilot\b)",
    re.IGNORECASE,
)
_CLOUD = re.compile(
    r"(?<![\w-])claude\b[^|;&\n]*--cloud\b"
    r"|(?<![\w-])codex\s+(?:exec\s+)?(?:--cloud\b|cloud\b)"
    r"|(?<![\w-])ultrareview\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RoleVerdict:
    denied: bool
    reason: str
    command: str


def orchestration_role() -> str | None:
    raw = (os.environ.get("SPECY_ROAD_ORCHESTRATION_ROLE") or "").strip().lower()
    return raw if raw in ROLE_CHOICES else None


def _segment_gh_pr(segment: str) -> bool:
    try:
        tokens = shlex.split(segment, comments=True)
    except ValueError:
        return bool(re.search(r"\bgh\b[^|;&\n]*\bpr\b", segment, re.I))
    tokens = _unwrap(tokens)
    i = 0
    while i < len(tokens):
        if tokens[i].rsplit("/", 1)[-1] == "gh":
            j = i + 1
            while j < len(tokens) and tokens[j].startswith("-"):
                flag = tokens[j]
                if "=" in flag:
                    j += 1
                elif flag in _GH_VALUE_FLAGS or (flag.startswith("--") and flag != "--"):
                    j += 2
                else:
                    j += 1
            if j < len(tokens) and tokens[j].lower() == "pr":
                return True
        i += 1
    return False


def _opaque_for_role(segment: str) -> str | None:
    """:func:`_opaque` for a segment that mentions ``git`` or ``gh``: the ``gh`` case is judged as
    git would be."""
    reason = _opaque(segment)
    if reason or not _GH_WORD.search(segment):
        return reason
    reason = _opaque(_GH_WORD.sub("git", segment))
    return reason.replace("git", "gh") if reason else None


def _substitution_bodies(segment: str) -> tuple[list[str], str]:
    """Bodies of ``$(…)``, ``<(…)``, ``>(…)`` and backticks (nested too), and the segment with them
    blanked."""
    bodies: list[str] = []
    rest = segment
    for _ in range(8):
        found = [m.group(1) or m.group(2) or "" for m in _SUBSTITUTION.finditer(rest)]
        if not found:
            break
        bodies.extend(found)
        rest = _SUBSTITUTION.sub(" x ", rest)
    return bodies, rest


def _wrapped_command(inner: list[str], segment: str) -> tuple[str | None, str | None]:
    """``(command, reason)`` for ``eval …`` and ``sh -c …``: the text the wrapper runs, or why it
    cannot be seen."""
    if not inner:
        return None, None
    if inner[0] == "eval":
        if any(_EXPANSION.search(a) for a in inner[1:]) and _MENTIONS.search(segment):
            return None, ("eval of a shell expansion that mentions git or gh; "
                          "the guard cannot see what runs")
        return " ".join(inner[1:]), None
    if inner[0].rsplit("/", 1)[-1] in _SHELLS:
        for j, t in enumerate(inner[1:], 1):
            if t in _SHELL_C or (t.startswith("-") and "c" in t[1:] and len(t) <= 4):
                return (inner[j + 1] if j + 1 < len(inner) else None), None
    return None, None


def _indirect(segment: str, role: str) -> tuple[bool, str | None]:
    """``(handled, reason)`` for what a segment runs indirectly.

    Command substitutions, ``eval`` and ``sh -c`` bodies are judged by what
    they run; a segment the parser cannot follow (a command name from a
    variable, ``env -S``, ``xargs git``, an interpreter one-liner) that
    mentions ``git`` or ``gh`` is denied rather than waved through. Not
    handled means the caller judges the plain tokens.
    """
    bodies, rest = _substitution_bodies(segment)
    for body in bodies:
        reason = classify_for_role(body, role)
        if reason:
            return True, reason
    mentions = bool(_MENTIONS.search(segment))
    if _UNBALANCED.search(rest) and mentions:
        return True, "unbalanced command substitution mentioning git or gh; rewrite it plainly"
    opaque = _opaque_for_role(segment) if mentions else None
    if opaque:
        return True, opaque
    try:
        tokens = shlex.split(segment, comments=True)
    except ValueError:
        return True, (
            "could not parse this shell command and it mentions git or gh; rewrite it plainly"
            if mentions else None
        )
    wrapped, reason = _wrapped_command(_unwrap(tokens), segment)
    if reason or wrapped is not None:
        return True, reason or classify_for_role(wrapped or "", role)
    return False, None


def _reason_for_segment(segment: str, role: str) -> str | None:
    """Why one segment is denied for ``role``, else ``None``."""
    handled, reason = _indirect(segment, role)
    if handled:
        return reason
    sub, args = _git_subcommand(shlex.split(segment, comments=True))
    if sub == "!":  # `git -c alias.x='!cmd' x` runs cmd through the shell
        return classify_for_role(" ".join(args), role)
    if shapes.dynamic_verb(sub):
        return shapes.dynamic_verb(sub)
    sub = sub.lower() if sub else None
    if sub == "commit" and role == "reviewer":
        return "reviewers must not commit; the executor owns implementation commits"
    if sub == "push":
        return "orchestration roles must not push; finish-this-task and the maintainer push"
    if _segment_gh_pr(segment):
        return "orchestration roles must not open pull requests; finish-this-task owns the PR"
    if role == "executor" and _WORKTREE.search(segment):
        return "executors must not create harness worktrees; specy-road owns linked worktrees"
    if role == "executor" and _CLOUD.search(segment):
        return "executors must not start cloud or fork sessions the orchestrator does not own"
    return None


def _inline_tool_vars(command: str) -> str:
    """``g=git; $g commit`` is ``git commit`` and ``h=gh; $h pr`` is ``gh pr`` to the guard."""
    command = shapes.inline_git_vars(command)
    for m in shapes._ASSIGN.finditer(command):
        value = next((v for v in m.groups()[1:] if v is not None), "")
        if re.match(r"(\S*/)?gh(\s|$)", value):
            pattern = rf"\$\{{{m.group(1)}\b[^}}]*\}}|\${m.group(1)}\b"
            command = re.sub(pattern, lambda _m: value, command)
    return command


def classify_for_role(command: str, role: str) -> str | None:
    if role not in ROLE_CHOICES:
        return None
    for seg in split_segments(_inline_tool_vars(command).strip()):
        reason = _reason_for_segment(seg, role)
        if reason:
            return reason
    return None


def decide_role(command: str, *, role: str | None = None) -> RoleVerdict:
    role = (role or orchestration_role() or "").strip().lower()
    if role not in ROLE_CHOICES:
        return RoleVerdict(False, "", command)
    reason = classify_for_role(command, role)
    if not reason:
        return RoleVerdict(False, "", command)
    return RoleVerdict(True, f"orchestration guard ({role}): {reason}", command)


# Harness hook adapters


@dataclass(frozen=True)
class OrchestrationAdapter:
    name: str
    extract: Any
    on_allow: Any
    on_deny: Any
    config_executor: str
    config_reviewer: str
    notes: str


def _claude_hook(role: str) -> str:
    return (
        f'SPECY_ROAD_ORCHESTRATION_ROLE={role} specy-road orchestration guard --format claude-code'
    )


_CLAUDE_JSON = """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "%s", "timeout": 30, "onFailure": "block"}
        ]
      }
    ]
  }
}"""

_CLAUDE_EXEC = OrchestrationAdapter(
    "claude-code",
    _bash_command,
    lambda _note: (None, None, 0),
    lambda reason: (None, reason, 2),
    _CLAUDE_JSON % _claude_hook("executor"),
    _CLAUDE_JSON % _claude_hook("reviewer"),
    "One hook in .claude/settings.json (or settings.local.json); role from "
    "$SPECY_ROAD_ORCHESTRATION_ROLE. Exit 2 blocks; exit 1 does not. "
    "onFailure block fails closed on timeout or crash. Hooks run under claude -p.",
)

_CODEX_HOOK = 'SPECY_ROAD_ORCHESTRATION_ROLE=%s specy-road orchestration guard --format codex'

_CODEX_JSON = """{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "%s", "timeout": 30,
           "statusMessage": "specy-road orchestration guard"}
        ]
      }
    ]
  }
}"""

_CODEX = OrchestrationAdapter(
    "codex",
    _bash_command,
    lambda _note: (None, None, 0),
    lambda reason: (None, reason, 2),
    _CODEX_JSON % (_CODEX_HOOK % "executor"),
    _CODEX_JSON % (_CODEX_HOOK % "reviewer"),
    "One hook in .codex/hooks.json; role from $SPECY_ROAD_ORCHESTRATION_ROLE. "
    "Project hooks load only when .codex/ is trusted, or run once with "
    "--dangerously-bypass-hook-trust for specy-road's own hook files. Exit 2 denies.",
)

_CURSOR_JSON = """{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {"command": "%s", "timeout": 30, "failClosed": true, "matcher": ""}
    ]
  }
}"""

_CURSOR = OrchestrationAdapter(
    "cursor",
    _cursor_command,
    lambda _note: (json.dumps({"permission": "allow"}), None, 0),
    lambda reason: (
        json.dumps(
            {
                "permission": "deny",
                "agent_message": reason,
                "user_message": "specy-road: refused for this orchestration role",
            }
        ),
        None,
        0,
    ),
    _CURSOR_JSON % ("SPECY_ROAD_ORCHESTRATION_ROLE=executor "
                    "specy-road orchestration guard --format cursor"),
    _CURSOR_JSON % ("SPECY_ROAD_ORCHESTRATION_ROLE=reviewer "
                    "specy-road orchestration guard --format cursor"),
    "One hook in .cursor/hooks.json with failClosed true; role from "
    "$SPECY_ROAD_ORCHESTRATION_ROLE. Cursor also merges .claude/settings.json hooks.",
)

ADAPTERS: dict[str, OrchestrationAdapter] = {
    "generic": OrchestrationAdapter(
        "generic",
        lambda p: _string_command(p.get("command")),
        lambda _note: (None, None, 0),
        lambda reason: (None, reason, 2),
        '{"command": "SPECY_ROAD_ORCHESTRATION_ROLE=executor '
        'specy-road orchestration guard --format generic"}',
        '{"command": "SPECY_ROAD_ORCHESTRATION_ROLE=reviewer '
        'specy-road orchestration guard --format generic"}',
        "Generic contract: JSON stdin with a command field; exit 2 denies.",
    ),
    "claude-code": _CLAUDE_EXEC,
    "codex": _CODEX,
    "cursor": _CURSOR,
}


def cmd_orchestration_guard(ns: argparse.Namespace) -> int:
    adapter = ADAPTERS[ns.format]
    role = ns.role or orchestration_role()
    if ns.print_config:
        cfg = adapter.config_reviewer if ns.config_role == "reviewer" else adapter.config_executor
        print(cfg)
        print(f"# {adapter.notes}", file=sys.stderr)
        return 0
    try:
        resolve_repo_root(ns)
        command = ns.command or adapter.extract(read_payload(sys.stdin.read()))
        if not command:
            return print_answer(adapter.on_allow(None))
        if role not in ROLE_CHOICES:
            return print_answer(adapter.on_allow(None))
        v = decide_role(command, role=role)
    except Exception as e:  # noqa: BLE001 — fail closed
        return print_answer(
            adapter.on_deny(f"internal error ({e}); refusing rather than failing open")
        )
    if v.denied:
        return print_answer(adapter.on_deny(v.reason))
    return print_answer(adapter.on_allow(None))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road orchestration guard")
    p.add_argument("--format", choices=sorted(ADAPTERS), required=True)
    p.add_argument("--command", metavar="CMD",
                   help="Judge this command (default: harness stdin payload)")
    p.add_argument("--role", choices=sorted(ROLE_CHOICES),
                   help="Override $SPECY_ROAD_ORCHESTRATION_ROLE")
    p.add_argument(
        "--print-config",
        action="store_true",
        help="Print hook JSON for --config-role on stdout; caveats on stderr",
    )
    p.add_argument(
        "--config-role",
        choices=("executor", "reviewer"),
        default="executor",
        help="Which role snippet --print-config emits (default: executor)",
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_orchestration_guard)
    return p


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
