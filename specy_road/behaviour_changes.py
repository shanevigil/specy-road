"""Behaviour changes that make common project agent instructions wrong.

Each entry records the version a change shipped in, the command and flags it
concerns, one line on what happens now, and optionally a pattern for project
text that still states the old behaviour. ``validate`` reports such text
(:mod:`specy_road.agent_text_report`); it never rewrites it.

Matching is per sentence (read whole across wrapped lines). Entries 1–4 require
the sentence to name ``command`` as a literal token (``specy-road <command>``
or inside backticks). Entry 5 (pickup ``--base``) also matches init-era prose
that names no command. A sentence that matches ``current`` describes today's
behaviour and is never reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _all_of(*parts: str) -> re.Pattern[str]:
    """Text that matches every regex in ``parts``, in any order."""
    return re.compile("".join(f"(?=.*(?:{part}))" for part in parts), re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class BehaviourChange:
    """One shipped change and the project text it contradicts."""

    since: str
    command: str
    flags: tuple[str, ...]
    now: str
    contradicts: re.Pattern[str] | None = None
    """The stale assertion, searched within one sentence."""
    current: re.Pattern[str] | None = None
    """Today's guidance: a sentence matching this is never reported."""
    command_anchor: bool = True
    """When false, ``contradicts`` may match without naming :attr:`command` (pickup ``--base`` only)."""

    def contradicted_by(self, sentence: str) -> bool:
        """Whether ``sentence`` asserts the stale behaviour, not the current one."""
        if self.contradicts is None:
            return False
        if self.command_anchor:
            cmd = re.escape(self.command)
            if not re.search(rf"\bspecy-road\s+{cmd}\b|`[^`]*(?<![\w-]){cmd}(?![\w-])[^`]*`", sentence):
                return False
        if not self.contradicts.search(sentence):
            return False
        return not (self.current is not None and self.current.search(sentence))


CATALOGUE: tuple[BehaviourChange, ...] = (
    BehaviourChange(
        since="0.3.1rc1",
        command="mark-implementation-reviewed",
        flags=("--yes",),
        now="`--yes` never creates a review: it approves only when independent review records already "
        "satisfy the policy, and an agent never approves its own work",
        contradicts=re.compile(r"--yes\b", re.IGNORECASE),
        current=re.compile(
            r"\b(?:never|do\s+not|don't|must\s+not|no\s+longer|only\s+when|refuse\w*|independent|recorded|"
            r"review\s+records?|already\s+satisf\w*|closes\s+the\s+gate|policy\s+met|"
            r"reviews?\s+are\s+already|handoff\s+status|review-packet)\b",
            re.IGNORECASE,
        ),
    ),
    BehaviourChange(
        since="0.3.1rc3",
        command="finish-this-task",
        flags=("--on-complete", "--override-on-complete"),
        now="an `--on-complete` mode other than pr that differs from the recorded one is refused unless "
        "`--override-on-complete` is passed, a person's choice that agents do not make",
        contradicts=re.compile(r"--on-complete[ =]+[`'\"]?(?:merge|auto)\b", re.IGNORECASE),
        current=re.compile(
            r"--override-on-complete|\brecorded\b|\brefuse\w*|\bdiffer\w*|merge\|pr|pr\|merge|on_complete=|"
            r"opens\s+a\s+PR\b|^specy-road finish-this-task --on-complete merge$",
            re.IGNORECASE,
        ),
    ),
    BehaviourChange(
        since="0.3.1rc1",
        command="do-next-available-task",
        flags=("--local",),
        now="`--local` registers the claim in this checkout only and pushes nothing",
        contradicts=re.compile(r"\balways\s+push", re.IGNORECASE),
        current=re.compile(r"--local\b|\bunless\b", re.IGNORECASE),
    ),
    BehaviourChange(
        since="0.3.1rc2",
        command="finish-this-task",
        flags=("--delete-branch",),
        now="`--delete-branch` (merge mode) deletes the feature branch locally and on the remote once the merge lands",
        contradicts=re.compile(
            r"\b(?:does\s+not|doesn't|never|won't|will\s+not)\s+delete\w*\b.*\bbranch", re.IGNORECASE
        ),
        current=re.compile(r"--delete-branch\b|\bunless\b", re.IGNORECASE),
    ),
    BehaviourChange(
        since="0.1.0rc1",
        command="do-next-available-task",
        flags=("--base",),
        now="pickup commits the claim to roadmap/registry.yaml on the integration branch (`--base`) before "
        "it creates the feature branch; no commit on the feature branch registers the work",
        contradicts=_all_of(
            r"\bfirst\s+commit\b",
            r"\bregister(?:s|ed|ing)?\b",
            r"\bfeature[-\s]branch|\bregistry\.yaml\b|\bregister\s+as\s+in-progress\b",
        ),
        current=re.compile(r"\bintegration\s+branch\b|--base\b", re.IGNORECASE),
        command_anchor=False,
    ),
)
