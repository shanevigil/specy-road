"""Per-leaf review tallies on gate commits, and per-area quality computed from them.

``mark-implementation-reviewed`` writes one ``Review-tally:`` trailer beside the ``Reviewed-by`` lines
(:func:`tally_trailers`): the leaf's review rounds, rounds with a block, findings per category, test-integrity
findings and RCA escalations, read from the gitignored ``work/reviews/<ID>/`` records at that moment. The digest's
"Quality by area" section and ``policy.quality_routing`` read **only** those trailers from tracked git history
(:func:`area_quality`), so every checkout and CI compute the same numbers for the same HEAD. A gate commit without
the trailer (landed before it existed) counts as a leaf with no tally and is left out of the rates.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.runtime_paths import project_prefix, rebase_to_project

TRAILER = "Review-tally"
#: The subject ``mark-implementation-reviewed`` gives a leaf's gate commit.
_GATE_SUBJECT = re.compile(r"^chore\(rm-(?P<codename>[^)\s]+)\): mark implementation reviewed$")
_TALLY = re.compile(rf"^{TRAILER}: (?P<node>\S+) (?P<fields>.*)$")
_FIELD = re.compile(r"(?P<key>[a-z_]+)=(?P<value>\S*)")
_COUNTS = ("rounds", "blocks", "integrity", "rca")


def leaf_tally(repo_root: Path, node_id: str, commit: str | None) -> dict[str, Any]:
    """The leaf's review record counts now: rounds, blocking rounds, findings per category, integrity, RCA."""
    from specy_road.integrity import compare_integrity
    from specy_road.review_policy_ref import policy_source
    from specy_road.review_rca import loop_state

    loop = loop_state(repo_root, node_id)
    findings: Counter[str] = Counter()
    for rnd in loop.rounds:
        for r in rnd.records:
            for category, items in (r.data.get("findings") or {}).items():
                findings[category] += len(items or [])
    ref = policy_source(repo_root)[0]
    base = git_text(["merge-base", ref, commit], repo_root) if ref and commit else None
    return {
        "rounds": len(loop.rounds),
        "blocks": sum(1 for rnd in loop.rounds if any(r.data["verdict"] == "block" for r in rnd.records)),
        "integrity": len(compare_integrity(repo_root, base, commit)) if base else 0,
        "rca": sum(1 for r in loop.rcas if r.ok) + (loop.escalation is not None),
        "findings": {k: v for k, v in sorted(findings.items()) if v},
    }


def format_tally(node_id: str, tally: dict[str, Any]) -> str:
    found = ",".join(f"{k}:{v}" for k, v in sorted(tally["findings"].items())) or "none"
    return f"{TRAILER}: {node_id} " + " ".join(f"{k}={tally[k]}" for k in _COUNTS) + f" findings={found}"


def tally_trailers(repo_root: Path, gate: Any) -> list[str]:
    """The gate commit's ``Review-tally`` line for a passed :class:`~specy_road.review_gate.GateResult`; none when
    the records cannot be read (the leaf then counts as no tally)."""
    try:
        return [format_tally(gate.node_id, leaf_tally(repo_root, gate.node_id, gate.commit))]
    except Exception:  # noqa: BLE001 - the tally is a record for the digest, never a reason to refuse the gate
        return []


def parse_tally(line: str) -> tuple[str, dict[str, int]] | None:
    """``(node id, counts)`` from one trailer line, or ``None`` when it is not a well-formed tally."""
    m = _TALLY.match(line.strip())
    if not m:
        return None
    fields = {f["key"]: f["value"] for f in _FIELD.finditer(m["fields"])}
    if not all(fields.get(k, "").isdigit() for k in _COUNTS):
        return None
    return m["node"], {k: int(fields[k]) for k in _COUNTS}


def gate_history(root: Path) -> list[tuple[str, str, dict[str, int] | None]]:
    """Newest-first ``(kind, key, counts)`` per gate commit touching ``root``: ``("id", node id, counts)`` for a
    tallied one, ``("codename", codename, None)`` for one without a tally. Empty when git cannot answer."""
    out = git_stdout(["log", "--topo-order", "--format=%x1e%B", f"--grep={TRAILER}:",
                      "--grep=mark implementation reviewed", "--", "."], root) or ""
    rows: list[tuple[str, str, dict[str, int] | None]] = []
    for body in out.split("\x1e")[1:]:
        lines = body.strip().splitlines()
        tally = next((t for t in map(parse_tally, lines) if t), None)
        subject = _GATE_SUBJECT.match(lines[0]) if lines else None
        if tally:
            rows.append(("id", tally[0], tally[1]))
        elif subject:
            rows.append(("codename", subject["codename"], None))
    return rows


def leaf_areas(zones: Iterable[Any] | None, depth: int, prefix: str = "") -> list[str]:
    """The distinct areas of ``zones``: the first ``depth`` path components, relative to the project root."""
    areas: list[str] = []
    for z in zones or []:
        if not isinstance(z, str) or not z.strip().strip("/"):
            continue
        z = z.strip().strip("/")
        parts = (rebase_to_project(z, prefix) or z).split("/")
        area = "/".join(parts[: max(1, depth)])
        if area not in areas:
            areas.append(area)
    return sorted(areas)


@dataclass
class AreaQuality:
    area: str
    leaves: int = 0
    no_tally: int = 0
    rounds: int = 0
    blocked_leaves: int = 0
    integrity: int = 0
    rca: int = 0
    flagged: bool = False

    @property
    def tallied(self) -> int:
        return self.leaves - self.no_tally

    @property
    def mean_rounds(self) -> float | None:
        return self.rounds / self.tallied if self.tallied else None

    @property
    def block_rate(self) -> float | None:
        """Share of the tallied leaves that had at least one blocking round."""
        return self.blocked_leaves / self.tallied if self.tallied else None


def _window(root: Path, nodes: list[dict[str, Any]], size: int) -> list[tuple[dict[str, Any], dict[str, int] | None]]:
    """The last ``size`` distinct landed leaves with touch zones, newest first, with their tally (or ``None``)."""
    parents = {n.get("parent_id") for n in nodes}
    leaves = [n for n in nodes if n.get("id") not in parents and n.get("touch_zones")]
    by = {"id": {n["id"]: n for n in leaves}, "codename": {n.get("codename"): n for n in leaves if n.get("codename")}}
    seen: set[str] = set()
    out: list[tuple[dict[str, Any], dict[str, int] | None]] = []
    for kind, key, counts in gate_history(root):
        node = by[kind].get(key)
        if node is None or node["id"] in seen:
            continue
        seen.add(node["id"])
        out.append((node, counts))
        if len(out) >= size:
            break
    return out


def area_quality(root: Path, nodes: list[dict[str, Any]], policy: dict[str, Any]) -> list[AreaQuality]:
    """Per-area quality over the policy's window, flagged areas first, then by name; empty when no leaf in the
    window has a tally (a history with only pre-tally gate commits has nothing to rate)."""
    window = _window(root, nodes, int(policy.get("quality_window") or 50))
    if not any(counts for _, counts in window):
        return []
    depth, prefix = int(policy.get("quality_area_depth") or 1), project_prefix(root)
    threshold = float(policy.get("quality_threshold", 0.5))
    areas: dict[str, AreaQuality] = {}
    for node, counts in window:
        for name in leaf_areas(node.get("touch_zones"), depth, prefix):
            a = areas.setdefault(name, AreaQuality(name))
            a.leaves += 1
            if counts is None:
                a.no_tally += 1
                continue
            a.rounds += counts["rounds"]
            a.blocked_leaves += counts["blocks"] > 0
            a.integrity += counts["integrity"]
            a.rca += counts["rca"]
    for a in areas.values():
        a.flagged = a.block_rate is not None and a.block_rate > threshold
    return sorted(areas.values(), key=lambda a: (not a.flagged, a.area))


def flagged_areas(root: Path, nodes: list[dict[str, Any]], policy: dict[str, Any]) -> set[str]:
    """The flagged areas when ``policy.quality_routing`` is on; empty when it is off."""
    if not policy.get("quality_routing"):
        return set()
    return {a.area for a in area_quality(root, nodes, policy) if a.flagged}


def quality_review(policy: dict[str, Any], zones: Iterable[Any] | None, flagged: set[str],
                   prefix: str = "") -> tuple[list[dict[str, Any]], list[str]]:
    """``(strong_review items, notes)`` for one leaf in ``orchestrate plan``: each flagged area its zones fall in
    wants one reviewer from the strong set (every ``require_one_of`` in ``policy.strong_review``); with no strong
    set there is no one to route to, so the plan says so instead."""
    hit = [a for a in leaf_areas(zones, int(policy.get("quality_area_depth") or 1), prefix) if a in flagged]
    strong = sorted({m for item in policy.get("strong_review") or [] for m in item.get("require_one_of") or []})
    if not strong:
        return [], [f"quality_routing: area {a} is flagged, but policy.strong_review names no reviewer to route to"
                    for a in hit]
    return [{"item": f"quality_routing (area: {a})", "require_one_of": strong} for a in hit], []
