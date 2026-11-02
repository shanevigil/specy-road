"""Render a node's ``goal`` and numbered ``acceptance`` criteria for the brief.

Used by :mod:`generate_brief` to add ``### Goal`` and ``### Acceptance
criteria`` under section 1 (execution target). Each criterion gets a stable id
``A1..An`` in list order; review records cite those ids for their
per-criterion result, so the numbering must not depend on anything but the
node's own ``acceptance`` list.

Public surface:

* :func:`acceptance_ids` — ``["A1", ...]`` for one node.
* :func:`render_goal_and_acceptance` — markdown lines ready to drop into the brief.
* :func:`warn_acceptance_missing` — ``validate``'s warning for leaves a review
  cannot attest per criterion.
* :func:`warn_acceptance_merged` — ``validate``'s warning for a criterion that
  looks like several joined with ``|``.
* :func:`warn_unauthored` — ``validate``'s block for leaves pickup skips because
  their sheet is a placeholder and they have no acceptance.
* :func:`with_size_line`, :func:`size_warning`, :func:`print_size_warning` — the
  brief's size budget: a header line with its total bytes and three largest
  numbered sections, and the stderr warning past :data:`SIZE_WARN_BYTES`.
"""

from __future__ import annotations

import re
import sys

from specy_road.milestone_subtree import structural_leaf_ids
from specy_road.node_kinds import is_pickable

_WARN_CAP = 10   # per-leaf lines in warn_unauthored; the acceptance warnings are one line per class
SIZE_WARN_BYTES = 65536
_SECTION = re.compile(r"^## \d+\. ", re.MULTILINE)   # the brief's own numbered sections, not inlined sheets


def _acceptance(node: dict) -> list[str]:
    raw = node.get("acceptance") or []
    return [a for a in raw if isinstance(a, str) and a.strip()]


def acceptance_ids(node: dict) -> list[str]:
    """Stable ids for the node's acceptance criteria, in list order."""
    return [f"A{i}" for i in range(1, len(_acceptance(node)) + 1)]


def render_goal_and_acceptance(node: dict) -> list[str]:
    goal = (node.get("goal") or "").strip()
    out = ["### Goal", "", goal if goal else "_(no `goal` set on this node)_", ""]
    out += ["### Acceptance criteria", ""]
    items = _acceptance(node)
    if not items:
        out.append(
            "_(no `acceptance` set on this node — reviewers judge against the "
            "planning sheet instead)_"
        )
    for aid, text in zip(acceptance_ids(node), items):
        out.append(f"- **{aid}:** {text.strip()}")
    out.append("")
    return out


def warn_acceptance_missing(nodes: list[dict], gate_on: bool) -> None:
    """Warn (stderr only) on open actionable leaves without ``acceptance`` while the gate is on.

    Their review records need no per-criterion result, so a review attests
    nothing criterion by criterion. Without the gate the field is optional.
    """
    if not gate_on:
        return
    leaves = structural_leaf_ids(nodes)
    bare = [n["id"] for n in nodes
            if n.get("id") in leaves and is_pickable(n)
            and n.get("status") != "Complete" and not _acceptance(n)]
    if not bare:
        return
    print(f"warning: each of {len(bare)} open leaf/leaves ({', '.join(bare)}) has no acceptance criteria; with "
          "require_implementation_review_before_finish on, a review of it cannot attest per-criterion results",
          file=sys.stderr)
    print("  fix each with: specy-road edit-node <NODE_ID> --set acceptance=..., one --set per criterion",
          file=sys.stderr)


def warn_acceptance_merged(nodes: list[dict]) -> None:
    """Warn (stderr only) on an open node whose criterion contains ``|``.

    ``edit-node --set acceptance=a|b`` stores one criterion, and a review then
    attests ``A1`` for both. 0.3.1rc1 adopters wrote lists that way because
    nothing said otherwise.
    """
    merged = [n["id"] for n in nodes
              if n.get("status") != "Complete" and any("|" in a for a in _acceptance(n))]
    if not merged:
        return
    print(f"warning: {len(merged)} open node(s) have an acceptance criterion containing '|' "
          f"({', '.join(merged)}); if that is several criteria, re-set them with one --set per criterion",
          file=sys.stderr)
    print("  fix each with: specy-road edit-node <NODE_ID> --set acceptance='First' --set acceptance='Second'",
          file=sys.stderr)


def warn_unauthored(unauthored: dict[str, str], *, show_all: bool = False) -> None:
    """Warn (stderr only), in one block, on the leaves pickup skips as unauthored.

    ``unauthored`` maps node id to ``planning_sheet_bootstrap.placeholder_sheet``'s
    reason. Capped like the acceptance warning; ``show_all`` (``validate --all``)
    lists every one.
    """
    if not unauthored:
        return
    items = list(unauthored.items())
    shown = items if show_all else items[:_WARN_CAP]
    print(f"warning: {len(items)} open leaf/leaves have a placeholder planning sheet and no acceptance criteria; "
          "do-next-available-task and grind-session skip them until the sheet is written or acceptance is set "
          "(--allow-unauthored picks them anyway):", file=sys.stderr)
    for nid, reason in shown:
        print(f"  {nid}: {reason}", file=sys.stderr)
    if len(items) > len(shown):
        print(f"  … and {len(items) - len(shown)} more (specy-road validate --all lists every one)", file=sys.stderr)


def section_sizes(text: str) -> list[tuple[str, int]]:
    """``(heading, bytes)`` per numbered ``## N.`` section of a rendered brief, largest first."""
    starts = [m.start() for m in _SECTION.finditer(text)] + [len(text)]
    blocks = [text[a:b] for a, b in zip(starts, starts[1:])]
    sizes = [(b.split("\n", 1)[0].strip(), len(b.encode("utf-8"))) for b in blocks]
    return sorted(sizes, key=lambda hs: (-hs[1], hs[0]))


def _size_line(total: int, largest: list[tuple[str, int]]) -> str:
    top = "; ".join(f"`{h}` {n} B" for h, n in largest[:3]) or "none"
    return f"_Size: {total} bytes. Largest sections: {top}._"


def with_size_line(header: list[str], body: list[str]) -> str:
    """The brief: ``header`` lines, the size line, then ``body``; the total counts the line itself."""
    largest = section_sizes("\n".join(body))
    rest = "\n".join(body).rstrip() + "\n"
    base = len(("\n".join(header) + "\n").encode("utf-8")) + len(rest.encode("utf-8")) + 2   # + "\n\n"
    total = base
    while True:   # the line's own length depends on the number it prints
        line = _size_line(total, largest)
        if total == base + len(line.encode("utf-8")):
            return "\n".join(header) + "\n" + line + "\n\n" + rest
        total = base + len(line.encode("utf-8"))


def size_warning(text: str) -> str | None:
    """Warning text for a brief over :data:`SIZE_WARN_BYTES`, naming the largest sections, else None."""
    total = len(text.encode("utf-8"))
    if total <= SIZE_WARN_BYTES:
        return None
    top = ", ".join(f"`{h}` ({n} B)" for h, n in section_sizes(text)[:3])
    return (f"warning: brief is {total} bytes (over {SIZE_WARN_BYTES}); largest sections: {top}. "
            "Trim the planning sheets or cite fewer contracts to keep it cacheable.")


def print_size_warning(text: str) -> None:
    """``specy-road brief``: the size warning on stderr, when there is one."""
    warning = size_warning(text)
    if warning:
        print(warning, file=sys.stderr)
