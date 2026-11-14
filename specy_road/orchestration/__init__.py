"""Orchestration's public interface: what the review gate, the CLI and the PM GUI import.

Callers outside this package import from ``specy_road.orchestration`` only, never a module
inside it (``scripts/check_import_layers.py`` lists any that do). :func:`snapshot` is the
read-only state model, schema 1 (``tests/fixtures/orchestration_snapshot_v1.json``,
``docs/orchestration.md``); :func:`read_state` is the same read for readers that need the worker
records themselves (``worker list``, doctor's claim report); :func:`read_claims` is its claim
read alone, which the readiness rule takes (``specy_road.orchestration.claims``, so the planner
does not import the worker modules). Writes stay in the modules that make
them today.

The worker runtime lives in ``specy_road.orchestration.workers``; the names the gate, the CLI
entry points and the GUI take from it are served here too (:data:`_SOURCES`). Every name loads on
first use (:func:`__getattr__`, PEP 562) from the one module that defines it: importing a worker
module does not import :mod:`specy_road.orchestration.state`, which imports modules
(``chore_records``, ``orphaned_claims``) that import the worker modules, and reading
:func:`read_claims` still imports no worker module.
"""

from __future__ import annotations

import importlib
from typing import Any

#: Defining module (relative to this package) -> the names served from it.
_SOURCES: dict[str, tuple[str, ...]] = {
    "claims": ("read_claims",),
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
    "ADAPTERS", "CODEX_MEMORY_OFF", "HARNESSES", "HELD_STATES", "LeaseError", "OrchestrationState",
    "Unsupported", "WorkerError", "add_sync_parser", "add_terminate", "begin_op", "cmd_sync",
    "complete_op", "end_finished_workers", "events_since", "force_warnings", "list_records",
    "list_view", "load_record", "log_path", "lookup_op", "project_root_from_worktree",
    "read_claims",
    "read_state", "reconcile_lines", "recover_stalled", "render_command", "snapshot", "stall_lines",
    "stalled_workers", "sync_marks", "timeline", "timeline_lines", "usage", "usage_json_payload",
    "usage_lines", "worker_ops", "workers_dir",
]


def __getattr__(name: str) -> Any:
    """Load ``name`` from the module that defines it; a ``workers`` submodule is served whole."""
    source = _SOURCE_OF.get(name)
    if source is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if source == "workers":
        return importlib.import_module(f"{__name__}.workers.{name}")
    return getattr(importlib.import_module(f"{__name__}.{source}"), name)
