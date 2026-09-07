"""Event emission and stable exit codes for ``specy-road grind-session``.

Exit codes (documented contract for automations / CI wrappers):

* 0  session ended normally (bound reached or no actionable work left)
* 1  generic failure (implement hook or finish failed)
* 2  no actionable leaves at start
* 3  blocked on a dependency or gate — human action required
* 4  --pre-finish-cmd failed
* 5  pickup (do-next-available-task) register/commit/git failed
* 6  nothing pickable because this worktree already holds a claim

6 is deliberately not folded into 3. A dependency block needs a human to go do
something else; an open claim needs ``finish-this-task`` or
``abort-task-pickup`` and a re-run, which a supervisor can drive unattended.
Widening 3 to cover both would silently change what it means for the external
supervisors already built against these codes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_NO_LEAVES = 2
EXIT_BLOCKED = 3
EXIT_PRE_FINISH_FAILED = 4
EXIT_PICKUP_FAILED = 5
EXIT_IN_FLIGHT = 6


def _now_iso() -> str:
    """UTC, to the second. Monkeypatched in tests to freeze event timestamps."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EventEmitter:
    """Emit structured (``--json``) or human-readable session events."""

    def __init__(self, *, as_json: bool) -> None:
        self.as_json = as_json

    def emit(self, event: str, **fields) -> None:
        if self.as_json:
            payload = {"event": event, "ts": _now_iso(), **fields}
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
        if event == "in_flight":
            return _human_in_flight(prefix, node, fields)
        if event == "resumed":
            return f"{prefix}: {node} -> {fields.get('branch')}"
        if event == "hook_failed":
            return (
                f"{prefix}: phase={fields.get('phase')} "
                f"node={node} rc={fields.get('rc')}"
            )
        if event == "stopped":
            return f"{prefix}: {fields.get('reason')}" + (f" at {node}" if node else "")
        if event == "plan":
            return fields.get("text", prefix)
        if event == "cleanup":
            return _human_cleanup(prefix, fields)
        if event == "usage_limited":
            minutes = int(fields.get("wait_seconds", 0) // 60)
            return (
                f"{prefix}: {node} — the implementer hit a usage limit that "
                f"resets at {fields.get('reset_at')}. Waiting {minutes} min, "
                f"then resuming (attempt {fields.get('attempt')})."
            )
        if event == "implementer_vanished":
            return (
                f"{prefix}: {node} — the implement command exited "
                f"{fields.get('rc')} without printing anything, so something "
                "outside the run killed it. Re-running in "
                f"{fields.get('retry_in_seconds')}s (attempt "
                f"{fields.get('attempt')} of {fields.get('max_retries')})."
            )
        return f"{prefix}: {fields}"


def _human_in_flight(prefix: str, node, fields: dict) -> str:
    """Why the loop stopped, when the answer is "you already hold a claim".

    Names the node and its branch, because the whole complaint this replaces
    was that the operator was told to look at a dependency while the actual
    blocker was a claim of their own sitting one command away from resolution.
    """
    lines = [
        f"{prefix}: nothing pickable — this worktree already holds a claim on "
        f"{node} ({fields.get('branch') or '?'})."
    ]
    others = fields.get("others") or []
    if others:
        lines.append(f"  also claimed here: {', '.join(others)}")
    lines.append(
        "  finish it (specy-road finish-this-task), release it "
        "(specy-road abort-task-pickup), or re-run with --resume-in-flight."
    )
    return "\n".join(lines)


def _human_cleanup(prefix: str, fields: dict) -> str:
    """The end-of-session line: where we ended up, and what was tidied away."""
    local = fields.get("deleted_local") or []
    remote = fields.get("deleted_remote") or []
    where = (
        f"on {fields.get('integration_branch')}"
        if fields.get("checked_out")
        else f"could NOT return to {fields.get('integration_branch')}"
    )
    lines = [f"{prefix}: {where}; deleted {len(local)} local / {len(remote)} remote branch(es)"]
    for failure in fields.get("failed") or []:
        lines.append(
            f"  warning: {failure.get('step')} {failure.get('branch')}: "
            f"{failure.get('message')}"
        )
    for warning in fields.get("warnings") or []:
        lines.append(f"  {warning}")
    hint = fields.get("hint")
    if hint:
        lines.append(f"  to clean up the branches this session merged: {hint}")
    return "\n".join(lines)
