"""What each roadmap node type is allowed to do.

Three facts about gates -- *never pickable*, *never a parent*, *only under a
vision, phase or milestone* -- were re-derived from the type string at sixteen
call sites across ten modules that are otherwise type-agnostic. They had already
drifted: ``validate_roadmap_gates`` accepted a gate under a milestone while
``roadmap_outline_renumber`` refused the same reparent, so the outline editor
rejected a shape ``specy-road validate`` considers correct.

Only graph semantics live here. How a gate's planning sheet or review prompt
differs is presentation, and stays with the modules that render it -- they just
ask :func:`is_gate` instead of each re-spelling the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GATE = "gate"

#: Types that may parent a gate. Also the answer ``validate`` enforces.
GATE_PARENT_TYPES = ("vision", "phase", "milestone")


@dataclass(frozen=True)
class NodeKind:
    """The capabilities of one node type."""

    name: str
    #: May ``do-next-available-task`` hand this to an implementer, if it is a leaf?
    pickable: bool
    #: May other nodes sit under it?
    allows_children: bool
    #: Types this node may sit under; ``None`` means no restriction.
    allowed_parents: tuple[str, ...] | None


_STRUCTURAL = {
    name: NodeKind(name, pickable=True, allows_children=True, allowed_parents=None)
    for name in ("vision", "phase", "milestone", "task")
}

NODE_KINDS: dict[str, NodeKind] = {
    **_STRUCTURAL,
    GATE: NodeKind(
        GATE,
        pickable=False,
        allows_children=False,
        allowed_parents=GATE_PARENT_TYPES,
    ),
}

#: Anything unrecognised behaves like an ordinary structural node, so a schema
#: addition degrades to "no special rules" rather than to a crash.
_DEFAULT = _STRUCTURAL["task"]


def normalize_type(node_type: Any) -> str:
    """A node's type as a comparable lowercase string."""
    return str(node_type or "").strip().lower()


def kind_of(node_type: Any) -> NodeKind:
    """The :class:`NodeKind` for a type string."""
    return NODE_KINDS.get(normalize_type(node_type), _DEFAULT)


def is_gate(node_type: Any) -> bool:
    """Whether ``node_type`` names a gate."""
    return normalize_type(node_type) == GATE


def is_pickable(node: dict[str, Any]) -> bool:
    """Whether a node may be handed to an implementer."""
    return kind_of(node.get("type")).pickable


def allows_children(node: dict[str, Any] | None) -> bool:
    """Whether ``node`` may parent other nodes."""
    return kind_of((node or {}).get("type")).allows_children


def parent_type_allowed(node_type: Any, parent_type: Any) -> bool:
    """Whether a node of ``node_type`` may sit under ``parent_type``."""
    allowed = kind_of(node_type).allowed_parents
    return allowed is None or normalize_type(parent_type) in allowed
