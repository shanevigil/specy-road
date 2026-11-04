"""Opt-in ``policy.reviewer_resumed_delta``: a delta approval may waive ``reviewer_fresh_session`` (M11.36).

A reviewer that approved a commit and is resumed for the next small fix round
attests ``fresh_session: false``. With the key on (default off) such a record
still counts when it names ``delta_from``: the gate then holds it to the delta
rules of :func:`review_gate.delta_problem` like any delta approval. Any other
approval without ``fresh_session: true`` is still refused. Split out of
``review_gate`` to keep that module under its file-limits cap.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from specy_road.orchestration_config import effective_config
from specy_road.review_files import ReviewFile
from specy_road.review_policy_ref import policy_source

FRESH_SESSION = "policy requires a fresh reviewer session (fresh_session: true)"
RESUMED_KEY = "policy.reviewer_resumed_delta"


def fresh_session_problem(policy: dict[str, Any], data: dict[str, Any], other: str | None) -> str | None:
    """Why a record does not count given ``other``, the reason from the gate's remaining checks.

    Exactly :data:`FRESH_SESSION` when ``reviewer_fresh_session`` is the only reason; ``other`` alone when the
    session passes or ``reviewer_resumed_delta`` waives it for an approval naming ``delta_from``.
    """
    waived = policy.get("reviewer_resumed_delta") and data.get("delta_from")
    if not policy.get("reviewer_fresh_session", True) or data.get("fresh_session") or waived:
        return other
    return f"{FRESH_SESSION}; {other}" if other else FRESH_SESSION


def fresh_only_note(repo_root: Path, config: dict[str, Any], node: dict[str, Any], review: ReviewFile,
                    commit: str | None, today: date | None = None) -> str:
    """The ``handoff status`` reason for a record refused only for ``fresh_session``: says so, and whether a
    resumed delta approval from the same model would count at ``commit`` (and under which policy)."""
    from specy_road.review_gate import _delta_why, delta_problem, prior_approvals

    model, policy, base = review.data["model"], config["policy"], review.data.get("delta_from")
    priors = prior_approvals(repo_root, config, node, model, commit, today)
    head = f"{FRESH_SESSION}, the only reason it does not count"
    if review.data["verdict"] != "approve":   # the delta rules gate approvals only; a waived block always counts
        return (f"{head}; with {RESUMED_KEY}: true this resumed block would count" if base else
                f"{head}; a resumed block counts only when it names delta_from"
                + ("" if policy.get("reviewer_resumed_delta") else f" and {RESUMED_KEY} is on"))
    if base:   # naming delta_from with fresh_session false is refused only while the key is off
        why = _delta_why(repo_root, node, priors, review, commit, policy)
        return (f"{head}; with {RESUMED_KEY}: true this resumed delta approval would count" if why is None else
                f"{head}; with {RESUMED_KEY}: true it would still not count: {why}")
    why = "no earlier approval" if not priors else delta_problem(
        repo_root, node, priors[-1].data["commit"], commit, policy)
    if why:
        return f"{head}; a resumed delta approval would not count either ({why}): a fresh full review is needed"
    sha = priors[-1].data["commit"]
    when = "" if policy.get("reviewer_resumed_delta") else f" with {RESUMED_KEY}: true"
    return f"{head}; a resumed delta approval naming delta_from: {sha} would count{when}"


def resumed_delta_on(root: Path) -> bool:
    """Whether the effective policy (as the gate reads it) turns ``reviewer_resumed_delta`` on; fails closed."""
    ref, err = policy_source(root)
    if err:
        return False
    config, err = effective_config(root, ref)
    return not err and bool(config["policy"].get("reviewer_resumed_delta"))

