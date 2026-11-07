"""Per-leaf review tallies on gate commits, and per-area quality computed from them.

Every input is defined once here, from tracked data only, so every checkout and CI compute the same numbers for
the same ``HEAD``:

* **Tally.** ``mark-implementation-reviewed`` writes one ``Review-tally:`` trailer beside the ``Reviewed-by`` lines
  (:func:`tally_trailers`). Its rounds, blocks, findings and approvals come from the review history merged with the
  very records the passing gate counted (so an interactive human approval with no history copy is a round), plus
  test-integrity findings and RCA escalations.
* **Population.** A completed leaf is a **finish merge**: a ``Merge branch 'feature/rm-<codename>' into
  <integration branch>`` commit (as ``finish-this-task`` writes it, the branch named by ``roadmap/git-workflow.yaml``
  at ``HEAD``) on ``HEAD``'s first-parent history, which on the integration branch is that branch's own line. A
  merge reachable only through a side branch does not count, nor one a ``git revert`` reachable from ``HEAD``
  undid. Bookkeeping commits (``mark implementation reviewed``, ``complete, deregister``) and node status never
  decide it. The window is the last ``quality_window`` of them in first-parent order, newest first
  (:func:`completed_leaves`).
* **Zones.** The live graph's touch zones for the codename; for a leaf no longer live (archived), the graph as
  committed at its finish merge.
* **Tally.** The newest ``Review-tally`` trailer on the codename's gate commit among the commits its finish merge
  brought in (:func:`merge_tally`).
* **No tally.** A completed leaf whose gate commit carries no trailer (landed before it existed) counts as landed
  and is left out of every rate.
* **Unreadable.** A ``Review-tally: <id> unreadable`` trailer (the records could not be read) counts as landed,
  apart from no tally, and is left out of every rate. The digest shows that count on its own.
* **Policy.** ``quality_window``, ``quality_area_depth`` and ``quality_threshold`` are read from
  ``roadmap/orchestration.yaml`` as committed at ``HEAD`` (:func:`quality_policy`), never from a local overlay.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.runtime_paths import project_prefix, rebase_to_project

TRAILER = "Review-tally"
#: Second field of a trailer whose counts could not be read. Not a missing trailer.
UNREADABLE = "unreadable"
#: The subject ``finish-this-task`` gives the merge that lands a leaf (``finish_land_deterministic``).
_FINISH = re.compile(r"^Merge branch 'feature/rm-(?P<codename>[^']+)' into (?P<into>\S+)$")
_REVERTS = re.compile(r"^This reverts commit (?P<sha>[0-9a-f]{40})\b", re.M)
_GATE = "mark implementation reviewed"
_TALLY = re.compile(rf"^{TRAILER}: (?P<node>\S+) (?P<fields>.*)$")
_FIELD = re.compile(r"(?P<key>[a-z_]+)=(?P<value>\S*)")
_COUNTS = ("rounds", "blocks", "approvals", "integrity", "rca")


def _counted_rounds(repo_root: Path, gate: Any, history: list[Any]) -> dict[str, dict[str, Any]]:
    """``{commit: {model: record}}``: the history's rounds, with each record the gate counted put in its commit's
    round under its model (the same identity :func:`specy_road.review_rca.review_rounds` uses), so a live record with
    no history copy is still a round and one with a copy is not counted twice."""
    from specy_road.review_target import full_sha

    rounds = {rnd.commit: {r.data["model"]: r for r in rnd.records} for rnd in history}
    for counted in gate.approvals + gate.blocks:
        raw = counted.review.data["commit"]
        rounds.setdefault(full_sha(repo_root, raw) or raw, {})[counted.model] = counted.review
    return rounds


def leaf_tally(repo_root: Path, gate: Any) -> dict[str, Any]:
    """The leaf's review counts at its passing gate: rounds, blocking rounds, approvals the gate counted, findings
    per category, integrity findings and RCA escalations."""
    from specy_road.integrity import compare_integrity
    from specy_road.review_policy_ref import policy_source
    from specy_road.review_rca import loop_state

    loop = loop_state(repo_root, gate.node_id)
    rounds = list(_counted_rounds(repo_root, gate, loop.rounds).values())
    findings: Counter[str] = Counter()
    for records in rounds:
        for r in records.values():
            for category, items in (r.data.get("findings") or {}).items():
                findings[category] += len(items or [])
    ref = policy_source(repo_root)[0]
    base = git_text(["merge-base", ref, gate.commit], repo_root) if ref and gate.commit else None
    return {
        "rounds": len(rounds),
        "blocks": sum(1 for recs in rounds if any(r.data["verdict"] == "block" for r in recs.values())),
        "approvals": len(gate.approvals),
        "integrity": len(compare_integrity(repo_root, base, gate.commit)) if base else 0,
        "rca": sum(1 for r in loop.rcas if r.ok) + (loop.escalation is not None),
        "findings": {k: v for k, v in sorted(findings.items()) if v},
    }


def format_tally(node_id: str, tally: dict[str, Any]) -> str:
    found = ",".join(f"{k}:{v}" for k, v in sorted(tally["findings"].items())) or "none"
    return f"{TRAILER}: {node_id} " + " ".join(f"{k}={tally[k]}" for k in _COUNTS) + f" findings={found}"


def tally_trailers(repo_root: Path, gate: Any) -> list[str]:
    """The gate commit's ``Review-tally`` line for a passed :class:`~specy_road.review_gate.GateResult`.

    When the records cannot be read, one stderr line and an unreadable trailer; the gate still closes.
    """
    try:
        return [format_tally(gate.node_id, leaf_tally(repo_root, gate))]
    except Exception as exc:  # noqa: BLE001 - the tally is a record for the digest, never a reason to refuse the gate
        print(f"review tally: {type(exc).__name__}: {exc}; the leaf's quality numbers will be missing", file=sys.stderr)
        return [f"{TRAILER}: {gate.node_id} {UNREADABLE}"]


def parse_tally(line: str) -> tuple[str, dict[str, int] | str] | None:
    """``(node id, counts)`` from one trailer line, ``(node id, unreadable)`` when the counts could not be read,
    or ``None`` when it is not a well-formed tally."""
    m = _TALLY.match(line.strip())
    if not m:
        return None
    if m["fields"].strip() == UNREADABLE:
        return m["node"], UNREADABLE
    fields = {f["key"]: f["value"] for f in _FIELD.finditer(m["fields"])}
    if not all(fields.get(k, "").isdigit() for k in _COUNTS):
        return None
    return m["node"], {k: int(fields[k]) for k in _COUNTS}


def quality_policy(root: Path) -> dict[str, Any]:
    """The policy as committed at ``HEAD`` with defaults filled in; the defaults when it is absent or invalid there.
    Never the working tree or ``orchestration.local.yaml``: those differ between checkouts of the same ``HEAD``."""
    from specy_road.orchestration_config import DEFAULT_POLICY, load_orchestration_config

    data, err = load_orchestration_config(root, "HEAD")
    return {**DEFAULT_POLICY, **((data or {}).get("policy") or {} if not err else {})}


def _reverted(root: Path) -> set[str]:
    """Commits whose effect a ``git revert`` reachable from ``HEAD`` undid; a reverted revert restores its target."""
    out = git_stdout(["log", "--topo-order", "--format=%x1e%H%x1f%B", "--grep=This reverts commit", "HEAD"], root)
    undone: set[str] = set()
    for chunk in (out or "").split("\x1e")[1:]:   # newest first: a revert is always newer than what it reverts
        sha, _, body = chunk.partition("\x1f")
        m = _REVERTS.search(body)
        if m and sha not in undone:
            undone.add(m["sha"])
    return undone


def completed_leaves(root: Path) -> list[tuple[str, str]]:
    """``(codename, finish merge)`` per distinct codename, newest first, from ``HEAD``'s first-parent history into
    the integration branch named at ``HEAD``; a reverted merge is skipped. Empty when git cannot answer."""
    from specy_road.review_policy_ref import WORKFLOW_REL, committed_yaml

    into = str(committed_yaml(root, "HEAD", WORKFLOW_REL).get("integration_branch") or "main")
    # No pathspec: under one, --first-parent drops a merge that is TREESAME to its first parent under the project.
    out = git_stdout(["log", "--first-parent", "--format=%H%x1f%s", "--grep=^Merge branch 'feature/rm-", "HEAD"],
                     root)
    undone = _reverted(root)
    leaves: dict[str, str] = {}
    for line in (out or "").splitlines():
        sha, _, subject = line.partition("\x1f")
        m = _FINISH.match(subject)
        if m and m["into"] == into and sha not in undone and m["codename"] not in leaves:
            leaves[m["codename"]] = sha
    return list(leaves.items())


def merge_tally(root: Path, codename: str, merge: str) -> dict[str, int] | str | None:
    """The newest tally on ``codename``'s gate commit among the commits ``merge`` brought in.

    ``None`` when that commit carries no trailer; :data:`UNREADABLE` when the trailer says so.
    """
    subject = f"chore(rm-{codename}): {_GATE}"
    out = git_stdout(["log", "--topo-order", "--format=%x1e%B", "--fixed-strings", f"--grep={subject}",
                      f"{merge}^1..{merge}^2"], root)
    for body in (out or "").split("\x1e")[1:]:
        lines = body.strip().splitlines()
        if lines and lines[0] == subject:
            return next((t[1] for t in map(parse_tally, lines) if t), None)
    return None


def leaf_areas(zones: Iterable[Any] | None, depth: int, prefix: str = "") -> list[str]:
    """The distinct areas of ``zones``: the first ``depth`` path components, relative to the project root."""
    areas: list[str] = []
    for z in _project_zones(zones, prefix):
        area = "/".join(z.split("/")[: max(1, depth)])
        if area not in areas:
            areas.append(area)
    return sorted(areas)


def _project_zones(zones: Iterable[Any] | None, prefix: str) -> list[str]:
    out = []
    for z in zones or []:
        if isinstance(z, str) and z.strip().strip("/"):
            z = z.strip().strip("/")
            out.append(rebase_to_project(z, prefix) or z)
    return out


@dataclass
class AreaQuality:
    area: str
    leaves: int = 0
    no_tally: int = 0
    unreadable: int = 0
    rounds: int = 0
    blocked_leaves: int = 0
    integrity: int = 0
    rca: int = 0
    flagged: bool = False

    @property
    def tallied(self) -> int:
        return self.leaves - self.no_tally - self.unreadable

    @property
    def mean_rounds(self) -> float | None:
        return self.rounds / self.tallied if self.tallied else None

    @property
    def block_rate(self) -> float | None:
        """Share of the tallied leaves that had at least one blocking round."""
        return self.blocked_leaves / self.tallied if self.tallied else None


def _window(root: Path, nodes: list[dict[str, Any]], size: int) -> list[tuple[list[str], dict[str, int] | str | None]]:
    """The last ``size`` completed leaves with touch zones, newest first: ``(zones, tally or None)``."""
    from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref

    parents = {n.get("parent_id") for n in nodes}
    live = {n["codename"]: n for n in nodes if n.get("codename") and n.get("id") not in parents}
    out: list[tuple[list[str], dict[str, int] | None]] = []
    for codename, sha in completed_leaves(root):
        node = live.get(codename)
        if node is None:   # archived (or renamed) since: its zones as committed when it landed
            node = next((n for n in load_roadmap_nodes_at_ref(root, sha) or [] if n.get("codename") == codename), None)
        if node and node.get("touch_zones"):
            out.append((list(node["touch_zones"]), merge_tally(root, codename, sha)))
            if len(out) >= size:
                break
    return out


def area_quality(root: Path, nodes: list[dict[str, Any]]) -> list[AreaQuality]:
    """Per-area quality over the window, flagged areas first, then by name; empty only when no completed leaf with
    touch zones exists. Leaves with no tally, and leaves whose tally is unreadable, are counted as landed and left
    out of the rates."""
    policy = quality_policy(root)
    window = _window(root, nodes, int(policy["quality_window"]))
    depth, prefix = int(policy["quality_area_depth"]), project_prefix(root)
    areas: dict[str, AreaQuality] = {}
    for zones, counts in window:
        for name in leaf_areas(zones, depth, prefix):
            a = areas.setdefault(name, AreaQuality(name))
            a.leaves += 1
            if counts is None:
                a.no_tally += 1
                continue
            if counts == UNREADABLE:
                a.unreadable += 1
                continue
            a.rounds += counts["rounds"]
            a.blocked_leaves += counts["blocks"] > 0
            a.integrity += counts["integrity"]
            a.rca += counts["rca"]
    for a in areas.values():
        a.flagged = a.block_rate is not None and a.block_rate > float(policy["quality_threshold"])
    return sorted(areas.values(), key=lambda a: (not a.flagged, a.area))


def flagged_areas(root: Path, policy: dict[str, Any]) -> set[str]:
    """The flagged areas when ``policy.quality_routing`` is on; empty when it is off."""
    if not policy.get("quality_routing"):
        return set()
    from specy_road.bundled_scripts.roadmap_load import load_roadmap

    return {a.area for a in area_quality(root, load_roadmap(root)["nodes"]) if a.flagged}


def quality_review(policy: dict[str, Any], zones: Iterable[Any] | None, flagged: set[str],
                   prefix: str = "") -> tuple[list[dict[str, Any]], list[str]]:
    """``(strong_review items, notes)`` for one leaf in ``orchestrate plan``: each flagged area one of its zones
    falls in (the zone is the area or under it) wants one reviewer from the strong set (every ``require_one_of`` in
    ``policy.strong_review``); with no strong set there is no one to route to, so the plan says so instead."""
    zs = _project_zones(zones, prefix)
    hit = sorted(a for a in flagged if any(z == a or z.startswith(a + "/") for z in zs))
    strong = sorted({m for item in policy.get("strong_review") or [] for m in item.get("require_one_of") or []})
    if not strong:
        return [], [f"quality_routing: area {a} is flagged, but policy.strong_review names no reviewer to route to"
                    for a in hit]
    return [{"item": f"quality_routing (area: {a})", "require_one_of": strong} for a in hit], []
