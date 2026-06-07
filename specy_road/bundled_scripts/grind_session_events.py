"""Event emission and stable exit codes for ``specy-road grind-session``.

Exit codes (documented contract for automations / CI wrappers):

* 0  session ended normally (bound reached or no actionable work left)
* 1  generic failure (implement hook or finish failed)
* 2  no actionable leaves at start
* 3  blocked on a dependency or gate — human action required
* 4  --pre-finish-cmd failed
* 5  pickup (do-next-available-task) register/commit/git failed
"""

from __future__ import annotations

import json
import sys

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_NO_LEAVES = 2
EXIT_BLOCKED = 3
EXIT_PRE_FINISH_FAILED = 4
EXIT_PICKUP_FAILED = 5


class EventEmitter:
    """Emit structured (``--json``) or human-readable session events."""

    def __init__(self, *, as_json: bool) -> None:
        self.as_json = as_json

    def emit(self, event: str, **fields) -> None:
        if self.as_json:
            payload = {"event": event, **fields}
            print(json.dumps(payload, sort_keys=False), flush=True)
            return
        print(self._human(event, fields), flush=True)

    @staticmethod
    def _human(event: str, fields: dict) -> str:
        node = fields.get("node_id")
        prefix = f"[grind-session] {event}"
        if event == "picked":
            return f"{prefix}: {node} -> {fields.get('branch')}"
        if event == "implementing":
            return f"{prefix}: {node} ({fields.get('mode')})"
        if event == "pre_finish":
            return f"{prefix}: {node}"
        if event == "finished":
            extra = f" -> {fields.get('merged_to')}" if fields.get("merged_to") else ""
            return f"{prefix}: {node}{extra}"
        if event == "blocked":
            wait = ", ".join(fields.get("waiting_on") or []) or "?"
            return (
                f"{prefix}: {fields.get('reason')} — "
                f"{fields.get('count', 0)} leaf/leaves waiting (e.g. on {wait}). "
                "Human action required."
            )
        if event == "hook_failed":
            return (
                f"{prefix}: phase={fields.get('phase')} "
                f"node={node} rc={fields.get('rc')}"
            )
        if event == "stopped":
            return f"{prefix}: {fields.get('reason')}" + (f" at {node}" if node else "")
        if event == "plan":
            return fields.get("text", prefix)
        return f"{prefix}: {fields}"


def fail(emitter: EventEmitter, reason: str, code: int, **fields) -> int:
    """Emit a ``stopped`` event with ``reason`` and return ``code``."""
    emitter.emit("stopped", reason=reason, **fields)
    return code
