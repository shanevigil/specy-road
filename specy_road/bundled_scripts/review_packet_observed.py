"""Review-packet sections computed from git that ``review_packet.py`` (at its line cap) imports.

``## Test integrity`` lists every ``specy-road integrity`` finding for the commit
under review. When one of them removes or weakens a test and the node's
``planned_test_changes`` does not list it, ``## Required check: unplanned test
removal`` follows, for a leaf or a milestone and whatever ``policy.integrity_gate`` says, and ``review record``
refuses an approve without an ``acceptance`` entry for each line
(:mod:`specy_road.integrity_removals`, M15.18).
"""

from __future__ import annotations

from pathlib import Path

from specy_road.integrity import compare_integrity
from specy_road.integrity_removals import REQUIRED_HEADING, planned_for_target, unplanned_removals
from specy_road.review_target import ReviewTarget


def computed_note(t: ReviewTarget) -> str:
    return f"_Computed by review-packet from git (`{t.base}...{t.commit}`)._"


def test_integrity_section(root: Path, t: ReviewTarget) -> list[str]:
    """Deterministic ``## Test integrity`` block for the review packet."""
    return _integrity_block(t, _findings(root, t))


def integrity_sections(root: Path, t: ReviewTarget) -> list[str]:
    """``## Test integrity``, then the required check when a removal or weakening is unplanned."""
    findings = _findings(root, t)
    removals = [] if not findings else unplanned_removals(findings, planned_for_target(root, t))
    return _integrity_block(t, findings) + (unplanned_removal_lines(t, removals) if removals else [])


def _findings(root: Path, t: ReviewTarget) -> list[str] | None:
    """Integrity lines for ``base...commit``; ``None`` without both."""
    return [f.line() for f in compare_integrity(root, t.base, t.commit)] if t.base and t.commit else None


def _integrity_block(t: ReviewTarget, findings: list[str] | None) -> list[str]:
    if findings is None:
        return ["## Test integrity", "", "_(cannot compute: no merge base or no commit)_", ""]
    return ["## Test integrity", "", computed_note(t), "", *(findings or ["_none_"]), ""]


def unplanned_removal_lines(t: ReviewTarget, removals: list[str]) -> list[str]:
    """The required-check section for ``removals`` (integrity lines not in ``planned_test_changes``)."""
    return [
        f"## {REQUIRED_HEADING}", "",
        f"These findings remove or weaken a test, and `{t.node_id}`'s `planned_test_changes` (on the integration "
        f"branch or at the commit under review) does not list them. Whatever `policy.integrity_gate` says, an "
        "approve must carry one `acceptance` entry per line, keyed by the line exactly, once you have checked "
        "that an acceptance item and the diff justify the change: `\"<line>\": pass`. Otherwise block with a "
        "`required_changes` entry. `review record` refuses an approve without them.", "",
        *(f"- `{line}`" for line in removals), "",
        "The entries, for your record's `acceptance` once each is justified:", "",
        "```yaml", *(f'"{line}": pass' for line in removals), "```", "",
    ]
