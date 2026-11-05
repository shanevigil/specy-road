"""Attribute shared-stash list changes to the worker whose branch owns each entry (M15.25).

Turn boundaries compare ``git stash list`` only. A stash pushed and popped entirely inside
another worker's turn leaves identical start/end lists, so that action is not detected.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from specy_road.worker_state import WorkerRecord, add_flag, append_event, events_since, list_records, load_record

_FLAG_POST_RUN = "post_run_findings"

StashEntry = tuple[str, str]  # (commit hash, subject from ``git stash list --format=%gs``)

_ON = re.compile(r"^On (.+?): ", re.IGNORECASE)
_WIP = re.compile(r"^WIP on (.+?): ", re.IGNORECASE)

_UNKNOWN_STASH_SUMMARY = (
    "stash state unknown: git stash list could not be read at the start or end of the turn "
    "(the stack is shared by every worktree of the repository)"
)


def stash_branch(subject: str) -> str | None:
    """The branch named in a stash subject, or ``None`` when the subject does not use the usual forms."""
    if m := _ON.match(subject):
        branch = m.group(1).strip()
        return None if branch.startswith("(") else branch
    if m := _WIP.match(subject):
        branch = m.group(1).strip()
        return None if branch.startswith("(") else branch
    return None


def _attributed_hashes(repo_root: Path, worker_id: str) -> set[str]:
    out: set[str] = set()
    for ev in events_since(repo_root, worker_id):
        if ev.type != "post_run_check" or not ev.detail:
            continue
        detail = ev.detail
        for f in detail.get("findings") or ():
            if isinstance(f, dict) and isinstance(f.get("stash_hash"), str):
                out.add(f["stash_hash"])
        for h in detail.get("attributed_stash_hashes") or ():
            if isinstance(h, str):
                out.add(h)
    return out


def _owner(repo_root: Path, branch: str) -> WorkerRecord | None:
    for rec in list_records(repo_root):
        if rec.branch == branch:
            return rec
    return None


def _rule_summary(subject: str) -> str:
    return (f'stash entry {subject!r}: the executor prompt forbids stashing '
            f"(the stack is shared by every worktree of the repository)")


def _legacy_stash_summary(subject: str) -> str:
    return ("stash list changed during the turn (the stack is shared by every worktree of the repository): "
            f"{subject!r}")


def _attribute_owner(repo_root: Path, owner: WorkerRecord, stash_hash: str, subject: str) -> None:
    finding: dict[str, Any] = {"kind": "stash_rule_violation", "summary": _rule_summary(subject),
                                "stash_hash": stash_hash, "subject": subject}
    append_event(repo_root, owner, "post_run_check", source="system",
                 summary=f"post-run check: 1 finding(s): {finding['summary']}",
                 detail={"findings": [finding], "attributed_stash_hashes": [stash_hash]})
    add_flag(repo_root, owner, _FLAG_POST_RUN)


def _decide_stash_hash_change(repo_root: Path, rec: WorkerRecord, stash_hash: str,
                              subject: str) -> list[dict[str, Any]]:
    """Observer findings for one added or removed hash; all attribution paths go through here."""
    branch = stash_branch(subject)
    if branch is None:
        return [{"kind": "stash", "summary": _legacy_stash_summary(subject), "subject": subject}]
    owner = _owner(repo_root, branch)
    if owner is None:
        return [{"kind": "stash", "summary": _legacy_stash_summary(subject), "subject": subject}]
    if stash_hash in _attributed_hashes(repo_root, owner.worker_id):
        return []
    if owner.worker_id == rec.worker_id:
        return [{"kind": "stash_rule_violation", "summary": _rule_summary(subject),
                 "stash_hash": stash_hash, "subject": subject}]
    _attribute_owner(repo_root, load_record(repo_root, owner.worker_id), stash_hash, subject)
    return [{"kind": "stash_other", "summary": f"stash change on {owner.worker_id}'s branch ({branch!r}): "
                                                f"{subject!r}",
              "worker_id": owner.worker_id, "branch": branch, "stash_hash": stash_hash}]


def stash_findings(repo_root: Path, rec: WorkerRecord, before: tuple[StashEntry, ...] | None,
                   after: tuple[StashEntry, ...] | None) -> list[dict[str, Any]]:
    """Stash-list deltas for this turn: attribute to the branch owner, notes for innocent observers."""
    if before is None or after is None:
        if before != after:
            return [{"kind": "stash", "summary": _UNKNOWN_STASH_SUMMARY}]
        return []
    before_map = dict(before)
    after_map = dict(after)
    out: list[dict[str, Any]] = []
    for stash_hash in sorted(set(before_map) | set(after_map)):
        if before_map.get(stash_hash) == after_map.get(stash_hash):
            continue
        subject = after_map.get(stash_hash) or before_map.get(stash_hash) or ""
        out.extend(_decide_stash_hash_change(repo_root, rec, stash_hash, subject))
    return out
