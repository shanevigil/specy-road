"""Removed or weakened tests a leaf did not plan: a required reviewer check (M15.18).

``specy-road integrity`` reports removed tests, removed test files, new skips and
lost asserts. Each such line the node's ``planned_test_changes`` does not list is
an *unplanned test removal*: ``review-packet`` puts it under
:data:`REQUIRED_HEADING` and ``review record`` refuses an approve whose
``acceptance`` has no entry for it, whatever ``policy.integrity_gate`` says.

The plan is read from the integration branch and from the node as committed at
the reviewed commit: an owner may authorize a change after pickup on either, and
on the leaf branch the edit is reviewed with the diff.
"""

from __future__ import annotations

import re
from pathlib import Path

from specy_road.integrity import compare_integrity
from specy_road.integrity_gate import planned_test_changes
from specy_road.review_target import ReviewTarget, node_at

REQUIRED_HEADING = "Required check: unplanned test removal"
REMOVAL_KINDS = ("removed-test", "removed-test-file", "new-skip", "assert-loss")
# An acceptance key in a review record for one such line: the line exactly as integrity prints it.
REMOVAL_KEY = re.compile(r"^(?:removed-test|removed-test-file|new-skip|assert-loss): \S")


def unplanned_removals(lines: list[str], planned: set[str]) -> list[str]:
    """The removal and weakening lines of ``lines`` not in ``planned``, in order."""
    return [line for line in lines if line.split(":", 1)[0] in REMOVAL_KINDS and line not in planned]


def target_unplanned_removals(root: Path, t: ReviewTarget) -> list[str]:
    """Unplanned removals for a leaf target's ``base...commit``; none for a milestone or without both commits."""
    if t.milestone or not t.base or not t.commit:
        return []
    return unplanned_removals([f.line() for f in compare_integrity(root, t.base, t.commit)], planned_for_target(root, t))


def planned_for_target(root: Path, t: ReviewTarget) -> set[str]:
    """``planned_test_changes`` on the integration branch and at the reviewed commit, together."""
    at_commit = (node_at(root, t.node_id, t.commit) or {}).get("planned_test_changes") or []
    planned = {s for s in at_commit if isinstance(s, str)}
    return planned | (planned_test_changes(root, t.base_ref, t.node_id) if t.base_ref else set())


def missing_removal_entries(acceptance: dict, removals: list[str]) -> list[str]:
    """The ``removals`` a record's ``acceptance`` has no entry for."""
    return [line for line in removals if line not in acceptance]
