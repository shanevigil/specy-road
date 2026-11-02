"""Acceptance items only a person can satisfy (``human:`` prefix) and the finish gate they add.

A criterion such as *a named person approves the wording* or *a link only a
person can supply* cannot be judged from a diff. Marked ``human:``, it is
``n/a`` for reviewers (:func:`role_prompt_rca.reviewer_preamble` says so and
``review_semantic_errors`` never counts ``n/a`` as a fail), and
``finish-this-task`` instead requires a recorded decision for it on the
planning sheet: a line, in any section, of the form ``A2: <decision>`` (an
optional list marker or checkbox in front is fine).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path

HUMAN_PREFIX = "human:"
_DECISION = re.compile(r"^\s*(?:[-*+]\s*(?:\[[ xX]\]\s*)?)?(A[1-9][0-9]*)\s*:\s*(\S.*)$")


def is_human_item(text: str) -> bool:
    return text.strip().lower().startswith(HUMAN_PREFIX)


def human_acceptance_ids(node: dict) -> list[str]:
    """The ``A#`` ids of ``node``'s criteria that start with ``human:``."""
    items = [a for a in node.get("acceptance") or [] if isinstance(a, str) and a.strip()]
    return [aid for aid, text in zip(acceptance_ids(node), items) if is_human_item(text)]


def recorded_decisions(sheet_text: str) -> dict[str, str]:
    """``A#`` -> decision text for every ``A#: <decision>`` line in a planning sheet."""
    out: dict[str, str] = {}
    for line in sheet_text.splitlines():
        m = _DECISION.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()
    return out


def undecided_human_items(root: Path, node: dict) -> list[str]:
    """The human-marked ids with no decision on the sheet; a missing sheet leaves them all undecided."""
    human = human_acceptance_ids(node)
    if not human:
        return []
    try:
        rel = normalize_planning_dir(node.get("planning_dir") or "")
        text = resolve_planning_path(root, rel).read_text(encoding="utf-8")
    except (OSError, ValueError):
        text = ""
    decided = recorded_decisions(text)
    return [aid for aid in human if aid not in decided]


def human_acceptance_or_exit(root: Path, node: dict) -> None:
    """Stop ``finish-this-task`` while a ``human:`` item has no recorded decision on the sheet."""
    missing = undecided_human_items(root, node)
    if not missing:
        return
    sheet = node.get("planning_dir") or "its planning sheet"
    ids = ", ".join(missing)
    print(
        f"error: {node['id']} has human acceptance item(s) with no recorded decision: {ids}.\n"
        "  Reviewers mark a `human:` item n/a; the person it names decides it instead.\n"
        f"  Record each decision as a line `- {missing[0]}: <decision, who and when>` in {sheet}\n"
        "  (any section), commit the sheet on this branch, then run finish-this-task again.",
        file=sys.stderr,
    )
    raise SystemExit(1)
