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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.decisions import plan_preferences
from specy_road.model_profiles import Profile
from specy_road.orchestration_pinned import WORKTREE_REF, pinned_config, pinned_profile_for_entry, roster_source
from specy_road.orchestration_config import active_substitutions
from specy_road.review_strong import applicable_items, item_label
from specy_road.review_tally import flagged_areas, quality_review
from specy_road.roster_local import local_roster_ids
from specy_road.runtime_paths import project_prefix

DEFAULT_SENSITIVITY = "public"
ANY = "any"
MIN_EXECUTOR_SCORE = 3
#: Executor order by roster ``class`` and ``billing_route``; anything unlisted ranks in the middle.
CLASS_RANK = {"cheap": 0, "senior": 2}
FLAT_RATE_ROUTES = ("subscription", "oauth")


def node_sensitivity(node: dict[str, Any]) -> str:
    return str(node.get("sensitivity") or DEFAULT_SENSITIVITY)


def node_eligibility(node: dict[str, Any]) -> str:
    return str(node.get("executor_eligibility") or ANY)


def entry_may_process(entry: dict[str, Any]) -> list[str]:
    """``may_process`` as written; ``[public]`` only when the key is absent — an explicit ``[]`` denies all."""
    raw = entry.get("may_process")
    return [DEFAULT_SENSITIVITY] if raw is None else [str(x) for x in raw]


def may_handle(entry: dict[str, Any], sensitivity: str) -> bool:
    return sensitivity in entry_may_process(entry)


def _pause_boundary(entry: dict[str, Any]) -> str | None:
    return entry.get("paused_until") or entry.get("unavailable_until")


def _as_utc(now: datetime | date | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, date) and not isinstance(now, datetime):
        return datetime.combine(now, datetime.min.time(), tzinfo=timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _pause_active(entry: dict[str, Any], now: datetime | date | None = None) -> bool:
    """True while a date (inclusive through that day) or datetime pause has not passed."""
    raw = _pause_boundary(entry)
    if not raw:
        return False
    s = str(raw)
    current = _as_utc(now)
    if len(s) == 10:
        return s >= current.date().isoformat()
    try:
        until = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return current < until.astimezone(timezone.utc)


def is_available(entry: dict[str, Any], now: datetime | date | None = None) -> bool:
    """False when ``available: false`` or a pause is still in force."""
    if entry.get("available") is False:
        return False
    return not _pause_active(entry, now)


def unavailability_reason(entry: dict[str, Any], now: datetime | date | None = None) -> str | None:
    """Why :func:`is_available` is false, for delegate and prompt refusals."""
    if entry.get("available") is False:
        return "available: false"
    if _pause_active(entry, now):
        if entry.get("paused_until"):
            return f"paused until {entry['paused_until']}"
        if entry.get("unavailable_until"):
            return f"unavailable until {entry['unavailable_until']}"
    return None


def unavailable_prompt_error(model: str, entry: dict[str, Any]) -> str:
    return f"{model!r} is unavailable ({unavailability_reason(entry) or 'availability'})"


@dataclass
class Candidate:
    entry: dict[str, Any]
    profile: Profile | None
    local: bool = False   # added by this clone's roster_add (roster_local), not committed

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

    @property
    def class_rank(self) -> int:
        return CLASS_RANK.get(str(self.entry.get("class") or ""), 1)

    @property
    def billing_rank(self) -> int:
        """0 for a flat-rate route (subscription, OAuth), 1 when unset, 2 for any other (metered)."""
        route = str(self.entry.get("billing_route") or "").lower()
        if not route:
            return 1
        return 0 if any(t in route for t in FLAT_RATE_ROUTES) else 2

    def executor_key(self) -> tuple[int, float, int, int]:
        return (self.class_rank, self.cost if self.cost is not None else float("inf"),
                self.billing_rank, -self.score("executor"))

    def describe(self, role: str) -> str:
        cost = f"${self.cost:g}/MTok" if self.cost is not None else "cost unknown"
        return f"{self.id} ({self.family}; {role} score {self.score(role) or '?'}, {cost})" + (
            " [local]" if self.local else "")


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
    strong_review: list[dict[str, Any]] = field(default_factory=list)   # item, require_one_of, can_satisfy

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "sensitivity": self.sensitivity, "eligibility": self.eligibility,
                "coordinator": self.coordinator, "executor": self.executor, "reviewers": self.reviewers,
                "notes": self.notes, "problems": self.problems, "strong_review": self.strong_review}


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


def _usable(c: Candidate, sensitivity: str, today: date | None) -> bool:
    return is_available(c.entry, today) and may_handle(c.entry, sensitivity)


def _valid(pool: list[Candidate], a: Assignment) -> list[Candidate]:
    """The pool without invalid profiles, each reported once: `prompt` would refuse them."""
    bad = [c for c in pool if c.profile is not None and not c.profile.ok]
    for c in bad:
        why = f"{c.id}: its profile is invalid ({'; '.join(c.profile.errors)}); fix it or drop the entry"
        if why not in a.problems:
            a.problems.append(why)
    return [c for c in pool if c not in bad]


def _pick_executor(cands: list[Candidate], a: Assignment, today: date | None, drift: str | None = None) -> None:
    pool = [c for c in cands if "executor" in (c.entry.get("roles") or []) and _usable(c, a.sensitivity, today)]
    if a.eligibility != ANY:
        pool = [c for c in pool if str(c.entry.get("class") or "") == a.eligibility]
    capable = [c for c in _valid(pool, a) if c.profile is None or c.score("executor") >= MIN_EXECUTOR_SCORE]
    capable.sort(key=Candidate.executor_key)
    if not capable and drift:   # the may_process hint would send the adopter to a file routing does not read
        a.problems.append(f"no eligible executor: {drift}")
        return
    if not capable:
        need = f"may_process containing {a.sensitivity!r}"
        if a.eligibility != ANY:
            need += f" and class {a.eligibility!r}"
        a.problems.append(f"no eligible executor: needs a rostered executor with {need}")
        return
    a.executor = capable[0].id
    tags = [f"{k} {capable[0].entry[k]}" for k in ("class", "billing_route") if capable[0].entry.get(k)]
    a.notes.append("executor: cheapest capable — " + capable[0].describe("executor")
                   + (f" [{', '.join(tags)}]" if tags else ""))


def _pick_reviewers(cands: list[Candidate], a: Assignment, config: dict[str, Any], today: date | None) -> None:
    policy = config["policy"]
    required = int(policy["reviewers_required"])
    distinct = bool(policy["reviewers_distinct_families"])
    substitutes = {s.get("use") for s in active_substitutions(config, a.node_id, today)}
    pool = _valid([c for c in cands
                   if ("reviewer" in (c.entry.get("roles") or []) or c.id in substitutes)
                   and _usable(c, a.sensitivity, today) and c.id != a.executor], a)
    pool.sort(key=lambda c: (-c.score("reviewer"), c.cost if c.cost is not None else float("inf")))
    _pick_strong(pool, a, substitutes)
    seen = {c.family for c in pool if c.id in a.reviewers}

    def count() -> int:   # distinct families when the policy asks for them; strong picks may share one
        return len(seen) if distinct else len(a.reviewers)

    for c in pool:
        if count() >= required:
            break
        if c.id in a.reviewers or distinct and c.family in seen:
            continue
        a.reviewers.append(c.id)
        seen.add(c.family)
        a.notes.append("reviewer: " + c.describe("reviewer") + (" [substitute]" if c.id in substitutes else ""))
    if count() < required:
        unit = "distinct-family reviewers" if distinct else "reviewers"
        a.problems.append(f"need {required} {unit} that may process {a.sensitivity!r} "
                          f"(other than the executor), found {count()}")


def _pick_strong(pool: list[Candidate], a: Assignment, substitutes: set[Any]) -> None:
    """Record who can satisfy each of ``a.strong_review`` and pick the best-ranked one first: the gate needs one
    approval per item whatever the families, so an item already met by an earlier pick adds no one."""
    for s in a.strong_review:
        s["can_satisfy"] = [c.id for c in pool if c.id in s["require_one_of"]]
        if not s["can_satisfy"]:
            a.problems.append(f"{s['item']}: none of {', '.join(s['require_one_of'])} can review this leaf "
                              f"(a rostered reviewer or active substitute, available, that may process "
                              f"{a.sensitivity!r}, other than the executor)")
        elif not set(s["can_satisfy"]) & set(a.reviewers):
            c = next(c for c in pool if c.id == s["can_satisfy"][0])
            a.reviewers.append(c.id)
            a.notes.append("reviewer: " + c.describe("reviewer") + (" [substitute]" if c.id in substitutes else "")
                           + f" [strong review: {s['item']}]")


def _pick_coordinator(cands: list[Candidate], a: Assignment, today: date | None) -> None:
    pool = _valid([c for c in cands if "coordinator" in (c.entry.get("roles") or [])
                   and _usable(c, a.sensitivity, today)], a)
    pool.sort(key=lambda c: -c.score("coordinator"))
    if pool:
        a.coordinator = pool[0].id
    else:
        a.problems.append(f"no eligible coordinator: needs a rostered coordinator with may_process "
                          f"containing {a.sensitivity!r}")


def assign_leaf(node: dict[str, Any], cands: list[Candidate], config: dict[str, Any],
                today: date | None = None, drift: str | None = None, prefix: str = "",
                flagged: set[str] | None = None) -> Assignment:
    """``prefix``: :func:`project_prefix`, so a strong-review zone written from either root meets the leaf's.
    ``flagged``: the areas ``policy.quality_routing`` routes a strong reviewer to (:mod:`specy_road.review_tally`)."""
    a = Assignment(node["id"], node_sensitivity(node), node_eligibility(node))
    a.strong_review = [{"item": item_label(i, item), "require_one_of": list(item["require_one_of"])}
                       for i, item in applicable_items(config["policy"], node.get("touch_zones"), prefix)]
    items, notes = quality_review(config["policy"], node.get("touch_zones"), flagged or set(), prefix)
    a.strong_review += items
    a.notes += notes
    _pick_executor(cands, a, today, drift)
    _pick_reviewers(cands, a, config, today)
    _pick_coordinator(cands, a, today)
    return a


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
                             roster_from_worktree: bool = False) -> tuple[OrchestrationPlan | None, str | None]:
    """``roster_from_worktree``: a dry run on the working tree's roster (``roster_ref`` is ``worktree``)."""
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
    batches = [[assign_leaf(by_id[nid], cands, config, today, drift, prefix, flagged) for nid in batch if nid in by_id]
               for batch in sp.parallel_batches]
    prefs, pref_err = plan_preferences(root, today)
    return OrchestrationPlan(under, dict(config["policy"]), batches,
                             [b.node_id for b in sp.blocked], list(sp.active),
                             [u.node_id for u in sp.unauthored], ref, drift,
                             [preference_notice(p, cands, today) for p in prefs], pref_err, local), None
