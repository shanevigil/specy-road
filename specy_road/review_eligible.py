"""Who on the roster can still supply a counting approval: the lines ``handoff status`` prints under the policy.

When the gate is not met, a coordinator needs more than ``1/2 ... not met``: which roster entries may still
approve at this commit (the human included), and why each of the others cannot. Each roster entry is judged
with the gate's own checks (:mod:`specy_road.review_gate`), plus who wrote the change, taken from the leaf's
READY files as ``review_rca.rca_parties`` does:

* not a reviewer role — no ``reviewer`` role and no active substitution covering the node;
* the node's sensitivity is outside its roster ``may_process``;
* executor of the leaf — it filed a READY before any valid review of its own on the leaf;
* wrote a fix commit on this leaf — it filed a READY after reviewing the leaf;
* rejected record — its record at this commit is invalid or does not count, with the gate's reason;
* same family as an approval already counted, under ``reviewers_distinct_families`` (not when its approval would
  satisfy an unmet ``policy.strong_review`` item, which counts whatever the family);
* ``signed_reviews`` is on and its roster entry has no ``public_key``;
* unavailable — ``available: false`` or a ``paused_until`` / ``unavailable_until`` still in force
  (skipped when that model's approval already counts at this commit).

Every exclusion is checked first, so a model whose approval the gate counts is listed as counting only when none
applies (a READY author never is); one that blocks may still approve on re-review. While a ``policy.strong_review``
item is unmet, each row that can approve says whether its approval would satisfy it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.orchestrate_plan import (
    entry_may_process,
    is_available,
    may_handle,
    node_sensitivity,
    unavailability_reason,
)
from specy_road.orchestration_config import is_rostered_reviewer, substitute_for
from specy_road.review_files import HUMAN, list_ready, list_review_history, list_reviews
from specy_road.review_strong import item_label
from specy_road.review_target import same_commit


def _writers(repo_root: Path, node_id: str, branch: str | None) -> dict[str, str]:
    """Model -> why it wrote part of the change: a READY written after the model's first valid review on the leaf
    is a fix; any other READY is the executor's (an executor that also files an approval stays the executor).
    Filing times are file mtimes: ``history/`` copies are written once. A self-review (``authored_fix``) is invalid."""
    first: dict[str, float] = {}
    for r in list_review_history(repo_root, node_id) + list_reviews(repo_root, node_id):
        if r.ok and (r.on_disk or r.path).is_file():
            t = (r.on_disk or r.path).stat().st_mtime
            first[r.data["model"]] = min(t, first.get(r.data["model"], t))
    out: dict[str, str] = {}
    for r in list_ready(repo_root, node_id, branch):
        agent = str(r.data.get("agent")) if r.ok else None
        if agent and agent not in out:
            fix = agent in first and r.path.stat().st_mtime > first[agent]
            out[agent] = (f"wrote a fix commit on this leaf ({r.path.name})" if fix
                          else f"executor of the leaf ({r.path.name})")
    return out


def _rejected(repo_root: Path, gate: Any) -> dict[str, str]:
    """Model -> why its record at the commit under review does not count (invalid or ineligible)."""
    counted = {c.model for c in gate.approvals + gate.blocks}
    out: dict[str, str] = {}
    for r in gate.invalid:
        if r.data.get("model") and (not r.data.get("commit") or same_commit(repo_root, r.data["commit"], gate.commit)):
            out.setdefault(str(r.data["model"]), f"rejected record {r.path.name}: {'; '.join(r.errors)}")
    for r, why in gate.ineligible:
        if r.data["model"] not in counted:
            out.setdefault(r.data["model"], f"rejected record {r.path.name}: {why}")
    return out


def _roster_reason(config: dict[str, Any], node: dict[str, Any], model: str,
                   counting: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Why the roster itself keeps ``model`` from reviewing ``node``, else ``None``."""
    entry = next(e for e in config["roster"] if e.get("id") == model)
    if not is_rostered_reviewer(config, model) and substitute_for(config, node["id"], model) is None:
        return f"not a reviewer role (roles: {', '.join(entry.get('roles') or []) or 'none'}) and no active substitution"
    if not may_handle(entry, node_sensitivity(node)):
        return f"{node['id']} is {node_sensitivity(node)!r}; it may process only {entry_may_process(entry)}"
    if config["policy"].get("signed_reviews") and not entry.get("public_key"):
        return "policy requires signed reviews and its roster entry has no public_key"
    if model not in counting and not is_available(entry):
        return f"unavailable ({unavailability_reason(entry) or 'availability'})"
    return None


def _same_family(gate: Any, model: str, family: str | None) -> str | None:
    """A counted approval of the family from another model; for a counted model, only an earlier one, since
    the gate counts the family once."""
    if not gate.distinct_families:
        return None
    mine = next((i for i, a in enumerate(gate.approvals) if a.model == model), len(gate.approvals))
    other = next((a for a in gate.approvals[:mine] if a.family == family), None)
    return f"same family ({family}) as {other.model}'s approval, which already counts" if other else None


def _eligible_text(gate: Any, node_id: str, model: str) -> str:
    if any(b.model == model for b in gate.blocks):
        return "can approve on re-review (its record blocks this commit)"
    key = " --sign-key <your private key>" if (gate.config.get("policy") or {}).get("signed_reviews") else ""
    if model == HUMAN:
        return f"can approve, interactively with `specy-road mark-implementation-reviewed {node_id}{key}`"
    return (f"can approve (file a signed record: `specy-road review record{key}`)" if key
            else "can approve (file with `specy-road review record`)")


def reviewer_eligibility(repo_root: Path, node: dict[str, Any], gate: Any, branch: str | None) -> list[dict[str, Any]]:
    """One row per roster entry while the gate is not met: ``model``, ``family``, ``eligible`` and ``reason``."""
    if gate.passed or gate.config_error or gate.commit is None:
        return []
    config, writers, rejected = gate.config, _writers(repo_root, node["id"], branch), _rejected(repo_root, gate)
    counting = {a.model for a in gate.approvals}
    rows = []
    for entry in config["roster"]:
        model, family = entry["id"], entry.get("family")
        # Every exclusion first: an author or a second same-family approval never reads as counting.
        why = (_roster_reason(config, node, model, counting=counting) or writers.get(model) or rejected.get(model)
               or (None if _meets_strong(gate, model) else _same_family(gate, model, family)))
        ok = "its approval counts" if model in counting else _eligible_text(gate, node["id"], model)
        if why is None and model in counting and not is_available(entry):
            ok = "its approval counts; unavailable for new reviews"
        elif why is None and model not in counting:
            ok += _strong_text(gate, model)
        rows.append({"model": model, "family": family, "eligible": why is None, "reason": why or ok})
    return rows


def _meets_strong(gate: Any, model: str) -> bool:
    return any(model in item["require_one_of"] for _, item in gate.strong_unmet)


def _strong_text(gate: Any, model: str) -> str:
    """Which unmet ``strong_review`` items an approval from ``model`` would satisfy, and which not."""
    if not gate.strong_unmet:
        return ""
    meets = [item_label(i, item) for i, item in gate.strong_unmet if model in item["require_one_of"]]
    misses = [item_label(i, item) for i, item in gate.strong_unmet if model not in item["require_one_of"]]
    return ((f"; would satisfy {', '.join(meets)}" if meets else "")
            + (f"; would not satisfy {', '.join(misses)}" if misses else ""))


def eligibility_lines(st: dict[str, Any]) -> list[str]:
    """``handoff status`` text: the rows of :func:`reviewer_eligibility`, under the policy line."""
    rows = st.get("reviewer_eligibility") or []
    head = ["  who can still supply a counting approval at this commit:"] if rows else []
    return head + [f"    {r['model']} ({r['family']}): {'' if r['eligible'] else 'excluded — '}{r['reason']}"
                   for r in rows]
