"""The fix-round budget and the deferral of new-input-class findings to a follow-up leaf.

``policy.max_fix_rounds`` (unset: no budget) caps the blocking review rounds one
leaf may spend; once spent, ``handoff status`` reports ``fix_round_budget_spent``
and names the next command (:func:`fix_round_budget`). An RCA record of type
``defer_findings`` proposes moving findings whose **input class** is new to a
follow-up leaf; :func:`deferral_problems` is the rule that refuses one, and a
human applies the rest with ``specy-road review defer``, which leaves a
``DEFERRAL-<round>.yaml`` marker beside the RCA record. The gate then treats the
deferring reviewer's block at that commit as resolved, and nothing else
(:func:`apply_deferrals`). Design: ``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from specy_road.decisions import decisions_path, read_decisions
from specy_road.review_files import RCA_PREFIX, ReviewFile, reviews_dir
from specy_road.review_target import same_commit

if TYPE_CHECKING:   # review_gate imports this module
    from specy_road.review_gate import GateResult
    from specy_road.review_rca import LoopState, Round

DEFERRAL_PREFIX = "DEFERRAL-"


def normalise_input_class(text: str) -> str:
    """Two input classes match when equal after lower-casing and collapsing whitespace (no fuzzy match)."""
    return " ".join(str(text).lower().split())


def _round_of(rounds: list[Round], commit: str) -> int | None:
    commit = str(commit)
    return next((i for i, rnd in enumerate(rounds)
                 if rnd.commit.startswith(commit) or commit.startswith(rnd.commit)), None)


def deferral_problems(rounds: list[Round], rcas: list[ReviewFile], applied: list[tuple[str, dict[str, Any]]],
                      item: dict[str, Any]) -> list[str]:
    """Why one ``deferred_findings`` item may never be deferred; empty when it may.

    ``rcas`` are the leaf's other RCA records and ``applied`` its applied deferrals as ``(file name, marker)``.
    Each problem names the record or round it collides with.
    """
    who = f"{item['reviewer']} @ {str(item['commit'])[:12]}"
    out: list[str] = []
    cls = normalise_input_class(item["input_class"])
    named = [(r.path.name, x.get("input_class")) for r in rcas if r.ok
             for x in (r.data.get("deferred_findings") or [])
             + ((r.data.get("criterion_rewrite") or {}).get("finding_disposition") or [])]
    named += [(name, x.get("input_class")) for name, m in applied for x in m.get("deferred") or []]
    hit = next((name for name, other in named if other and normalise_input_class(other) == cls), None)
    if hit:
        out.append(f"{who}: input class {item['input_class']!r} was already named in {hit}; it is not new")
    idx = _round_of(rounds, item["commit"])
    if idx is None or not any(r.data["model"] == item["reviewer"] and r.data["verdict"] == "block"
                              for r in rounds[idx].records):
        return out + [f"{who}: no blocking record from {item['reviewer']} at that commit in the review history"]
    if item["category"] == "correctness":
        for i, rnd in enumerate(rounds[:idx], 1):
            passed = [r.data["model"] for r in rnd.records
                      if (r.data.get("acceptance") or {}).get(item["acceptance_id"]) == "pass"]
            if passed:
                out.append(f"{who}: a correctness finding on {item['acceptance_id']}, which round {i} "
                           f"({', '.join(passed)}) marked pass")
                break
    return out


def marker_path(repo_root: Path, node_id: str, rca_name: str) -> Path:
    """``DEFERRAL-<round>.yaml`` beside ``RCA-<round>.md`` (gitignored, like the records it qualifies)."""
    return reviews_dir(repo_root, node_id) / f"{DEFERRAL_PREFIX}{Path(rca_name).stem.removeprefix(RCA_PREFIX)}.yaml"


def list_applied(repo_root: Path, node_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Every applied deferral marker of the leaf as ``(file name, data)``; an unreadable one is skipped."""
    d = reviews_dir(repo_root, node_id)
    out = []
    for p in sorted(d.glob(f"{DEFERRAL_PREFIX}*.yaml")) if d.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("node_id") == node_id:
            out.append((p.name, data))
    return out


def write_marker(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def deferred_by(repo_root: Path, node_id: str, model: str, commit: str) -> str | None:
    """The closed decision that deferred ``model``'s block at ``commit``, else ``None``."""
    closed = {e.get("id") for e in read_decisions(decisions_path(repo_root)).get("entries") or []
              if isinstance(e, dict) and e.get("status") == "closed" and e.get("node") == node_id}
    for _name, m in list_applied(repo_root, node_id):
        if m.get("decision") in closed and any(
                x.get("reviewer") == model and same_commit(repo_root, str(x.get("commit")), commit)
                for x in m.get("deferred") or []):
            return str(m["decision"])
    return None


def apply_deferrals(repo_root: Path, result: GateResult) -> None:
    """Move each counted block an applied, closed deferral names (reviewer and commit) to ``ineligible``."""
    for b in list(result.blocks):
        decision = deferred_by(repo_root, result.node_id, b.model, b.review.data["commit"])
        if decision:
            result.blocks.remove(b)
            result.ineligible.append((b.review, f"deferred by {decision}"))


def fix_round_budget(policy: dict[str, Any], loop: LoopState, node_id: str) -> dict[str, Any] | None:
    """``None`` when ``policy.max_fix_rounds`` is unset; else the blocking rounds, whether the budget is
    spent, and the command that resolves it: the RCA when none covers the latest round, else the deferral."""
    budget = policy.get("max_fix_rounds")
    if budget is None:
        return None
    blocking = sum(1 for rnd in loop.rounds if any(r.data["verdict"] == "block" for r in rnd.records))
    covering = [r for r in loop.rcas if r.ok and int(r.data["trigger"]["round"]) >= len(loop.rounds)]
    if not covering:
        nxt = (f"specy-road prompt {node_id} --role rca --force --reason \"fix-round budget spent\" "
               "--model <reviewer that has not reviewed it>")
    elif covering[-1].data["recommended_action"]["type"] == "defer_findings":
        nxt = f"specy-road review defer {node_id} --rca {covering[-1].path}"
    else:
        nxt = f"specy-road review list {node_id} ({covering[-1].path.name} recommends " \
              f"{covering[-1].data['recommended_action']['type']})"
    return {"max_fix_rounds": int(budget), "blocking_rounds": blocking, "spent": blocking >= int(budget), "next": nxt}
