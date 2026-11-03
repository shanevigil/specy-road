"""``policy.strong_review``: a leaf that touches a high-risk zone needs one approval from a named set of reviewers.

Each item names ``zones`` (touch-zone paths or directory prefixes) and ``require_one_of`` (roster ids). An item
applies to a leaf when one of the leaf's touch zones meets one of its zones: the same path, one a directory
prefix of the other, or a glob zone matching the other (:func:`finish_implementation_check.zone_matches`, the
rule the review packet uses, tried in both directions as the picker's zone clash is). In a nested project
either zone may be written from the git root or from the project root, so both forms are tried.

The review gate refuses while an applicable item has no counting approval (one the gate already counts:
eligible, at the commit under review) from a model it lists; ``orchestrate plan`` shows each ready leaf's items
and who can satisfy them. A substitute satisfies an item only when its own id is listed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from specy_road.finish_implementation_check import zone_matches
from specy_road.review_files import HUMAN
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import project_prefix, rebase_to_project


def _clean(zones: Iterable[Any] | None) -> list[str]:
    return [z.strip().strip("/") for z in zones or [] if isinstance(z, str) and z.strip().strip("/")]


def touch_zones(repo_root: Path, node: dict[str, Any]) -> tuple[list[str], list[str]]:
    """``(the registry claim's touch zones, the node's own)``, each cleaned of blanks and edge slashes."""
    entry = next((e for e in read_registry(registry_path(repo_root)).get("entries") or []
                  if e.get("node_id") == node["id"]), None) or {}
    return _clean(entry.get("touch_zones")), _clean(node.get("touch_zones"))


def _forms(zone: str, prefix: str) -> set[str]:
    zone = zone.strip().strip("/")
    return {zone, rebase_to_project(zone, prefix) or zone, f"{prefix}{zone}"}


def zones_meet(a: str, b: str, prefix: str = "") -> bool:
    """Whether zones ``a`` and ``b`` share a path, in either root's form (``prefix``: :func:`project_prefix`)."""
    return any(zone_matches(x, y) or zone_matches(y, x) for x in _forms(a, prefix) for y in _forms(b, prefix))


def applicable_items(policy: dict[str, Any], zones: Iterable[Any] | None, prefix: str = "") -> list[tuple[int, dict[str, Any]]]:
    """``(index, item)`` for every ``strong_review`` item one of ``zones`` meets."""
    return [(i, item) for i, item in enumerate(policy.get("strong_review") or [])
            if any(zones_meet(z, iz, prefix) for z in _clean(zones) for iz in _clean(item.get("zones")))]


def item_label(index: int, item: dict[str, Any]) -> str:
    return f"strong_review[{index}] (zones: {', '.join(item.get('zones') or [])})"


def unmet_strong(repo_root: Path, node: dict[str, Any], policy: dict[str, Any],
                 approvals: list[Any]) -> list[tuple[int, dict[str, Any]]]:
    """The items that apply to ``node`` and that no counted approval in ``approvals`` satisfies."""
    if not policy.get("strong_review"):
        return []
    claim, own = touch_zones(repo_root, node)
    models = {a.model for a in approvals}
    items = applicable_items(policy, list(dict.fromkeys(claim + own)), project_prefix(repo_root))
    return [(i, item) for i, item in items if not models & set(item["require_one_of"])]


def strong_problem(index: int, item: dict[str, Any]) -> str:
    """The gate's refusal line for an unmet item."""
    return (f"{item_label(index, item)}: the leaf's touch zones meet a strong-review zone; need a counting approval "
            f"from one of {', '.join(item['require_one_of'])} at this commit, have none")


def human_closes_strong(gate: Any) -> bool:
    """Whether a human approval would satisfy every unmet item of ``gate``: each one lists the human."""
    return all(HUMAN in item["require_one_of"] for _, item in gate.strong_unmet)
