"""Assign a coordinator, an executor, and reviewers to each ready leaf.

``specy-road orchestrate plan`` (proposal §4.2): starts from the dependency
waves and parallel batches that ``grind-session --plan`` already computes
(:mod:`session_plan`), then picks models from the roster for every ready
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
* **Availability (§3.7).** A roster entry with ``unavailable_until`` on or
  after today is skipped; substitutions already model who stands in.
* **Cost (§3.7).** Among capable executors (profile executor score ≥ 3, or no
  profile), the cheapest by list price wins; reviewers rank by reviewer score,
  then cost; the coordinator by coordinator score.
* **Independence (§3.2).** The executor's model is not offered as its own
  reviewer, and with ``reviewers_distinct_families`` one reviewer per family.

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
from specy_road.bundled_scripts.session_plan import compute_session_plan
from specy_road.model_profiles import Profile, profile_for_entry
from specy_road.orchestration_config import active_substitutions, effective_config
from specy_road.registry_yaml import read_registry, registry_path

DEFAULT_SENSITIVITY = "public"
ANY = "any"
MIN_EXECUTOR_SCORE = 3


def node_sensitivity(node: dict[str, Any]) -> str:
    return str(node.get("sensitivity") or DEFAULT_SENSITIVITY)


def node_eligibility(node: dict[str, Any]) -> str:
    return str(node.get("executor_eligibility") or ANY)


def entry_may_process(entry: dict[str, Any]) -> list[str]:
    raw = entry.get("may_process")
    return [str(x) for x in raw] if raw else [DEFAULT_SENSITIVITY]


def may_handle(entry: dict[str, Any], sensitivity: str) -> bool:
    return sensitivity in entry_may_process(entry)


def is_available(entry: dict[str, Any], today: date | None = None) -> bool:
    """False while ``unavailable_until`` (inclusive) has not passed."""
    until = entry.get("unavailable_until")
    return not until or str(until) < (today or date.today()).isoformat()


@dataclass
class Candidate:
    entry: dict[str, Any]
    profile: Profile | None

    @property
    def id(self) -> str:
        return str(self.entry.get("id"))

    @property
    def family(self) -> str:
        return str(self.entry.get("family"))

    def score(self, role: str) -> int:
        return (self.profile.role_score(role) or 0) if self.profile and self.profile.ok else 0

    @property
    def cost(self) -> float | None:
        """List price per million tokens, input plus output; ``None`` when unknown."""
        if not self.profile or not self.profile.ok:
            return None
        c = self.profile.data.get("cost_usd_per_mtok") or {}
        try:
            return float(c.get("input")) + float(c.get("output"))
        except (TypeError, ValueError):
            return None

    def describe(self, role: str) -> str:
        cost = f"${self.cost:g}/MTok" if self.cost is not None else "cost unknown"
        return f"{self.id} ({self.family}; {role} score {self.score(role) or '?'}, {cost})"


@dataclass
class Assignment:
    node_id: str
    sensitivity: str
    eligibility: str
    coordinator: str | None = None
    executor: str | None = None
    reviewers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "sensitivity": self.sensitivity, "eligibility": self.eligibility,
                "coordinator": self.coordinator, "executor": self.executor, "reviewers": self.reviewers,
                "notes": self.notes, "problems": self.problems}


@dataclass
class OrchestrationPlan:
    under: str | None
    policy: dict[str, Any]
    batches: list[list[Assignment]]
    blocked: list[str]
    active: list[str]

    @property
    def ok(self) -> bool:
        return all(a.ok for b in self.batches for a in b)

    def to_dict(self) -> dict[str, Any]:
        return {"under": self.under, "policy": self.policy, "ok": self.ok,
                "batches": [[a.to_dict() for a in b] for b in self.batches],
                "blocked": self.blocked, "active": self.active}


def _usable(c: Candidate, sensitivity: str, today: date | None) -> bool:
    return is_available(c.entry, today) and may_handle(c.entry, sensitivity)


def _pick_executor(cands: list[Candidate], a: Assignment, today: date | None) -> None:
    pool = [c for c in cands if "executor" in (c.entry.get("roles") or []) and _usable(c, a.sensitivity, today)]
    if a.eligibility != ANY:
        pool = [c for c in pool if str(c.entry.get("class") or "") == a.eligibility]
    capable = [c for c in pool if c.profile is None or not c.profile.ok or c.score("executor") >= MIN_EXECUTOR_SCORE]
    capable.sort(key=lambda c: (c.cost if c.cost is not None else float("inf"), -c.score("executor")))
    if not capable:
        need = f"may_process containing {a.sensitivity!r}"
        if a.eligibility != ANY:
            need += f" and class {a.eligibility!r}"
        a.problems.append(f"no eligible executor: needs a rostered executor with {need}")
        return
    a.executor = capable[0].id
    a.notes.append("executor: cheapest capable — " + capable[0].describe("executor"))


def _pick_reviewers(cands: list[Candidate], a: Assignment, config: dict[str, Any], today: date | None) -> None:
    policy = config["policy"]
    required = int(policy["reviewers_required"])
    distinct = bool(policy["reviewers_distinct_families"])
    substitutes = {s.get("use") for s in active_substitutions(config, a.node_id, today)}
    pool = [c for c in cands
            if ("reviewer" in (c.entry.get("roles") or []) or c.id in substitutes)
            and _usable(c, a.sensitivity, today) and c.id != a.executor]
    pool.sort(key=lambda c: (-c.score("reviewer"), c.cost if c.cost is not None else float("inf")))
    seen: set[str] = set()
    for c in pool:
        if distinct and c.family in seen:
            continue
        a.reviewers.append(c.id)
        seen.add(c.family)
        a.notes.append("reviewer: " + c.describe("reviewer") + (" [substitute]" if c.id in substitutes else ""))
        if len(a.reviewers) >= required:
            break
    if len(a.reviewers) < required:
        unit = "distinct-family reviewers" if distinct else "reviewers"
        a.problems.append(f"need {required} {unit} that may process {a.sensitivity!r} "
                          f"(other than the executor), found {len(a.reviewers)}")


def _pick_coordinator(cands: list[Candidate], a: Assignment, today: date | None) -> None:
    pool = [c for c in cands if "coordinator" in (c.entry.get("roles") or []) and is_available(c.entry, today)]
    pool.sort(key=lambda c: -c.score("coordinator"))
    if pool:
        a.coordinator = pool[0].id


def assign_leaf(node: dict[str, Any], cands: list[Candidate], config: dict[str, Any],
                today: date | None = None) -> Assignment:
    a = Assignment(node["id"], node_sensitivity(node), node_eligibility(node))
    _pick_coordinator(cands, a, today)
    _pick_executor(cands, a, today)
    _pick_reviewers(cands, a, config, today)
    return a


def build_orchestration_plan(root: Path, *, under: str | None = None,
                             today: date | None = None) -> tuple[OrchestrationPlan | None, str | None]:
    config, err = effective_config(root)
    if err:
        return None, f"orchestration config: {err}"
    nodes = load_roadmap(root)["nodes"]
    by_id = {n["id"]: n for n in nodes}
    if under and under not in by_id:
        return None, f"unknown node id: {under}"
    sp = compute_session_plan(nodes, read_registry(registry_path(root)), under=under)
    cands = [Candidate(e, profile_for_entry(root, e)) for e in config.get("roster") or []]
    batches = [[assign_leaf(by_id[nid], cands, config, today) for nid in batch if nid in by_id]
               for batch in sp.parallel_batches]
    return OrchestrationPlan(under, dict(config["policy"]), batches,
                             [b.node_id for b in sp.blocked], list(sp.active)), None
