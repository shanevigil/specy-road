"""Opt-in ``policy.reviewer_resumed_delta``: delta approvals may waive ``reviewer_fresh_session``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.orchestration_config import effective_config
from specy_road.review_files import ReviewFile
from specy_road.review_policy_ref import policy_source


def fresh_session_problem(policy: dict[str, Any], data: dict[str, Any]) -> str | None:
    """Why ``reviewer_fresh_session`` keeps the record from counting, else ``None`` when it passes or is waived."""
    if not policy.get("reviewer_fresh_session", True) or data.get("fresh_session"):
        return None
    if policy.get("reviewer_resumed_delta") and data.get("delta_from"):
        return None
    base = "policy requires a fresh reviewer session (fresh_session: true)"
    if data.get("delta_from"):
        return f"{base}; enable policy.reviewer_resumed_delta to allow a resumed session for this delta approval"
    if policy.get("reviewer_resumed_delta"):
        return f"{base}; reviewer_resumed_delta applies only to approvals naming delta_from"
    if policy.get("delta_review", True):
        return f"{base}; a resumed delta approval would require policy.reviewer_resumed_delta: true"
    return base


def _resumed_delta_on(root: Path) -> bool:
    ref, err = policy_source(root)
    if err:
        return False
    config, _ = effective_config(root, ref)
    return bool(config["policy"].get("reviewer_resumed_delta"))


def delta_session_lines(root: Path, node: dict[str, Any], model: str, commit: str | None) -> list[str]:
    """When ``model`` reads a delta packet, say whether a resumed session may attest ``fresh_session: false``."""
    from specy_road.review_gate import delta_basis

    if delta_basis(root, node, model, commit)[0] is None:
        return []
    if _resumed_delta_on(root):
        return [
            "This round is a **delta review** of the change since your earlier approval. You may resume "
            "the session that read this packet: set `fresh_session: false` and name `delta_from` as the packet "
            "describes.",
            "",
        ]
    return [
        "This round is a **delta review**; the default policy still requires `fresh_session: true` "
        "(a session that saw only this packet). A maintainer may enable `policy.reviewer_resumed_delta` "
        "so a resumed session can approve when you name `delta_from`.",
        "",
    ]


def delta_section_lines(prior: ReviewFile, root: Path) -> list[str]:
    """The **Delta review** section for ``build_packet`` when ``prior`` is set."""
    sha, model = prior.data["commit"], prior.data["model"]
    resumed = _resumed_delta_on(root)
    session = (
        "You may resume the session that read this packet: set `fresh_session: false` and "
        if resumed else
        "Use a fresh session (`fresh_session: true`); enable `policy.reviewer_resumed_delta` to allow "
        "`fresh_session: false` when you resume. Set "
    )
    return ["## Delta review", "", f"`{model}`, you approved `{sha}`. This packet covers only the change since: "
            "at most three documentation or test files inside the touch zones, with no integrity findings. "
            f"{session}`delta_from: \"{sha}\"` in your record's front matter; the gate counts it only for `{model}`.", "",
            f"### Your notes on `{sha}`", "", prior.body.strip() or "_(none)_", ""]
