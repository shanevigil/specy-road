"""Assign a coordinator, an executor, and reviewers to each ready leaf.

``specy-road orchestrate plan`` (proposal §4.2): starts from the dependency
waves and parallel batches that ``grind-session --plan`` already computes
(:func:`gather_session_plan`, so a leaf pickup skips — unauthored, or finished
on an unmerged branch — is not ready here either), then picks models from the roster for every ready
leaf using eligibility, sensitivity, availability, cost, and role scores
from the model profiles. It assigns; it never dispatches — the coordinator
(or the slice-5 skill) does that with ``specy-road prompt``.

Rules, in the order they apply:

* **Sensitivity (§3.6).** A leaf's ``sensitivity`` (default ``public``) must be
  in a model's roster ``may_process`` (default ``[public]``), for executors
  and reviewers alike. Nothing restricted ever routes to a model that may
  not see it.
* **Eligibility (§3.1).** A leaf's ``executor_eligibility`` (default ``any``)
  names a roster ``class`` tag; only executors carrying that tag qualify.
* **Availability (§3.7).** A roster entry with ``available: false``, or with
  ``paused_until`` (or legacy ``unavailable_until``) still in force, is skipped;
  ``roadmap/orchestration.local.yaml`` can set those fields without a push,
  and add whole entries for this clone under ``roster_add`` (labelled local).
  Substitutions already model who stands in.
* **Cost (§3.7).** Among capable executors (profile executor score ≥ 3, or no
  profile), the roster ``class`` ranks first (``cheap``, then untagged or other
  tags, then ``senior``), then list price, then ``billing_route`` (a
  subscription or OAuth route before none, before any other, such as an API
  key), so a roster without prices still prefers what it declares cheap;
  reviewers rank by reviewer score, then cost; the coordinator by coordinator
  score.
* **Independence (§3.2).** The executor's model is not offered as its own
  reviewer, and with ``reviewers_distinct_families`` one reviewer per family.
* **Strong review.** Each ``policy.strong_review`` item the leaf's touch zones
  meet (:mod:`specy_road.review_strong`) is listed with the reviewers that can
  satisfy it, and its best-ranked one is picked first, whatever its family;
  an item none of them can satisfy makes the leaf unstaffable. With
  ``policy.quality_routing`` on, each flagged area (:mod:`specy_road.review_tally`)
  the leaf's zones fall in adds one more item over the strong set.

The human's routing preferences (``kind: preference`` in ``roadmap/decisions.yaml``)
are never applied here: the plan lists every active one under
``preferences_not_applied``, noting any preferred model the roster does not have
or marks unavailable, and the coordinator applies them when it delegates.

The leaf fields are read through :func:`node_sensitivity` and
:func:`node_eligibility` only, so where they live (node vs. orchestration
config) is a one-function decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.decisions import plan_preferences
from specy_road.orchestrate_assign import (  # noqa: F401 — re-exported: callers import them from here
    ANY,
    CLASS_RANK,
    DEFAULT_SENSITIVITY,
    FLAT_RATE_ROUTES,
    MIN_EXECUTOR_SCORE,
    Assignment,
    Candidate,
    _pause_active,
    assign_leaf,
    entry_may_process,
    is_available,
    may_handle,
    node_eligibility,
    node_sensitivity,
    unavailability_reason,
    unavailable_prompt_error,
)
from specy_road.orchestration_pinned import WORKTREE_REF, pinned_config, pinned_profile_for_entry, roster_source
from specy_road.review_tally import flagged_areas
from specy_road.roster_local import local_roster_ids
from specy_road.runtime_paths import project_prefix
from specy_road.zone_coverage import zone_coverage_warnings


@dataclass
class OrchestrationPlan:
    under: str | None
    policy: dict[str, Any]
    batches: list[list[Assignment]]
    blocked: list[str]
    active: list[str]
    unauthored: list[str] = field(default_factory=list)   # ready but for a placeholder sheet; pickup skips them
    roster_ref: str | None = None      # where the roster was read from; None outside git
    roster_drift: str | None = None    # the working-tree roster is absent there or differs
    preferences_not_applied: list[dict[str, Any]] = field(default_factory=list)   # active, for the coordinator
    preferences_error: str | None = None   # the ledger could not be read; the plan still stands
    local_roster: list[str] = field(default_factory=list)   # ids this clone's roster_add contributed

    @property
    def ok(self) -> bool:
        return all(a.ok for b in self.batches for a in b)

    def to_dict(self) -> dict[str, Any]:
        return {"under": self.under, "policy": self.policy, "ok": self.ok,
                "roster_ref": self.roster_ref, "roster_drift": self.roster_drift,
                "batches": [[a.to_dict() for a in b] for b in self.batches],
                "blocked": self.blocked, "active": self.active, "unauthored": self.unauthored,
                "preferences_not_applied": self.preferences_not_applied,
                "preferences_error": self.preferences_error, "local_roster": self.local_roster}


def preference_notice(pref: dict[str, Any], cands: list[Candidate], today: date | None) -> dict[str, Any]:
    """The preference plus ``roster_notes``: availability comes from the roster, so the two never disagree."""
    by_id = {c.id: c for c in cands}
    notes = []
    for m in pref.get("models") or []:
        why = "not in the roster" if m not in by_id else unavailability_reason(by_id[m].entry, today)
        if why:
            notes.append(f"{m}: {why}")
    return {**pref, "roster_notes": notes}


def build_orchestration_plan(root: Path, *, under: str | None = None, today: date | None = None,
                             spread: bool = False, roster_from_worktree: bool = False) -> tuple[OrchestrationPlan | None, str | None]:
    """``spread``: executors round-robin over the capable entries by leaf order (batch, then position).
    ``roster_from_worktree``: a dry run on the working tree's roster (``roster_ref`` is ``worktree``)."""
    config, err = pinned_config(root, worktree=roster_from_worktree)
    if err:
        return None, f"orchestration config: {err}"
    if under and under not in {n["id"] for n in load_roadmap(root)["nodes"]}:
        return None, f"unknown node id: {under}"
    nodes, _reg, sp = gather_session_plan(root, under)
    by_id = {n["id"]: n for n in nodes}
    local = local_roster_ids(root)
    cands = [Candidate(e, pinned_profile_for_entry(root, e, worktree=roster_from_worktree), e.get("id") in local)
             for e in config.get("roster") or []]
    ref, drift = (WORKTREE_REF, None) if roster_from_worktree else roster_source(root)
    prefix = project_prefix(root)
    flagged = flagged_areas(root, config["policy"])
    order = [nid for batch in sp.parallel_batches for nid in batch if nid in by_id]
    batches = [[assign_leaf(by_id[nid], cands, config, today, drift, prefix,
                            order.index(nid) if spread else None, flagged) for nid in batch if nid in by_id]
               for batch in sp.parallel_batches]
    assigned = [a.node_id for batch in batches for a in batch]
    coverage = zone_coverage_warnings(root, by_id, assigned)
    for batch in batches:
        for a in batch:
            if a.node_id in coverage:
                a.warnings.append(coverage[a.node_id])
    prefs, pref_err = plan_preferences(root, today)
    return OrchestrationPlan(under, dict(config["policy"]), batches,
                             [b.node_id for b in sp.blocked], list(sp.active),
                             [u.node_id for u in sp.unauthored], ref, drift,
                             [preference_notice(p, cands, today) for p in prefs], pref_err, local), None
