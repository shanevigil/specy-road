"""Registry claims no live worker, live session or READY at the branch tip is working (M15.26).

A claim pickup left behind blocks every overlapping leaf and, until this report, nothing said so.
``completed``, ``failed`` and ``terminated`` are not a live worker: the same states
:data:`specy_road.worker_orphans.SLOT_STATES` counts toward ``policy.max_workers``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from specy_road.git_subprocess import git_text
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.review_files import latest_ready
from specy_road.review_target import same_commit
from specy_road.session_presence import list_sessions
from specy_road.worker_orphans import SLOT_STATES
from specy_road.worker_state import list_records


def stays_claimed(node_id: str) -> str:
    """The sentence a failed delegate and an implement ``hook_failed`` line both end with."""
    return (f"{node_id} stays claimed with no worker: retry `specy-road worker delegate {node_id}` "
            f"or release it with `specy-road abort-task-pickup`")


def append_claim_hint(repo_root: Path, node_id: str | None, message: str) -> str:
    """``message``, plus :func:`stays_claimed`, when ``node_id`` is claimed and has no live worker."""
    if not node_id or not _claimed(repo_root, node_id) or _live_worker(repo_root, node_id):
        return message
    return f"{message}; {stays_claimed(node_id)}"


def orphaned_claims(repo_root: Path) -> list[dict[str, str]]:
    """Each claim with no live worker on its leaf, no live session on its branch, and no valid READY at the tip.

    ``age`` is from the branch's last commit, else the registry row's ``started`` date. ``since`` is that
    timestamp, or ``""`` when neither exists.
    """
    now = datetime.now(timezone.utc)
    records = list_records(repo_root)
    sessions = {s.branch for s in list_sessions(repo_root) if s.branch}
    out = []
    for entry in _entries(repo_root):
        node_id, branch = str(entry["node_id"]), str(entry["branch"])
        if _live_worker_in(records, node_id) or branch in sessions or _ready_at_tip(repo_root, node_id, branch):
            continue
        when = _branch_time(repo_root, branch) or _parse_when(entry.get("started"))
        out.append({
            "node_id": node_id,
            "codename": str(entry.get("codename") or ""),
            "branch": branch,
            "age": relative_age(when, now) if when else "unknown",
            "since": when.isoformat() if when else "",
        })
    return out


def report_lines(claims: list[dict[str, str]]) -> list[str]:
    """One line per claim: its age and the two commands that resolve it."""
    return [
        f"{c['node_id']} ({c['branch']}, {c['age']}): `specy-road worker delegate {c['node_id']}` to resume work, "
        f"or `specy-road abort-task-pickup` to release it"
        for c in claims
    ]


def _entries(repo_root: Path) -> list[dict]:
    raw = read_registry(registry_path(repo_root)).get("entries") or []
    return [e for e in raw if isinstance(e, dict) and e.get("node_id") and e.get("branch")]


def _claimed(repo_root: Path, node_id: str) -> bool:
    return any(str(e["node_id"]) == node_id for e in _entries(repo_root))


def _live_worker(repo_root: Path, node_id: str) -> bool:
    return _live_worker_in(list_records(repo_root), node_id)


def _live_worker_in(records, node_id: str) -> bool:
    return any(r.node_id == node_id and r.state in SLOT_STATES for r in records)


def _ready_at_tip(repo_root: Path, node_id: str, branch: str) -> bool:
    ready = latest_ready(repo_root, node_id, branch)
    tip = git_text(["rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}"], repo_root)
    return ready is not None and bool(tip) and same_commit(repo_root, str(ready.data.get("commit") or ""), tip)


def _branch_time(repo_root: Path, branch: str) -> datetime | None:
    raw = git_text(["log", "-1", "--format=%cI", branch], repo_root)
    return _parse_when(raw) if raw else None


def _parse_when(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 10:
        text += "T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def relative_age(when: datetime, now: datetime) -> str:
    """Format elapsed time as ``Nd``, ``Nh``, ``Nm``, or ``under 1m`` (shared with refusal markers)."""
    seconds = max(0, int((now - when).total_seconds()))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "under 1m"
