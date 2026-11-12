"""One read of orchestration state: claims, workers, worktrees and reviews, per leaf.

:func:`read_state` reads every source once; :func:`snapshot` turns that into the schema-2 document
(``tests/fixtures/orchestration_snapshot_v2.json``, v1 fields unchanged from
``tests/fixtures/orchestration_snapshot_v1.json``). Nothing here writes: no record, registry,
review file, git object or git index changes. Every git call passes ``-c core.fsmonitor=false
-c core.hooksPath=/dev/null`` with ``GIT_OPTIONAL_LOCKS=0``.

Each leaf's status comes from the fixture's truth table, first match wins. The abandoned rule is
M15.26's, stated once in :func:`specy_road.orphaned_claims.orphaned_claims`; the slot states are
:data:`specy_road.worker_orphans.SLOT_STATES`. An unreadable source sets only its own fields to
``unknown``: an unreadable worker record is listed with its id and nothing else, and every status is
judged from the readable records, as the M15.26 report judges them.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from specy_road.chore_records import load_chore
from specy_road.git_subprocess import run
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.orchestration.claims import read_claims
from specy_road.orphaned_claims import orphaned_claims
from specy_road.review_files import ReviewFile, list_ready, list_reviews, latest_ready
from specy_road.review_target import ReviewTargetError, same_commit
from specy_road.worker_orphans import SLOT_STATES
from specy_road.worker_process import wrapper_alive
from specy_road.worker_state import WorkerError, WorkerRecord, events_since, load_record, workers_dir

SCHEMA = 2
UNKNOWN = "unknown"
_ENDED = frozenset({"completed", "failed", "terminated"})
_GIT = ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null")
_CLAUDE_DIR = "CLAUDE_CONFIG_DIR"
_CLAUDE_NAMES = frozenset({"claude", ".claude"})
_READY_KEPT = ("blocked_on:", "node_id is ", "branch is ")
_REVIEW_KEPT = ("authored_fix:", "is_coordinator:", "verdict: approve with", "acceptance:")
_WORKER_UNKNOWN = (
    "harness", "model", "status", "pid_alive", "started_at", "ended_at",
    "account", "last_activity", "flags",
)


@dataclass
class OrchestrationState:
    """What :func:`read_state` read. ``claims`` is ``None`` when the registry cannot be read."""

    repo_root: Path
    records: list[WorkerRecord]
    unreadable_workers: list[str]
    claims: dict[str, dict[str, Any]] | None
    abandoned: list[dict[str, str]]
    worktrees: dict[str, str | None]  # resolved path -> branch, None when detached

    def active_records(self) -> list[WorkerRecord]:
        """The records ``worker list`` shows without ``--all``: not failed or terminated."""
        return [r for r in self.records if r.active]


def read_state(repo_root: Path) -> OrchestrationState:
    """Read worker records, registry claims, the M15.26 claim report and the git worktrees, once.

    The M15.26 report (:func:`orphaned_claims`) reads the registry itself, so it runs only when
    :func:`read_claims` found a readable registry: an unknown registry has no abandoned claims and
    never reaches that second read. Limit: a registry rewritten between the two reads is judged
    from both versions.
    """
    records, unreadable = _records(repo_root)
    claims = read_claims(repo_root)
    abandoned = orphaned_claims(repo_root) if claims is not None else []
    return OrchestrationState(
        repo_root, records, unreadable, claims, abandoned, _git_worktrees(repo_root)
    )


def snapshot(repo_root: Path) -> dict[str, Any]:
    """The schema-2 snapshot: v1 fields plus account, activity, flags, ahead/behind, ready, gate, holds."""
    state = read_state(repo_root)
    listed, gates = _hold_sources(repo_root)
    counts: dict[str | None, tuple[Any, Any]] = {}
    leafless = [
        _worker(state.repo_root, r) for r in state.records if load_chore(repo_root, r.node_id) is not None
    ]
    leafless += [_unreadable_worker(wid) for wid in state.unreadable_workers]
    leaves = {
        nid: _leaf(state, nid, listed, gates, counts) for nid in _leaf_ids(state)
    }
    return {"schema": SCHEMA, "leaves": leaves, "leafless_workers": leafless}


def leaf_status(state: OrchestrationState, node_id: str) -> str:
    """The truth table's status for ``node_id`` (tests/fixtures/orchestration_snapshot_v1.json)."""
    mine = [r for r in state.records if r.node_id == node_id]
    if any(r.state in SLOT_STATES for r in mine):
        return "running"
    if state.claims is None:
        return UNKNOWN
    if any(c["node_id"] == node_id for c in state.abandoned):
        return "abandoned"
    if mine:
        latest = max(mine, key=lambda r: (r.attempt, r.worker_id))
        if latest.state == "completed":
            return "exited_ok"
        if latest.state in _ENDED:
            return "exited_failed"
    return "claimed"


def _records(repo_root: Path) -> tuple[list[WorkerRecord], list[str]]:
    """Every readable worker record, and the ids of those that cannot be read.

    ``list_records`` skips an unreadable record; the snapshot lists it under ``leafless_workers``.
    """
    d = workers_dir(repo_root)
    readable, unreadable = [], []
    for p in sorted(d.glob("w-*.yaml")) if d.is_dir() else []:
        try:
            readable.append(load_record(repo_root, p.stem))
        except WorkerError:
            unreadable.append(p.stem)
    return readable, unreadable


def _git(args: list[str], cwd: Path):
    """One git read: fsmonitor and hooks off, and no optional index lock."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    return run([*_GIT, *args], cwd, env=env)


def _git_out(args: list[str], cwd: Path) -> str | None:
    return _git(args, cwd).text


def _git_worktrees(repo_root: Path) -> dict[str, str | None]:
    """Resolved worktree path -> its branch's short name, or ``None`` when detached."""
    out: dict[str, str | None] = {}
    text = _git_out(["worktree", "list", "--porcelain"], repo_root) or ""
    for block in text.split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in block.splitlines())
        if "worktree" in wt:
            out[str(Path(wt["worktree"]).resolve())] = (
                wt.get("branch", "").removeprefix("refs/heads/") or None
            )
    return out


def _leaf_ids(state: OrchestrationState) -> list[str]:
    ids = set(state.claims or {})
    ids |= {r.node_id for r in state.records if load_chore(state.repo_root, r.node_id) is None}
    return sorted(ids)


def _leaf(
    state: OrchestrationState, node_id: str, listed: Any, gates: list | None,
    counts: dict[str | None, tuple[Any, Any]],
) -> dict[str, Any]:
    entry = None if state.claims is None else state.claims.get(node_id)
    branch = str(entry["branch"]) if entry and entry.get("branch") else None
    mine = [r for r in state.records if r.node_id == node_id]
    # An unreadable registry is already ``claims is None``. The review target reads that file
    # again and raises; the leaf keeps its workers and reviews, with ready and gate unknown.
    ready, gate = (
        (UNKNOWN, _unknown_gate()) if state.claims is None
        else _ready_and_gate(state.repo_root, node_id, branch)
    )
    return {
        "claim": UNKNOWN if state.claims is None else None if entry is None else {
            "codename": str(entry.get("codename") or ""),
            "branch": branch,
            "registered_at": str(entry["started"]) if entry.get("started") else None,
        },
        "workers": [_worker(state.repo_root, r) for r in mine],
        "worktrees": _worktrees(state, branch, mine, counts),
        "reviews": _reviews(state.repo_root, node_id, branch),
        "status": leaf_status(state, node_id),
        "ready": ready,
        "gate": gate,
        "holds": _holds(node_id, listed, gates),
    }


def _worker(repo: Path, rec: WorkerRecord) -> dict[str, Any]:
    return {
        "id": rec.worker_id,
        "harness": rec.harness,
        "model": rec.model,
        "status": rec.state,
        "pid_alive": wrapper_alive(rec),
        "started_at": rec.created,
        "ended_at": rec.updated if rec.state in _ENDED else None,
        "account": _account(repo, rec),
        "last_activity": _last_activity(repo, rec),
        "flags": _flags(rec),
    }


def _unreadable_worker(worker_id: str) -> dict[str, Any]:
    return {"id": worker_id, **dict.fromkeys(_WORKER_UNKNOWN, UNKNOWN)}


def _flags(rec: WorkerRecord) -> list[str]:
    """The record's flags, plus ``paused_by_limit`` while that is the record's state."""
    flags = list(rec.flags)
    if rec.state == "paused_by_limit" and "paused_by_limit" not in flags:
        flags.append("paused_by_limit")
    return flags


def _account(repo: Path, rec: WorkerRecord) -> str | None:
    """Claude profile name from the config dir the record or its roster entry names, else null."""
    raw = _worker_config_dir(repo, rec.worker_id) or _roster_config_dir(repo, rec.model)
    return _profile_name(raw) if raw else None


def _worker_config_dir(repo: Path, worker_id: str) -> str | None:
    """The sandbox record of the config dir this worker ran with, when it is a regular file."""
    from specy_road.worker_sandbox import state_home

    path = state_home(repo, worker_id) / "claude-config-dir"
    text = _regular_text(path)
    return text.strip() if text else None


def _roster_config_dir(repo: Path, model: str) -> str | None:
    """``CLAUDE_CONFIG_DIR=...`` named by the roster entry for ``model``, else none."""
    from specy_road.orchestration_config import load_orchestration_config, roster_entry

    try:
        config, err = load_orchestration_config(repo)
    except (OSError, UnicodeDecodeError):
        return None
    entry = None if err or not config else roster_entry(config, model)
    if not entry:
        return None
    for text in _strings(entry):
        found = _config_assignment(text)
        if found:
            return found
    return None


def _config_assignment(text: str) -> str | None:
    key = _CLAUDE_DIR + "="
    for part in text.replace("\n", " ").split():
        if part.startswith(key):
            return part[len(key):].strip("\"'")
    return None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def _profile_name(raw: str) -> str | None:
    """The directory's name, or its parent's when the directory is ``claude`` or ``.claude``."""
    path = Path(raw).expanduser()
    name = path.name
    if name in _CLAUDE_NAMES:
        name = path.parent.name
    return name or None


def _last_activity(repo: Path, rec: WorkerRecord) -> str | None:
    """The newer of the last event's time and ``last_output_at``."""
    event_at = _last_event_at(repo, rec.worker_id)
    candidates = [(text, when) for text in (event_at, rec.last_output_at) if (when := _when(text))]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])[0]


def _last_event_at(repo: Path, worker_id: str) -> str | None:
    try:
        events = events_since(repo, worker_id, 0)
    except (OSError, UnicodeDecodeError):
        return None
    return max(events, key=lambda ev: ev.seq).at if events else None


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _worktrees(
    state: OrchestrationState, branch: str | None, mine: list[WorkerRecord],
    counts: dict[str | None, tuple[Any, Any]],
) -> list[dict[str, Any]]:
    paths = {p for p, b in state.worktrees.items() if branch and b == branch}
    paths |= {str(Path(r.worktree).resolve()) for r in mine}
    rows = []
    for p in sorted(paths):
        checked = state.worktrees.get(p)
        ahead, behind = _divergence(state.repo_root, checked, counts)
        rows.append({
            "path": p, "branch": checked, "dirty": _dirty(Path(p)), "ahead": ahead, "behind": behind,
        })
    return rows


def _divergence(
    repo: Path, branch: str | None, counts: dict[str | None, tuple[Any, Any]],
) -> tuple[Any, Any]:
    if branch not in counts:
        counts[branch] = _ahead_behind(repo, branch)
    return counts[branch]


def _ahead_behind(repo: Path, branch: str | None) -> tuple[Any, Any]:
    """Commits the worktree's branch is ahead of and behind the local integration ref."""
    if not branch:
        return UNKNOWN, UNKNOWN
    base, _remote, _warnings = resolve_integration_defaults(
        repo, explicit_base=None, explicit_remote=None,
    )
    if _git_out(["rev-parse", "--verify", "--quiet", f"refs/heads/{base}"], repo) is None:
        return UNKNOWN, UNKNOWN
    return _count(repo, f"{base}..{branch}"), _count(repo, f"{branch}..{base}")


def _count(repo: Path, spec: str) -> Any:
    text = _git_out(["rev-list", "--count", spec], repo)
    try:
        return int(text) if text is not None else UNKNOWN
    except ValueError:
        return UNKNOWN


def _dirty(path: Path) -> bool | str:
    """Whether git status lists anything; ``unknown`` when git cannot read ``path``.

    Fsmonitor, hooks and optional locks stay off, so a read cannot refresh the index or run a hook.
    """
    if not path.is_dir():
        return UNKNOWN
    r = _git(["--no-optional-locks", "status", "--porcelain", "--untracked-files=all"], path)
    return bool(r.out.strip()) if r.ok else UNKNOWN


def _reviews(repo_root: Path, node_id: str, branch: str | None) -> list[dict[str, Any]]:
    tip = (
        _git_out(["rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}"], repo_root)
        if branch else None
    )
    return [_review_row(repo_root, review, tip) for review in list_reviews(repo_root, node_id)]


def _review_row(repo: Path, review: ReviewFile, tip: str | None) -> dict[str, Any]:
    if _malformed(review, _REVIEW_KEPT):
        return dict.fromkeys(("model", "verdict", "commit", "fresh_for_head"), UNKNOWN)
    commit = review.data.get("commit")
    return {
        "model": review.data.get("model") or UNKNOWN,
        "verdict": review.data.get("verdict") or UNKNOWN,
        "commit": commit or UNKNOWN,
        "fresh_for_head": same_commit(repo, str(commit), tip) if commit and tip else UNKNOWN,
    }


def _ready_and_gate(repo: Path, node_id: str, branch: str | None) -> tuple[Any, dict[str, Any]]:
    """READY from :func:`latest_ready`, and the gate label from :func:`review_state` (no trial merge)."""
    from specy_road.bundled_scripts.review_cli import review_state

    try:
        rs = review_state(repo, node_id)
    except ReviewTargetError:
        return _ready_field(repo, node_id, branch, None), _unknown_gate()
    tip = _git_out(["rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}"], repo) if branch else None
    fresh: Any = same_commit(repo, rs.gate.commit, tip) if rs.gate.commit and tip else UNKNOWN
    gate = {
        "state": rs.state,
        "approvals": len(rs.gate.approvals),
        "blocks": len(rs.gate.blocks),
        "fresh_for_head": fresh,
    }
    return _ready_field(repo, node_id, branch, rs.target.commit), gate


def _unknown_gate() -> dict[str, Any]:
    return dict.fromkeys(("state", "approvals", "blocks", "fresh_for_head"), UNKNOWN)


def _ready_field(repo: Path, node_id: str, branch: str | None, commit: str | None) -> Any:
    files = list_ready(repo, node_id, branch)
    if files and not any(item.ok for item in files) and any(_malformed(item, _READY_KEPT) for item in files):
        return UNKNOWN
    ready = latest_ready(repo, node_id, branch)
    if ready is None:
        return None
    current = bool(commit) and same_commit(repo, str(ready.data.get("commit")), commit)
    row: dict[str, Any] = {
        "commit": ready.data.get("commit") or UNKNOWN,
        "model": ready.data.get("agent") or UNKNOWN,
        "at": _mtime_iso(ready.path),
    }
    if current:
        row["blocked_on"] = [
            {"acceptance": str(entry.get("acceptance")), "reason": str(entry.get("reason"))}
            for entry in (ready.data.get("blocked_on") or [])
            if isinstance(entry, dict)
        ]
    return row


def _malformed(review: ReviewFile, kept: tuple[str, ...]) -> bool:
    """True for a non-UTF-8, non-mapping or schema-invalid file. A later semantic error is kept."""
    return bool(review.errors) and not all(err.startswith(kept) for err in review.errors)


def _mtime_iso(path: Path) -> str:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return UNKNOWN
    return datetime.fromtimestamp(mtime, timezone.utc).replace(microsecond=0).isoformat()


def _hold_sources(repo: Path) -> tuple[Any, list | None]:
    return _hold_lines(repo), _gates(repo)


def _holds(node_id: str, listed: Any, gates: list | None) -> Any:
    if listed == UNKNOWN or gates is None:
        return UNKNOWN
    rows = [row for row in listed if row["id"] == node_id]
    rows += [
        {"source": "gate", "id": gate.node_id, "reason": gate.title or None}
        for gate in gates
        if node_id in gate.blocks
    ]
    return rows


def _gates(repo: Path) -> list | None:
    """Open gates as :func:`open_gates` lists them, or ``None`` when the graph cannot be loaded.

    The loader exits the process on a graph it refuses; a snapshot still returns.
    """
    from specy_road.bundled_scripts.roadmap_explain import open_gates
    from specy_road.roadmap_load import load_roadmap

    try:
        nodes = load_roadmap(repo).get("nodes")
    except (OSError, SystemExit):
        return None
    return open_gates(nodes) if isinstance(nodes, list) else None


def _hold_lines(repo: Path) -> Any:
    """Hold-list rows from the main checkout's ``work/grind-hold.txt``, or ``unknown``."""
    from specy_road.worktree_env import main_project_root

    path = main_project_root(repo) / "work" / "grind-hold.txt"
    try:
        os.lstat(path)
    except FileNotFoundError:
        return []
    except OSError:
        return UNKNOWN
    text = _regular_text(path)
    if text is None:
        return UNKNOWN
    return [row for line in text.splitlines() if (row := _hold_line(line))]


def _hold_line(line: str) -> dict[str, Any] | None:
    ident, sep, reason = line.partition("#")
    ident = ident.strip()
    if not ident:
        return None
    text = reason.strip() if sep else None
    return {"source": "hold_list", "id": ident, "reason": text or None}


def _regular_text(path: Path) -> str | None:
    """UTF-8 text of a regular file opened without following a final symlink, else ``None``."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as raw:
            if not stat.S_ISREG(os.fstat(raw.fileno()).st_mode):
                return None
            return raw.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
