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

from specy_road.tool_call_guard import _git_subcommand, _unwrap, split_segments

ROLE_CHOICES = frozenset({"reviewer", "executor"})

_GH_VALUE_FLAGS = frozenset({"-R", "--repo"})
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


def _segment_git_sub(segment: str) -> str | None:
    try:
        tokens = shlex.split(segment, comments=True)
    except ValueError:
        return None
    sub, _rest = _git_subcommand(tokens)
    if not sub or sub == "!":
        return None
    return sub.lower()


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


def _reason_for_segment(segment: str, role: str) -> str | None:
    sub = _segment_git_sub(segment)
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


def classify_for_role(command: str, role: str) -> str | None:
    if role not in ROLE_CHOICES:
        return None
    for seg in split_segments(command.strip()):
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
