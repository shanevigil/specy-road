"""The fix-round budget's next step, as an explicit state machine.

``policy.max_fix_rounds`` (unset: no budget) caps the blocking review rounds one leaf may spend. Once spent
while any counted review blocks, ``handoff status`` reports ``fix_round_budget_spent`` and the step this
module picks. :func:`facts` reads what the step depends on; :data:`STATES` is an ordered table of rows, the
first whose ``when`` holds is the state; its ``step`` yields exactly one :class:`Step`:

* ``command`` — a command that runs as printed from that state;
* ``blocked`` — no agent command would succeed; ``next`` is a ``decisions add`` asking a human (it runs);
* ``none`` — no budget step (budget not spent, or nothing blocks).

Later leaves add rows here (``review rca`` launcher, convergence-aware escalation): insert a :class:`State`
before the row it refines. Design: ``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from specy_road.orchestrate_plan import is_available
from specy_road.review_deferral import rca_deferral
from specy_road.review_files import HUMAN, PACKET_NAME, ReviewFile, latest_ready, reviews_dir

if TYPE_CHECKING:
    from specy_road.review_rca import LoopState

#: RCA states (``Facts.rca``).
NO_RCA, NON_DEFER, DEFER_UNAPPLIED, DEFER_APPLIED = "none", "non_defer", "defer_unapplied", "defer_applied"
EXECUTOR_ACTIONS = ("continue_with_class_fix", "restart_executor_fresh", "fix_tests", "fix_environment")


@dataclass(frozen=True)
class Facts:
    node_id: str
    budget: int | None
    blocking_rounds: int
    blocked: bool                 # a counted review blocks at the commit under review
    rca: str                      # NO_RCA | NON_DEFER | DEFER_UNAPPLIED | DEFER_APPLIED
    record: ReviewFile | None     # the covering RCA record
    refused: str | None           # why `review defer` would refuse the covering record (DEFER_UNAPPLIED)
    analyst: str | None           # an available rostered reviewer that neither implemented nor reviewed it
    executor: str | None          # the latest READY's agent, when an available rostered executor
    reviewer: str | None          # an available reviewer that blocked the latest round
    packet: bool                  # PACKET.md exists (the reviewer prompt needs it)

    @property
    def action(self) -> str | None:
        return self.record.data["recommended_action"]["type"] if self.record else None


@dataclass(frozen=True)
class Step:
    kind: str                     # "command" | "blocked" | "none"
    next: str | None
    why: str


@dataclass(frozen=True)
class State:
    name: str
    when: Callable[[Facts], bool]
    step: Callable[[Facts], Step]


def _human(f: Facts, reason: str, effect: str) -> Step:
    """``blocked``: a complete ``decisions add`` asking a human to act."""
    cmd = " ".join(["specy-road decisions add", f.node_id, "--kind decision", "--summary",
                     shlex.quote(f"fix-round budget spent: {reason}"), "--why", shlex.quote(reason),
                     "--option", shlex.quote(f"apply|{effect}"),
                     "--option", shlex.quote("decline|keep the current review loop"),
                     "--recommendation apply --recommendation-reason", shlex.quote("no agent command would succeed"),
                     "--default decline"])
    return Step("blocked", cmd, f"blocked: {reason}")


def _rca_why(f: Facts) -> str:
    a = f.record.data["recommended_action"]
    return f"{f.record.path.name} recommends {a['type']}: {a['instructions']}"


def _executor(f: Facts, why: str) -> Step:
    return Step("command", f"specy-road prompt {f.node_id} --role executor --model {shlex.quote(f.executor)}", why)


def _none(why: str) -> Callable[[Facts], Step]:
    return lambda f: Step("none", None, why)


_SPENT = "the budget is spent and a review still blocks"
STATES: list[State] = [
    State("budget_unset", lambda f: f.budget is None, _none("no fix-round budget (policy.max_fix_rounds unset)")),
    State("within_budget", lambda f: f.blocking_rounds < f.budget, _none("the fix-round budget is not spent")),
    State("spent_no_blocks", lambda f: not f.blocked, _none("the budget is spent, but no counted review blocks")),
    State("spent_no_rca", lambda f: f.rca == NO_RCA and f.analyst is not None,
          lambda f: Step("command", f"specy-road prompt {f.node_id} --role rca --force --reason "
                                    f"'fix-round budget spent' --model {shlex.quote(f.analyst)}",
                         "no root-cause analysis covers the latest round")),
    State("spent_no_rca_no_analyst", lambda f: f.rca == NO_RCA,
          lambda f: _human(f, "no root-cause analysis covers the latest round, and no available rostered reviewer "
                              "that neither implemented nor reviewed the leaf can write one",
                           "make an independent reviewer available, or stop the loop by hand")),
    State("spent_defer_unapplied", lambda f: f.rca == DEFER_UNAPPLIED and f.refused is None,
          lambda f: Step("command", f"specy-road review defer {f.node_id} --rca {shlex.quote(str(f.record.path))}",
                         _rca_why(f))),
    State("spent_defer_refused", lambda f: f.rca == DEFER_UNAPPLIED,
          lambda f: _human(f, f"{_rca_why(f)}; `review defer` would refuse it: {' '.join(f.refused.split())}",
                           "decide what the leaf does with these findings")),
    State("spent_defer_applied", lambda f: f.rca == DEFER_APPLIED and f.executor is not None,
          lambda f: _executor(f, f"{f.record.path.name} is applied; {_SPENT}, so the blocks it did not defer are "
                                 "fixed in this leaf")),
    State("spent_defer_applied_no_executor", lambda f: f.rca == DEFER_APPLIED,
          lambda f: _human(f, f"{f.record.path.name} is applied, {_SPENT}, and no available rostered executor "
                              "handed this leaf off", "assign an executor to the remaining blocks")),
    State("spent_rca_executor", lambda f: f.action in EXECUTOR_ACTIONS and f.executor is not None,
          lambda f: _executor(f, _rca_why(f))),
    State("spent_rca_packet", lambda f: f.action == "change_or_reprompt_reviewer" and f.reviewer and not f.packet,
          lambda f: Step("command", f"specy-road review-packet {f.node_id}",
                         f"{_rca_why(f)}; the reviewer prompt needs the packet first")),
    State("spent_rca_reviewer", lambda f: f.action == "change_or_reprompt_reviewer" and f.reviewer is not None,
          lambda f: Step("command", f"specy-road prompt {f.node_id} --role reviewer --model "
                                    f"{shlex.quote(f.reviewer)}", _rca_why(f))),
    State("spent_rca_human", lambda f: True,
          lambda f: _human(f, _rca_why(f), f.record.data["recommended_action"]["instructions"])),
]


def classify(f: Facts) -> State:
    return next(s for s in STATES if s.when(f))


def _available(config: dict[str, Any], role: str, exclude: set[str] = frozenset()) -> list[str]:
    """Rostered ids with ``role`` that :func:`orchestrate_plan.is_available` allows (the rule prompt applies)."""
    return [e["id"] for e in config.get("roster") or [] if role in (e.get("roles") or [])
            and e.get("id") not in exclude and e.get("id") != HUMAN and is_available(e)]


def facts(repo_root: Path, config: dict[str, Any], loop: LoopState, node_id: str, blocked: bool) -> Facts:
    """What the step depends on; the costlier reads happen only once the budget is set."""
    from specy_road.bundled_scripts.review_defer import applicable_record   # it imports review_deferral
    from specy_road.review_rca import rca_parties

    budget = (config.get("policy") or {}).get("max_fix_rounds")
    blocking = sum(1 for rnd in loop.rounds if any(r.data["verdict"] == "block" for r in rnd.records))
    covering = [r for r in loop.rcas if r.ok and int(r.data["trigger"]["round"]) >= len(loop.rounds)]
    record = covering[-1] if covering and budget is not None else None
    rca, refused = NO_RCA, None
    if record is not None and record.data["recommended_action"]["type"] != "defer_findings":
        rca = NON_DEFER
    elif record is not None and (not_in_effect := rca_deferral(repo_root, node_id, record.path.name)) == []:
        rca = DEFER_APPLIED
    elif record is not None:   # no marker, or one not in effect (its problems join the refusal)
        why = [applicable_record(repo_root, node_id, str(record.path))[1], *(not_in_effect or [])]
        rca, refused = DEFER_UNAPPLIED, "; ".join(w for w in why if w) or None
    ready = latest_ready(repo_root, node_id) if budget is not None else None
    agent = ready.data.get("agent") if ready else None
    reviewers = set(_available(config, "reviewer"))
    blockers = [r.data["model"] for r in loop.rounds[-1].records if r.data["verdict"] == "block"] if loop.rounds else []
    analysts = _available(config, "reviewer", rca_parties(repo_root, node_id, loop)) if budget is not None else []
    return Facts(node_id, None if budget is None else int(budget), blocking, blocked, rca, record, refused,
                 analysts[0] if analysts else None, agent if agent in _available(config, "executor") else None,
                 next((m for m in blockers if m in reviewers), None),
                 (reviews_dir(repo_root, node_id) / PACKET_NAME).is_file())


def fix_round_budget(repo_root: Path, config: dict[str, Any], loop: LoopState, node_id: str,
                     blocked: bool) -> dict[str, Any] | None:
    """``None`` when ``policy.max_fix_rounds`` is unset (status unchanged); else the budget, the state row,
    and its step. ``spent`` stays true while the budget is spent and any counted review blocks."""
    f = facts(repo_root, config, loop, node_id, blocked)
    state = classify(f)
    if state.name == "budget_unset":
        return None
    step = state.step(f)
    return {"max_fix_rounds": f.budget, "blocking_rounds": f.blocking_rounds,
            "spent": f.blocking_rounds >= f.budget and blocked, "state": state.name, "step": step.kind,
            "next": step.next, "next_why": step.why}
