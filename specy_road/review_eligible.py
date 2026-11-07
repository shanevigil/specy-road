"""Who on the roster can still supply a counting approval: the lines ``handoff status`` prints under the policy.

When the gate is not met, a coordinator needs more than ``1/2 ... not met``: which roster entries may still
approve at this commit (the human included), and why each of the others cannot. Each roster entry is judged
with the gate's own checks (:mod:`specy_road.review_gate`), plus who wrote the change, taken from the leaf's
READY files as ``review_rca.rca_parties`` does:

* not a reviewer role — no ``reviewer`` role and no active substitution covering the node;
* the node's sensitivity is outside its roster ``may_process``;
* executor of the leaf — it filed a READY before any valid review of its own on the leaf (READY authors and record
  models are compared by :class:`Identity`: case-folded, every roster entry whose id, ``harness_model`` or profile
  name it is; a name two roster entries have, or a refused profile, closes the gate);
* wrote a fix commit on this leaf — it filed a READY after reviewing the leaf;
* rejected record — its record at this commit is invalid or does not count, with the gate's reason;
* same family as an approval already counted, under ``reviewers_distinct_families`` (not when its approval would
  satisfy an unmet ``policy.strong_review`` item, which counts whatever the family);
* ``signed_reviews`` is on and its roster entry has no ``public_key``;
* ``signed_reviews`` is on and its model's profile records guidance bypass, with no opt-in (M21.44);
* unavailable — ``available: false`` or a ``paused_until`` / ``unavailable_until`` still in force
  (skipped when that model's approval already counts at this commit).

Every exclusion is checked first, so a model whose approval the gate counts is listed as counting only when none
applies (a READY author never is); one that blocks may still approve on re-review. While a ``policy.strong_review``
item is unmet, each row that can approve says whether its approval would satisfy it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.orchestrate_plan import (
    entry_may_process,
    guidance_problem,
    is_available,
    may_handle,
    node_sensitivity,
    unavailability_reason,
)
from specy_road.orchestration_config import is_rostered_reviewer, substitute_for
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.review_files import HUMAN, ReviewFile, list_ready, list_review_history, list_reviews
from specy_road.review_strong import item_label
from specy_road.review_target import same_commit


class Identity:
    """One rule for READY ``agent`` and review-record ``model`` names.

    An entry's names are its roster ``id`` and ``harness_model`` and, when it has a pinned profile
    (:func:`~specy_road.orchestration_pinned.pinned_profile_for_entry`), that profile's declared ``api_id``, file
    name and ``aliases``. A name, case-folded, may be every entry that has it: exact ids and aliases together, no
    precedence; a name no entry has is only itself. A READY author is excluded under every entry it may be.

    Any of these closes the gate with a problem (:attr:`problems`): a READY or record name two or more entries
    have; an entry whose pinned profile is refused (its names cannot be known); an unreadable READY
    (:func:`writers`). Limit: entries that share a name cannot be told apart, so a roster where they do keeps the
    gate closed for any READY or record using that name until the names differ."""

    def __init__(self, repo_root: Path, config: dict[str, Any] | None = None) -> None:
        config = pinned_config(repo_root)[0] if config is None else config
        self.names: dict[str, set[str]] = {}
        self.problems: list[str] = []
        for entry in config.get("roster") or []:
            rid = str(entry.get("id"))
            prof = pinned_profile_for_entry(repo_root, entry)
            if prof is not None and not prof.ok:
                self.problems.append(f"roster entry {rid!r}: its profile's names cannot be known "
                                     f"({'; '.join(prof.errors)}); READY authorship cannot be decided")
            data = prof.data if prof is not None else {}
            aliases = data.get("aliases") if isinstance(data.get("aliases"), list) else []
            stem = [prof.path.stem] if prof is not None and prof.ok else []
            for name in filter(None, [rid, entry.get("harness_model"), data.get("api_id"), *stem, *aliases]):
                self.names.setdefault(str(name).casefold(), set()).add(rid)

    def __call__(self, name: object) -> set[str]:
        """The roster ids ``name`` may be (the class rule)."""
        key = str(name).casefold()
        return set(self.names.get(key) or {key})

    def ambiguous(self, name: object, ids: set[str]) -> None:
        """Record a problem when ``ids`` (``self(name)``) holds more than one roster entry."""
        why = (f"{name!r} names more than one roster entry ({', '.join(sorted(ids))}); which of them wrote "
               "or reviewed this leaf cannot be decided: name distinct roster ids")
        self.problems += [why] if len(ids) > 1 and why not in self.problems else []


def writers(repo_root: Path, node_id: str, branch: str | None,
            identity: Identity | None = None) -> dict[str, tuple[str, str]]:
    """Model -> (its READY file's name, why it wrote part of the change) for every model that filed a valid READY
    on the leaf; the gate (:func:`specy_road.review_gate.evaluate_gate`) never counts their records and
    ``review delegate`` refuses them. A READY written after the model's first valid review on the leaf
    is a fix; any other READY is the executor's (an executor that also files an approval stays the executor).
    Filing times are file mtimes: ``history/`` copies are written once. A self-review (``authored_fix``) is invalid.
    Names are roster ids by ``identity`` (:class:`Identity` over the pinned roster when omitted): a READY author
    is keyed under every entry it may be."""
    ident = identity or Identity(repo_root)
    first: dict[str, float] = {}
    for r in list_review_history(repo_root, node_id) + list_reviews(repo_root, node_id):
        if r.ok and (r.on_disk or r.path).is_file():
            t = (r.on_disk or r.path).stat().st_mtime
            first.update({m: min(t, first.get(m, t)) for m in ident(r.data["model"])})
    out: dict[str, tuple[str, str]] = {}
    for r in list_ready(repo_root, node_id, branch):
        if r.errors[:1] and r.errors[0].startswith("cannot read:"):   # its author is unknown: never ignore it
            ident.problems.append(f"{r.path.name} is unreadable ({r.errors[0]}); its author cannot be excluded")
        ids = ident(r.data.get("agent")) if r.ok else set()
        ident.ambiguous(r.data.get("agent"), ids)
        for agent in sorted(ids - out.keys()):
            fix = agent in first and r.path.stat().st_mtime > first[agent]
            out[agent] = (r.path.name, f"wrote a fix commit on this leaf ({r.path.name})" if fix
                          else f"executor of the leaf ({r.path.name})")
    return out


def reviews_to_judge(repo_root: Path, node: dict[str, Any], branch: str | None,
                     ineligible: list[tuple[ReviewFile, str]], config: dict[str, Any] | None = None,
                     problems: list[str] | None = None) -> list[ReviewFile]:
    """The node's review records the gate judges: a record whose model may be one of :func:`writers` goes to
    ``ineligible`` instead, whatever its validity, ``authored_fix``, verdict or signature (rc4 defect D3).
    Names are compared by :class:`Identity` over ``config``; its ambiguity problems are added to ``problems``."""
    ident = Identity(repo_root, config)
    authors, out = writers(repo_root, node["id"], branch, ident), []
    for r in list_reviews(repo_root, node["id"], acceptance_ids(node)):
        ident.ambiguous(model := str(r.data.get("model")), ids := ident(model))
        if hit := sorted(ids & authors.keys()):
            ineligible.append((r, f"{model} wrote {authors[hit[0]][0]} on this leaf; "
                                  "the executor never reviews its own leaf"))
        else:
            out.append(r)
    if problems is not None:
        problems += ident.problems
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


def _roster_reason(repo_root: Path, config: dict[str, Any], node: dict[str, Any], model: str,
                   counting: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Why the roster itself keeps ``model`` from reviewing ``node``, else ``None``."""
    entry = next(e for e in config["roster"] if e.get("id") == model)
    if not is_rostered_reviewer(config, model) and substitute_for(config, node["id"], model) is None:
        return f"not a reviewer role (roles: {', '.join(entry.get('roles') or []) or 'none'}) and no active substitution"
    if not may_handle(entry, node_sensitivity(node)):
        return f"{node['id']} is {node_sensitivity(node)!r}; it may process only {entry_may_process(entry)}"
    no_key = config["policy"].get("signed_reviews") and not entry.get("public_key")
    if why := ("policy requires signed reviews and its roster entry has no public_key" if no_key
               else guidance_problem(repo_root, config, entry)):
        return why
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
    config, rejected = gate.config, _rejected(repo_root, gate)
    authors = writers(repo_root, node["id"], branch, Identity(repo_root, config))
    counting = {a.model for a in gate.approvals}
    rows = []
    for entry in config["roster"]:
        model, family = entry["id"], entry.get("family")
        # Every exclusion first: an author or a second same-family approval never reads as counting.
        why = (_roster_reason(repo_root, config, node, model, counting=counting) or authors.get(model, ("", None))[1] or rejected.get(model)
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
