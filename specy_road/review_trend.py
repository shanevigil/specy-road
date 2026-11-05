"""A review loop's findings trend, and whether it is converging.

Per round (``review_rca.review_rounds``): the **blocking findings** (every item in
the four finding categories of each blocking record, summed across records) and
the **failing acceptance ids**. A loop is **converging** when, over its last
``n = escalate_same_acceptance_blocks`` rounds, the count never rose, fell at
least once, and the latest round fails no acceptance id. Fewer than ``n`` rounds
(or any of them with an unknown count) is not enough evidence: never converging. While it converges,
``review_rca.escalation`` defers its ``same_family`` and ``review_rounds`` rules
unless ``policy.escalate_when_converging`` is true. Design:
``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

from typing import Any, Sequence

from specy_road.review_deferral import CATEGORIES


def round_findings(rnd: Any) -> int | None:
    """Blocking findings in one round: all four categories of every blocking record.

    ``None`` (unknown) when a blocking record lacks a list for any category; the schema requires all four.
    """
    lists = [(r.data.get("findings") or {}).get(c) for r in rnd.records if r.data["verdict"] == "block"
             for c in CATEGORIES]
    return None if any(not isinstance(x, list) for x in lists) else sum(map(len, lists))


def _ids(ids: set[str]) -> list[str]:
    return sorted(ids, key=lambda a: int(a[1:]))


def converging(rounds: Sequence[Any], n: int) -> bool:
    """Over the last ``n`` rounds the count never rose and fell at least once; the latest fails no id.

    Needs ``n`` (at least 2) rounds, each with a known count; with fewer the loop is not converging.
    """
    if n < 2 or len(rounds) < n:
        return False
    counts = [round_findings(r) for r in rounds[-n:]]
    if any(c is None for c in counts):
        return False
    steps = list(zip(counts, counts[1:]))
    return all(b <= a for a, b in steps) and any(b < a for a, b in steps) and not rounds[-1].failed


def _line(rounds: Sequence[Any], counts: list[int | None]) -> str:
    head = "findings by round: " + ", ".join("?" if c is None else str(c) for c in counts)
    if rounds[-1].failed:
        return f"{head}; round {len(rounds)} fails {', '.join(_ids(rounds[-1].failed))}"
    since = len(rounds)
    while since > 1 and not rounds[since - 2].failed:
        since -= 1
    return f"{head}; acceptance all pass since round {since}"


def trend_status(rounds: Sequence[Any], is_converging: bool, deferred: bool) -> dict[str, Any]:
    """``handoff status``'s ``findings_trend``: one entry per round, the loop's state and the lines it prints."""
    per = [{"round": i, "findings": round_findings(r), "failing_acceptance": _ids(r.failed)}
           for i, r in enumerate(rounds, 1)]
    lines = [_line(rounds, [p["findings"] for p in per])] if rounds else []
    if deferred:
        lines.append("converging; escalation deferred (policy.escalate_when_converging is false)")
    return {"rounds": per, "converging": is_converging, "escalation_deferred": deferred, "lines": lines}
