"""Pick the coordinator, executor and reviewers for one leaf (:func:`assign_leaf`).

Moved out of :mod:`specy_road.orchestrate_plan`, which re-exports these names and documents the
rules in the order they apply. ``spread_index`` (``orchestrate plan --spread``) picks the executor
round-robin among the capable, available entries by the leaf's position in the plan instead of the
cheapest; with no rostered coordinator the session that runs the plan coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from specy_road.model_profiles import Profile
from specy_road.orchestration_config import active_substitutions
from specy_road.review_strong import applicable_items, item_label

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
    coordinator_is_session: bool = False   # no rostered coordinator: the session running the plan coordinates
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
                "coordinator": self.coordinator, "coordinator_is_session": self.coordinator_is_session,
                "executor": self.executor, "reviewers": self.reviewers,
                "notes": self.notes, "problems": self.problems, "strong_review": self.strong_review}


def _usable(c: Candidate, sensitivity: str, today: date | None) -> bool:
    return is_available(c.entry, today) and may_handle(c.entry, sensitivity)


def _valid(pool: list[Candidate], a: Assignment) -> list[Candidate]:
    """The pool without invalid profiles, each reported once: `prompt` would refuse them."""
    bad = [c for c in pool if c.profile is not None and not c.profile.ok]
    for c in bad:
        errs = c.profile.errors
        why = f"{c.id}: {errs[0]}" if len(errs) == 1 and errs[0].startswith("invalid profile:") else \
            f"{c.id}: its profile is invalid ({'; '.join(errs)}); fix it or drop the entry"
        if why not in a.problems:
            a.problems.append(why)
    return [c for c in pool if c not in bad]


def _pick_executor(cands: list[Candidate], a: Assignment, today: date | None, drift: str | None = None,
                   spread_index: int | None = None) -> None:
    pool = [c for c in cands if "executor" in (c.entry.get("roles") or []) and _usable(c, a.sensitivity, today)]
    if a.eligibility != ANY:
        pool = [c for c in pool if str(c.entry.get("class") or "") == a.eligibility]
    valid = _valid(pool, a)
    capable = [c for c in valid if c.profile is None or c.score("executor") >= MIN_EXECUTOR_SCORE]
    capable.sort(key=Candidate.executor_key)
    if not capable and len(valid) < len(pool):   # the invalid-profile problem is the cause; a hint would mislead
        return
    if not capable and drift:   # the may_process hint would send the adopter to a file routing does not read
        a.problems.append(f"no eligible executor: {drift}")
        return
    if not capable:
        need = f"may_process containing {a.sensitivity!r}"
        if a.eligibility != ANY:
            need += f" and class {a.eligibility!r}"
        a.problems.append(f"no eligible executor: needs a rostered executor with {need}")
        return
    pick = capable[0] if spread_index is None else capable[spread_index % len(capable)]
    a.executor = pick.id
    tags = [f"{k} {pick.entry[k]}" for k in ("class", "billing_route") if pick.entry.get(k)]
    how = "cheapest capable" if spread_index is None else f"round-robin (--spread) over {len(capable)} capable"
    a.notes.append(f"executor: {how} — " + pick.describe("executor") + (f" [{', '.join(tags)}]" if tags else ""))


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
    elif not any("coordinator" in (c.entry.get("roles") or []) for c in cands):
        a.coordinator_is_session = True
        a.notes.append("coordinator: this session (no roster entry has the coordinator role; to roster a "
                       "model coordinator see docs/orchestration-roster.md)")
    else:
        a.problems.append(f"no eligible coordinator: needs a rostered coordinator with may_process "
                          f"containing {a.sensitivity!r}")


def assign_leaf(node: dict[str, Any], cands: list[Candidate], config: dict[str, Any],
                today: date | None = None, drift: str | None = None, prefix: str = "",
                spread_index: int | None = None) -> Assignment:
    """``prefix``: :func:`project_prefix`, so a strong-review zone written from either root meets the leaf's.
    ``spread_index``: the leaf's position in the plan, for ``--spread``; ``None`` picks the cheapest executor."""
    a = Assignment(node["id"], node_sensitivity(node), node_eligibility(node))
    a.strong_review = [{"item": item_label(i, item), "require_one_of": list(item["require_one_of"])}
                       for i, item in applicable_items(config["policy"], node.get("touch_zones"), prefix)]
    _pick_executor(cands, a, today, drift, spread_index)
    _pick_reviewers(cands, a, config, today)
    _pick_coordinator(cands, a, today)
    return a


