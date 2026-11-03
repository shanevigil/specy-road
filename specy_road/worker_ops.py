"""Operations behind ``specy-road worker`` (slice 7c): one lifecycle step per function, :class:`WorkerError` for the CLI.

``delegate`` runs after pickup (registry claim with a branch). The worktree is the coordinator checkout on
that branch, else ``work/.worktrees/<codename>``.

The steps live in :mod:`worker_ops_launch` (delegate), :mod:`worker_ops_message` (message, resume,
interrupt), :mod:`worker_ops_slots` (dead wrappers, stalls, the ``max_workers`` cap) and
:mod:`worker_ops_lifecycle` (terminate, adopt), so leaves that change one step do not collide; every name
is re-exported here, and the CLI and tests import this module.
"""

from __future__ import annotations

import sys
import types

from specy_road import worker_ops_launch, worker_ops_lifecycle, worker_ops_message, worker_ops_slots
from specy_road.worker_adapters import Unsupported  # re-exported
from specy_road.worker_lease import handoff, interventions_path, reclaim, record_hook_prompt  # re-exported
from specy_road.worker_ops_launch import (  # re-exported
    _brief_into,
    _check_eligible,
    _check_tree,
    _cli_for,
    _entry_and_harness,
    _launch_locked,
    _preflight,
    _target,
    _worktree_for,
    delegate,
)
from specy_road.worker_ops_lifecycle import _terminate_locked, adopt, terminate  # re-exported
from specy_road.worker_ops_message import CONTINUE_PROMPT, _send, interrupt, message, resume  # re-exported
from specy_road.worker_ops_slots import (  # re-exported
    _slot_or_existing,
    _wrapper_gone,
    sweep_dead_wrappers,
    sweep_stalled,
)
from specy_road.worker_process import process_alive, wrapper_gone  # re-exported: tests patch them here
from specy_road.worker_reconcile import dismiss, reconcile, sync  # re-exported; the CLI calls ops.reconcile/ops.sync
from specy_road.worker_runner import spawn  # re-exported: tests patch it here
from specy_road.worker_state import WorkerError, WorkerRecord  # re-exported

_PARTS = (worker_ops_launch, worker_ops_message, worker_ops_slots, worker_ops_lifecycle)


class _Facade(types.ModuleType):
    """Setting a name here (``monkeypatch.setattr(ops, "spawn", ...)``) sets it in every part that has it, as
    when the steps shared this one namespace; ``monkeypatch`` undoes it the same way."""

    def __setattr__(self, name: str, value: object) -> None:
        for part in _PARTS:
            if not name.startswith("__") and name in vars(part):   # a part's __file__ etc. stay its own
                setattr(part, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _Facade
