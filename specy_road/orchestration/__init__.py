"""Orchestration's public interface: what the review gate, the CLI and the PM GUI import.

Callers outside this package import from ``specy_road.orchestration`` only, never a module
inside it (``scripts/check_import_layers.py`` lists any that do). :func:`snapshot` is the
read-only state model, schema 1 (``tests/fixtures/orchestration_snapshot_v1.json``,
``docs/orchestration.md``); :func:`read_state` is the same read for readers that need the worker
records themselves (``worker list``, doctor's claim report). Writes stay in the modules that make
them today.
"""

from __future__ import annotations

from specy_road.orchestration.state import OrchestrationState, read_state, snapshot

__all__ = ["OrchestrationState", "read_state", "snapshot"]
