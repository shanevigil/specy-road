"""Deny git, gh, worktree and cloud commands by orchestration role (M8.5).

Used by ``specy-road orchestration guard`` and the checked-in harness hook
snippets ``specyrd init`` can install. Unlike :mod:`specy_road.tool_call_guard`,
these rules apply whenever ``SPECY_ROAD_ORCHESTRATION_ROLE`` (or ``--role``) is
``reviewer`` or ``executor``, not only when another session is live.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

from specy_road import tool_call_guard_shapes as shapes
from specy_road.tool_call_guard import (
    _SHELLS,
    _SUBSTITUTION,
    _UNBALANCED,
    _git_subcommand,
    _opaque,
    _unwrap,
    split_segments,
)

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
    """:func:`_opaque` for a segment that mentions ``git`` or ``gh``: the ``gh`` case is judged as git would be."""
    reason = _opaque(segment)
    if reason or not _GH_WORD.search(segment):
        return reason
    reason = _opaque(_GH_WORD.sub("git", segment))
    return reason.replace("git", "gh") if reason else None


def _substitution_bodies(segment: str) -> tuple[list[str], str]:
    """Bodies of ``$(…)``, ``<(…)``, ``>(…)`` and backticks (nested too), and the segment with them blanked."""
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
    """``(command, reason)`` for ``eval …`` and ``sh -c …``: the text the wrapper runs, or why it cannot be seen."""
    if not inner:
        return None, None
    if inner[0] == "eval":
        if any(_EXPANSION.search(a) for a in inner[1:]) and _MENTIONS.search(segment):
            return None, "eval of a shell expansion that mentions git or gh; the guard cannot see what runs"
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
        return True, ("could not parse this shell command and it mentions git or gh; rewrite it plainly" if mentions else None)
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
    if sub == "!":                                   # `git -c alias.x='!cmd' x` runs cmd through the shell
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
            command = re.sub(rf"\$\{{{m.group(1)}\b[^}}]*\}}|\${m.group(1)}\b", lambda _m: value, command)
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
