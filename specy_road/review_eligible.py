"""Who on the roster can still supply a counting approval: the lines ``handoff status`` prints under the policy.

When the gate is not met, a coordinator needs more than ``1/2 ... not met``: which roster entries may still
approve at this commit (the human included), and why each of the others cannot. Each roster entry is judged
with the gate's own checks (:mod:`specy_road.review_gate`), plus who wrote the change, taken from the leaf's
READY files as ``review_rca.rca_parties`` does:

* not a reviewer role — no ``reviewer`` role and no active substitution covering the node;
* the node's sensitivity is outside its roster ``may_process``;
* executor of the leaf — it filed a READY and has no valid review on the leaf;
* wrote a fix commit on this leaf — it filed a READY after reviewing the leaf;
* rejected record — its record at this commit is invalid or does not count, with the gate's reason;
* same family as an approval already counted, under ``reviewers_distinct_families``;
* ``signed_reviews`` is on and its roster entry has no ``public_key``.

A model whose approval already counts is listed as counting; one that blocks may still approve on re-review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.orchestrate_plan import entry_may_process, may_handle, node_sensitivity
from specy_road.orchestration_config import is_rostered_reviewer, substitute_for
from specy_road.review_files import HUMAN, list_ready, list_review_history, list_reviews
from specy_road.review_target import same_commit


def _writers(repo_root: Path, node_id: str, branch: str | None) -> dict[str, str]:
    """Model -> why it wrote part of the change: a READY from a model with no valid review on the leaf is the
    executor's; one from a model that has reviewed the leaf is a fix. A self-review (``authored_fix``) is invalid."""
    reviewed = {r.data.get("model") for r in list_review_history(repo_root, node_id) + list_reviews(repo_root, node_id)
                if r.ok}
    out: dict[str, str] = {}
    for r in list_ready(repo_root, node_id, branch):
        agent = str(r.data.get("agent")) if r.ok else None
        if agent and agent not in out:
            out[agent] = (f"wrote a fix commit on this leaf ({r.path.name})" if agent in reviewed
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


def _roster_reason(config: dict[str, Any], node: dict[str, Any], model: str) -> str | None:
    """Why the roster itself keeps ``model`` from reviewing ``node``, else ``None``."""
    entry = next(e for e in config["roster"] if e.get("id") == model)
    if not is_rostered_reviewer(config, model) and substitute_for(config, node["id"], model) is None:
        return f"not a reviewer role (roles: {', '.join(entry.get('roles') or []) or 'none'}) and no active substitution"
    if not may_handle(entry, node_sensitivity(node)):
        return f"{node['id']} is {node_sensitivity(node)!r}; it may process only {entry_may_process(entry)}"
    if config["policy"].get("signed_reviews") and not entry.get("public_key"):
        return "policy requires signed reviews and its roster entry has no public_key"
    return None


def _same_family(gate: Any, model: str, family: str | None) -> str | None:
    if not gate.distinct_families:
        return None
    other = next((a for a in gate.approvals if a.family == family and a.model != model), None)
    return f"same family ({family}) as {other.model}'s approval, which already counts" if other else None


def _eligible_text(gate: Any, node_id: str, model: str) -> str:
    if any(b.model == model for b in gate.blocks):
        return "can approve on re-review (its record blocks this commit)"
    if model == HUMAN:
        return f"can approve, interactively with `specy-road mark-implementation-reviewed {node_id}`"
    return "can approve (file with `specy-road review record`)"


def reviewer_eligibility(repo_root: Path, node: dict[str, Any], gate: Any, branch: str | None) -> list[dict[str, Any]]:
    """One row per roster entry while the gate is not met: ``model``, ``family``, ``eligible`` and ``reason``."""
    if gate.passed or gate.config_error or gate.commit is None:
        return []
    config, writers, rejected = gate.config, _writers(repo_root, node["id"], branch), _rejected(repo_root, gate)
    counting = {a.model for a in gate.approvals}
    rows = []
    for entry in config["roster"]:
        model, family = entry["id"], entry.get("family")
        why = _roster_reason(config, node, model)
        if why is None and model in counting:
            rows.append({"model": model, "family": family, "eligible": True, "reason": "its approval counts"})
            continue
        why = why or writers.get(model) or rejected.get(model) or _same_family(gate, model, family)
        rows.append({"model": model, "family": family, "eligible": why is None,
                     "reason": why or _eligible_text(gate, node["id"], model)})
    return rows


def eligibility_lines(st: dict[str, Any]) -> list[str]:
    """``handoff status`` text: the rows of :func:`reviewer_eligibility`, under the policy line."""
    rows = st.get("reviewer_eligibility") or []
    head = ["  who can still supply a counting approval at this commit:"] if rows else []
    return head + [f"    {r['model']} ({r['family']}): {'' if r['eligible'] else 'excluded — '}{r['reason']}"
                   for r in rows]
