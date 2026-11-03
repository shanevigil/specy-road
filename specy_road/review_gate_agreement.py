"""Whether the two review-gate settings agree.

``roadmap/orchestration.yaml`` says how many reviewers a leaf needs;
``require_implementation_review_before_finish`` in ``roadmap/git-workflow.yaml``
says whether ``finish-this-task`` enforces them. With the first asking for
reviewers and the second off, ``review list`` reports a gate that finish never
checks, so finish lands the leaf with the gate unmet. ``validate`` and ``doctor``
report that as an error. Nothing turns the gate on: that is the project's call.

The gate counts as on by :func:`review_gate.review_required`, the rule finish
uses (working tree or integration branch, failing closed). A missing
``orchestration.yaml`` asks for no reviewers here: the file is optional, and a
repo without one has stated no review policy. An unreadable one is left to the
commands that report its error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.git_workflow_config import GIT_WORKFLOW_REL
from specy_road.orchestration_config import DEFAULT_POLICY, ORCHESTRATION_REL, load_orchestration_config
from specy_road.review_gate import review_required

GATE_KEY = "require_implementation_review_before_finish"
#: The fix the mismatch message names, also printed by ``mark-implementation-reviewed``.
GATE_FIX = f"set `{GATE_KEY}: true` in {GIT_WORKFLOW_REL.as_posix()}"


def gate_config_mismatch(repo_root: Path, *, gate_on: bool | None = None) -> str | None:
    """The error when ``orchestration.yaml`` requires reviewers but finish does not enforce them, else ``None``.

    ``gate_on`` is :func:`review_required` when the caller already has it.
    """
    data, err = load_orchestration_config(repo_root)
    if err or data is None:
        return None
    required = int({**DEFAULT_POLICY, **(data.get("policy") or {})}["reviewers_required"])
    if review_required(repo_root) if gate_on is None else gate_on:
        return None
    return (
        f"{ORCHESTRATION_REL.as_posix()} requires {required} reviewer(s) (policy.reviewers_required), "
        f"but {GIT_WORKFLOW_REL.as_posix()} leaves {GATE_KEY} off, so finish-this-task does not "
        f"enforce the review gate and would land a leaf without those reviews. Fix: {GATE_FIX}."
    )


def report_gate_mismatch(repo_root: Path) -> bool:
    """Print the mismatch as ``error:`` on stderr; whether there was one."""
    msg = gate_config_mismatch(repo_root)
    if msg:
        print(f"error: {msg}", file=sys.stderr)
    return msg is not None
