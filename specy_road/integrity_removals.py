"""Removed or weakened tests a leaf did not plan: a required reviewer check (M15.18).

``specy-road integrity`` reports removed tests, removed test files, new skips and
lost asserts. Each such line the node's ``planned_test_changes`` does not list is
an *unplanned test removal*: ``review-packet`` puts it under
:data:`REQUIRED_HEADING` and ``review record`` refuses an approve whose
``acceptance`` has no entry for it, whatever ``policy.integrity_gate`` says.

The plan is read from the integration branch and from the node as committed at
the reviewed commit: an owner may authorize a change after pickup on either, and
on the leaf branch the edit is reviewed with the diff. The integration branch is
resolved here from the git workflow config, never from ``ReviewTarget.base_ref``,
which ``review-packet --base`` (and a resumed delta) replace to move the diff
range: which commits are diffed and which ref authorizes are separate inputs. A
milestone's plan also takes its leaves' lists, since each removal there landed
with one of them; the check itself applies to every target kind.
"""

from __future__ import annotations

import re
from pathlib import Path

from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.finish_implementation_check import base_ref
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.integrity import compare_integrity
from specy_road.review_target import ReviewTarget, node_at

REQUIRED_HEADING = "Required check: unplanned test removal"
REMOVAL_KINDS = ("removed-test", "removed-test-file", "new-skip", "assert-loss")
# An acceptance key in a review record for one such line: the line exactly as integrity prints it.
REMOVAL_KEY = re.compile(r"^(?:removed-test|removed-test-file|new-skip|assert-loss): \S")


def unplanned_removals(lines: list[str], planned: set[str]) -> list[str]:
    """The removal and weakening lines of ``lines`` not in ``planned``, in order."""
    return [line for line in lines if line.split(":", 1)[0] in REMOVAL_KINDS and line not in planned]


def target_unplanned_removals(root: Path, t: ReviewTarget) -> list[str]:
    """Unplanned removals for any target's ``base...commit``; none without both commits."""
    if not t.base or not t.commit:
        return []
    return unplanned_removals([f.line() for f in compare_integrity(root, t.base, t.commit)], planned_for_target(root, t))


def integration_ref(root: Path) -> str | None:
    """The integration branch's ref (remote-tracking first), whatever diff base a packet was given."""
    ib, remote, _warn = resolve_integration_defaults(root, explicit_base=None, explicit_remote=None)
    return base_ref(root, remote, ib)


def _plan(nodes: list[dict] | None, ids: set[str]) -> set[str]:
    return {s for n in nodes or [] if n.get("id") in ids for s in n.get("planned_test_changes") or [] if isinstance(s, str)}


def planned_for_target(root: Path, t: ReviewTarget) -> set[str]:
    """``planned_test_changes`` on the integration branch and at the reviewed commit, together.

    For a milestone, the node's and its leaves' lists.
    """
    ids = {t.node_id, *(t.leaf_ids if t.milestone else [])}
    at_commit = _plan([n for i in ids if (n := node_at(root, i, t.commit))], ids)
    ref = integration_ref(root)
    return at_commit | (_plan(load_roadmap_nodes_at_ref(root, ref), ids) if ref else set())


def missing_removal_entries(acceptance: dict, removals: list[str]) -> list[str]:
    """The ``removals`` a record's ``acceptance`` has no entry for."""
    return [line for line in removals if line not in acceptance]
