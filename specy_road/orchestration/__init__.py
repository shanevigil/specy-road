"""Orchestration's public interface: what the review gate, the CLI and the PM GUI import.

Callers outside this package import from ``specy_road.orchestration`` only, never a module
inside it (``scripts/check_import_layers.py`` lists any that do). :func:`snapshot` is the
read-only state model, schema 1 (``tests/fixtures/orchestration_snapshot_v1.json``,
``docs/orchestration.md``); :func:`read_state` is the same read for readers that need the worker
records themselves (``worker list``, doctor's claim report); :func:`read_claims` is its claim
read alone, which the readiness rule takes (``specy_road.orchestration.claims``, so the planner
does not import the worker modules). Writes stay in the modules that make
them today.

The worker runtime lives in ``specy_road.orchestration.workers``, harness facts and binaries in
``specy_road.orchestration.harness``, and the chore, decision and lesson records in
``specy_road.orchestration.records``; the roster, model profiles, leaf assignment and the
role-prompt library are modules of this package (``DESTINATIONS.md`` lists where each came from).
The names the gate, the CLI entry points and the GUI take from them are served here too
(:data:`_SOURCES`). Every name loads on first use (:func:`__getattr__`, PEP 562) from the one module
that defines it: importing a worker module does not import :mod:`specy_road.orchestration.state`,
which imports modules (``records.chore_records``, ``orphaned_claims``) that import the worker
modules, and reading :func:`read_claims` still imports no worker module.
"""

from __future__ import annotations

import importlib
from typing import Any

#: Defining module (relative to this package) -> the names served from it.
_SOURCES: dict[str, tuple[str, ...]] = {
    "claims": ("read_claims",),
    "harness": ("harness_facts",),
    "model_profiles": (
        "DEFAULT_MAX_AGE_DAYS", "GUIDANCE_BYPASS_KEY", "PROFILES_REL", "Profile", "ROLES",
        "display_rel", "list_profiles", "load_profile", "unmatched_roster_ids",
    ),
    "orchestrate_assign": (
        "ANY", "entry_may_process", "guidance_bypass_lines", "guidance_bypass_refusal",
        "guidance_bypass_warning", "guidance_problem", "is_available", "may_handle",
        "node_eligibility", "node_sensitivity", "unavailability_reason", "unavailable_prompt_error",
    ),
    "orchestrate_plan": ("OrchestrationPlan", "build_orchestration_plan"),
    "records.chore_garden_due": ("warn_garden_due",),
    "records.chore_records": (
        "_SLUG", "chore_node", "chore_prompt", "chore_target", "chores_dir", "load_chore",
        "open_chore",
    ),
    "records.decisions": (
        "DECISIONS_REL", "LOCAL", "PREFERENCE", "SHARED", "STANDING_RULE", "active_preferences",
        "add_entry", "add_preference", "close_entry", "coordinator_decision_lines",
        "decisions_path", "format_open_entry", "format_preference", "load_merged", "next_free_id",
        "open_questions", "read_decisions",
    ),
    "records.review_lessons": (
        "LESSONS_REL", "add_lesson", "format_lesson", "lessons_path", "read_lessons",
        "reviewer_lesson_lines",
    ),
    "role_prompt_cli": (
        "READ_BACK_HARNESSES", "claimed_worktree", "preflight", "resolve_cli",
        "reviewer_launch_block", "reviewer_turn", "run_plain_cli",
    ),
    "role_prompt_rca": (
        "DATA_LINE", "coordinator_preamble", "executor_preamble", "fix_check_lines", "precondition",
        "profile_lines", "reviewer_preamble",
    ),
    "role_prompt_rework": ("rework_check", "rework_lines"),
    "roster_generate": (
        "format_entries", "missing_profile_files", "roster_entries", "write_entries",
    ),
    "state": ("OrchestrationState", "read_state", "snapshot"),
    "workers": ("worker_ops",),
    "workers.worker_adapter_codex": ("CODEX_MEMORY_OFF",),
    "workers.worker_adapter_parsers": ("project_root_from_worktree",),
    "workers.worker_adapters": ("ADAPTERS", "Unsupported", "force_warnings"),
    "workers.worker_cli_render": (
        "_line", "_row", "timeline", "timeline_lines", "usage", "usage_json_payload", "usage_lines",
    ),
    "workers.worker_cli_sync": ("add_sync_parser", "cmd_sync"),
    "workers.worker_lock": ("workers_dir",),
    "workers.worker_ops": ("recover_stalled", "stall_lines", "stalled_workers"),
    "workers.worker_orphans": ("HELD_STATES", "add_terminate", "end_finished_workers", "list_view"),
    "workers.worker_outbox": ("lookup_op",),
    "workers.worker_reconcile": ("reconcile_lines", "sync_marks"),
    "workers.worker_runner": ("log_path",),
    "workers.worker_sessions": ("render_command",),
    "workers.worker_state": (
        "HARNESSES", "LeaseError", "WorkerError", "begin_op", "complete_op", "events_since",
        "list_records", "load_record",
    ),
}
_SOURCE_OF = {name: source for source, names in _SOURCES.items() for name in names}

__all__ = [
    "ADAPTERS", "ANY", "CODEX_MEMORY_OFF", "DATA_LINE", "DECISIONS_REL", "DEFAULT_MAX_AGE_DAYS",
    "GUIDANCE_BYPASS_KEY", "HARNESSES", "HELD_STATES", "LESSONS_REL", "LOCAL", "LeaseError",
    "OrchestrationPlan", "OrchestrationState", "PREFERENCE", "PROFILES_REL", "Profile",
    "READ_BACK_HARNESSES", "ROLES", "SHARED", "STANDING_RULE", "Unsupported", "WorkerError",
    "active_preferences", "add_entry", "add_lesson", "add_preference", "add_sync_parser",
    "add_terminate", "begin_op", "build_orchestration_plan", "chore_node", "chore_prompt",
    "chore_target", "chores_dir", "claimed_worktree", "close_entry", "cmd_sync", "complete_op",
    "coordinator_decision_lines", "coordinator_preamble", "decisions_path", "display_rel",
    "end_finished_workers", "entry_may_process", "events_since", "executor_preamble",
    "fix_check_lines", "force_warnings", "format_entries", "format_lesson", "format_open_entry",
    "format_preference", "guidance_bypass_lines", "guidance_bypass_refusal",
    "guidance_bypass_warning", "guidance_problem", "harness_facts", "is_available", "lessons_path",
    "list_profiles", "list_records", "list_view", "load_chore", "load_merged", "load_profile",
    "load_record", "log_path", "lookup_op", "may_handle", "missing_profile_files", "next_free_id",
    "node_eligibility", "node_sensitivity", "open_chore", "open_questions", "precondition",
    "preflight", "profile_lines", "project_root_from_worktree", "read_claims", "read_decisions",
    "read_lessons", "read_state", "reconcile_lines", "recover_stalled", "render_command",
    "resolve_cli", "reviewer_launch_block", "reviewer_lesson_lines", "reviewer_preamble",
    "reviewer_turn", "rework_check", "rework_lines", "roster_entries", "run_plain_cli", "snapshot",
    "stall_lines", "stalled_workers", "sync_marks", "timeline", "timeline_lines",
    "unavailability_reason", "unavailable_prompt_error", "unmatched_roster_ids", "usage",
    "usage_json_payload", "usage_lines", "warn_garden_due", "worker_ops", "workers_dir",
    "write_entries",
]


def __getattr__(name: str) -> Any:
    """Load ``name`` from the module that defines it; a ``workers`` or ``harness`` submodule is
    served whole."""
    source = _SOURCE_OF.get(name)
    if source is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if source in ("workers", "harness"):
        return importlib.import_module(f"{__name__}.{source}.{name}")
    return getattr(importlib.import_module(f"{__name__}.{source}"), name)
