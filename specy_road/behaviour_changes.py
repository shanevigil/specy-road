"""Behaviour changes that make common project agent instructions wrong.

Each entry records the version a change shipped in, the command and flags it
concerns, one line on what happens now, and optionally a pattern for a line of
project text that still states the old behaviour. ``validate`` reports such
lines (:mod:`specy_road.agent_text_report`); it never rewrites them.

A pattern that could match ordinary prose requires the command's name on the
same line; the commandless first-commit pattern instead requires the claim's
context (feature branch, registry, claim, in-progress or "the work").
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BehaviourChange:
    """One shipped change and the project text it contradicts."""

    since: str
    command: str
    flags: tuple[str, ...]
    now: str
    contradicts: re.Pattern[str] | None = None


def _line_with(*parts: str) -> re.Pattern[str]:
    """A line that matches every regex in ``parts``, in any order."""
    return re.compile("".join(f"(?=.*(?:{part}))" for part in parts), re.IGNORECASE)


CATALOGUE: tuple[BehaviourChange, ...] = (
    BehaviourChange(
        since="0.3.1rc1",
        command="mark-implementation-reviewed",
        flags=("--yes",),
        now="`--yes` never creates a review: it approves only when independent review records already "
        "satisfy the policy, and an agent never approves its own work",
        contradicts=_line_with(r"\bmark-implementation-reviewed\b", r"--yes\b"),
    ),
    BehaviourChange(
        since="0.3.1rc3",
        command="finish-this-task",
        flags=("--on-complete", "--override-on-complete"),
        now="an `--on-complete` mode other than pr that differs from the recorded one is refused unless "
        "`--override-on-complete` is passed, a person's choice that agents do not make",
        contradicts=_line_with(r"\bfinish-this-task\b", r"--on-complete[ =]+[`'\"]?(?:merge|auto)\b"),
    ),
    BehaviourChange(
        since="0.3.1rc1",
        command="do-next-available-task",
        flags=("--local",),
        now="`--local` registers the claim in this checkout only and pushes nothing",
        contradicts=_line_with(r"\b(?:do-next-available-task|pickup)\b", r"\balways\s+push"),
    ),
    BehaviourChange(
        since="0.3.1rc2",
        command="finish-this-task",
        flags=("--delete-branch",),
        now="`--delete-branch` (merge mode) deletes the feature branch locally and on the remote once the merge lands",
        contradicts=_line_with(
            r"\bfinish-this-task\b", r"\b(?:does\s+not|doesn't|never|won't|will\s+not)\s+delete\w*\b.*\bbranch"
        ),
    ),
    BehaviourChange(
        since="0.1.0rc1",
        command="do-next-available-task",
        flags=("--base",),
        now="pickup commits the claim to roadmap/registry.yaml on the integration branch (`--base`) before "
        "it creates the feature branch; no commit on the feature branch registers the work",
        contradicts=_line_with(
            r"\bfirst\s+commit\b",
            r"\bregister(?:s|ed|ing)?\b",
            r"\bfeature[-\s]branch|\bregistry\b|\bclaim\b|\bin-progress\b|\bthe\s+work\b",
        ),
    ),
)
