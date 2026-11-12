"""Acceptance items only a person can satisfy (``human:`` prefix) and the finish gate they add.

A criterion such as *a named person approves the wording* or *a link only a
person can supply* cannot be judged from a diff. Marked ``human:``, it is
``n/a`` for reviewers (:func:`role_prompt_rca.reviewer_preamble` says so and
``review_semantic_errors`` never counts ``n/a`` as a fail), and
``finish-this-task`` instead requires a person's decision for it in the
decisions ledger (M22.69): a closed ``kind: human-action`` entry with ``node``
the leaf, ``criterion: A#``, ``decided_by: operator`` and ``channel``
``terminal`` (``decisions close`` at an interactive terminal) or ``pm-gui``
(the PM GUI's answer). Only ``roadmap/decisions.yaml`` as committed at the leaf
branch's HEAD or at the integration branch tip counts; the working tree,
``decisions.local.yaml`` and a planning-sheet ``A#:`` line do not, since any
agent can write those.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.brief_acceptance import acceptance_ids
from specy_road.decisions import DECISIONS_REL
from specy_road.review_override import OPERATOR, PM_GUI
from specy_road.review_policy_ref import committed_yaml

HUMAN_PREFIX = "human:"
TERMINAL = "terminal"   # the ``channel`` of a criterion decision confirmed at a person's terminal
PERSON_CHANNELS = (TERMINAL, PM_GUI)


def is_human_item(text: str) -> bool:
    return text.strip().lower().startswith(HUMAN_PREFIX)


def human_criteria(node: dict) -> dict[str, str]:
    """``A#`` -> text of ``node``'s criteria that start with ``human:``."""
    items = [a for a in node.get("acceptance") or [] if isinstance(a, str) and a.strip()]
    return {aid: text for aid, text in zip(acceptance_ids(node), items) if is_human_item(text)}


def human_acceptance_ids(node: dict) -> list[str]:
    """The ``A#`` ids of ``node``'s criteria that start with ``human:``."""
    return list(human_criteria(node))


def undecided_human_items(root: Path, node: dict, integration_ref: str | None, head: str = "HEAD") -> list[str]:
    """The ``human:`` ids with no person's closed ledger entry at ``head`` or at ``integration_ref``."""
    human = human_acceptance_ids(node)
    if not human:
        return []
    decided: set[str] = set()
    for ref in (head, integration_ref):
        if not ref:
            continue
        for e in committed_yaml(root, ref, DECISIONS_REL.as_posix()).get("entries") or []:
            if isinstance(e, dict) and e.get("kind") == "human-action" and e.get("node") == node["id"] \
                    and e.get("status") == "closed" and e.get("decided_by") == OPERATOR \
                    and e.get("channel") in PERSON_CHANNELS:
                decided.add(str(e.get("criterion")))
    return [aid for aid in human if aid not in decided]


def human_acceptance_or_exit(root: Path, node: dict, integration_ref: str | None) -> None:
    """Stop ``finish-this-task`` while a ``human:`` item has no person's decision in the committed ledger."""
    missing = undecided_human_items(root, node, integration_ref)
    if not missing:
        return
    nid, first = node["id"], missing[0]
    where = "this branch or the integration branch" if integration_ref else "this branch"
    print(
        f"error: {nid} has human acceptance item(s) with no person's decision: {', '.join(missing)}.\n"
        "  Reviewers mark a `human:` item n/a; the person it names decides it in roadmap/decisions.yaml.\n"
        "  A planning-sheet `A#:` line no longer counts.\n"
        f"  Open one entry per item: specy-road decisions add {nid} --kind human-action --criterion {first} "
        "--summary ... --why ... --option ... --recommendation ... --recommendation-reason ... --default ...\n"
        "  A person then closes it: `specy-road decisions close <ID> --answer ...` in their own terminal, or the\n"
        f"  answer in the PM GUI's Status window. The closed entry must be committed on {where}; then run\n"
        "  finish-this-task again.",
        file=sys.stderr,
    )
    raise SystemExit(1)
