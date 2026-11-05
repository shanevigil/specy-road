"""After every turn: what the harness's events and the worktree's git state say beyond the exit code (M8.2).

A turn can exit 0 and still have gone wrong: Claude Code exits 0 after denying a tool, reports some usage
limits as subtype success, and retries a rate limit on its own (harness-facts). So the wrapper reads each turn
twice. While it runs, a :class:`TurnWatch` sees every event the adapter parsed (``permission_denied``,
``api_retry``, ``error``, ``usage_limited``) and is the retry watchdog: a run that keeps retrying on
``rate_limit`` past :data:`LIMIT_WAIT_CAP_SECONDS` of announced waits is stopped instead of being left to wait
out a usage limit. When it ends, :func:`close_turn` compares the worktree's git state (HEAD, branch, stash list,
porcelain) with the state at the turn's start, records the findings in one ``post_run_check`` event, flags the
worker :data:`FLAG_POST_RUN` (a clean turn clears it), and reports a turn stopped by a usage limit, which the
wrapper turns into :data:`PAUSED_BY_LIMIT` with the record's ``limit_reset_at``, whatever the exit code.

Steering files (M21.7, :mod:`specy_road.steering_paths`) are compared first: the git half (hooks, config) from the
filesystem before any post-turn git command, so ``git status`` never runs under a ``core.fsmonitor`` or hook the
turn changed; on such a change the git probes are skipped (a ``git_probes_skipped`` finding). Each changed steering
file is one ``steering_file`` finding, which replaces a ``porcelain`` or ``committed_outside_zones`` mention of the
same path, and sets the sticky :data:`FLAG_STEERING`, which only ``worker reconcile`` clears.

The paused state lives here and in that one record field; ``worker resume`` and ``worker message`` consult
:func:`limit_gate`. Deterministic: no model reads anything, only the parsed events and git.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from specy_road.finish_implementation_check import _clean, zone_matches
from specy_road.git_changed_paths import branch_commit_paths
from specy_road.git_subprocess import git_text, head_sha, run
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.steering_paths import FLAG_STEERING, SteeringWatch
from specy_road.worker_adapter_base import Parsed
from specy_road.worker_reconcile import _bookkeeping
from specy_road.worker_state import WorkerError, WorkerRecord, add_flag, append_event, clear_flag, mutate, status_entries

#: The record state of a worker whose last turn stopped at a usage limit; resumable after ``limit_reset_at``.
PAUSED_BY_LIMIT = "paused_by_limit"
#: The flag a post-run finding sets; each turn's check sets or clears it, as ``reconcile`` does ``needs_reconcile``.
FLAG_POST_RUN = "post_run_findings"
#: The retry watchdog's cap: seconds of ``rate_limit`` retry delays one turn may announce before it is stopped.
LIMIT_WAIT_CAP_SECONDS = 600


@dataclass(frozen=True)
class GitState:
    """What the post-run check compares; ``None`` where git could not answer."""
    head: str | None
    branch: str | None
    stash: tuple[str, ...] | None
    dirty: dict[str, str] | None   # each modified or untracked path and :func:`_content` of it


def _content(worktree: Path, rel: str) -> str:
    """What a dirty path holds, as the check compares it: the file's digest, a link's target, ``-`` when gone.
    A path dirty at the turn's start that the turn edits again is a change too, not only a new path."""
    path = worktree / rel
    if path.is_symlink():
        return f"link:{os.readlink(path)}"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "-"


def git_state(worktree: Path) -> GitState:
    stash = run(["stash", "list", "--format=%H"], worktree)
    entries = status_entries(worktree)
    return GitState(head_sha(worktree), git_text(["branch", "--show-current"], worktree),
                    tuple(stash.out.split()) if stash.ok else None,
                    {p: _content(worktree, p) for _xy, p in entries} if entries is not None else None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TurnWatch:
    """One turn's events as the post-run check needs them; created at the turn's start, before the harness."""

    def __init__(self, repo_root: Path, rec: WorkerRecord, *, now: Callable[[], datetime] = _utcnow) -> None:
        self.repo_root, self.rec, self.now = repo_root, rec, now
        self.before = git_state(Path(rec.worktree))
        self.steering: SteeringWatch | None = None
        self.steering_error: str | None = None
        try:   # the steering snapshot (M21.7); a failure is a finding, never a lost turn
            self.steering = SteeringWatch(repo_root, Path(rec.worktree), rec.node_id, self.before.dirty)
        except Exception as e:  # noqa: BLE001
            self.steering_error = str(e)
        self.proc: subprocess.Popen | None = None   # the harness, once started: what the watchdog stops
        self.denials: list[str] = []
        self.failed: str | None = None   # the last error no completed turn followed: the turn failed
        self.retries: list[dict[str, Any]] = []
        self.limit: dict[str, Any] | None = None     # a usage limit the harness's output named, or the watchdog's
        self.pending: dict[str, Any] | None = None   # rate_limit retries no completed turn has followed yet
        self.rate_wait = 0.0
        mutate(repo_root, rec, lambda r: setattr(r, "limit_reset_at", None))   # a new turn: the last limit is past

    def observe(self, parsed: Parsed) -> None:
        detail = parsed.detail or {}
        if parsed.type == "permission_denied":
            self.denials.append(parsed.summary)
        elif parsed.type == "error":
            self.failed = parsed.summary
        elif parsed.type == "usage_limited":
            self.limit = self.limit or detail
        elif parsed.type == "turn_completed":
            self.failed = self.pending = None   # a finished turn: earlier errors and retries did not stop it
        elif parsed.type == "api_retry":
            self.retries.append(detail)
            if detail.get("error") == "rate_limit":
                self._watchdog(detail)

    def exited(self, code: int) -> None:
        """The harness's exit code, read before :func:`close_turn`: a non-zero exit (a SIGKILL included, which no
        stream event reports) is a failed turn, unless a usage limit already explains the stop."""
        if code != 0 and not self.failed and not (self.limit or self.pending):
            self.failed = f"exit {code}"

    def _watchdog(self, detail: dict[str, Any]) -> None:
        delay = detail.get("retry_delay_ms")
        delay = delay / 1000 if isinstance(delay, (int, float)) and not isinstance(delay, bool) and delay > 0 else 0.0
        self.rate_wait += delay
        self.pending = {"reset_at": (self.now() + timedelta(seconds=delay)).isoformat(), "source": "api_retry",
                        "evidence": f"api_retry rate_limit, attempt {detail.get('attempt')}/{detail.get('max_retries')}"}
        if self.rate_wait <= LIMIT_WAIT_CAP_SECONDS or self.limit or self.proc is None or self.proc.poll() is not None:
            return
        self.limit = {**self.pending, "source": "watchdog",
                      "evidence": f"{self.rate_wait:.0f}s of rate_limit retries passed the {LIMIT_WAIT_CAP_SECONDS}s cap"}
        self.proc.terminate()   # the harness only (claude -p exits 143, the turn unfinished); the wrapper reads on to EOF
        append_event(self.repo_root, self.rec, "usage_limited", source="system",
                     summary=f"retry watchdog stopped the harness: {self.limit['evidence']}", detail=self.limit)

    def stream_findings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if self.denials:
            out.append({"kind": "permission_denied", "count": len(self.denials),
                        "summary": f"{len(self.denials)} permission denial(s): " + "; ".join(self.denials[:3])})
        if self.failed:
            out.append({"kind": "failed_turn", "summary": f"failed turn: {self.failed}"})
        if self.retries:
            kinds = sorted({str(r.get("error")) for r in self.retries})
            out.append({"kind": "api_retry", "count": len(self.retries),
                        "summary": f"{len(self.retries)} api retr{'y' if len(self.retries) == 1 else 'ies'} ({', '.join(kinds)})"})
        return out


def _outside_zones(repo_root: Path, rec: WorkerRecord, start: str, end: str,
                   expected: Callable[[str], bool]) -> list[str]:
    """Paths the turn's own commits changed outside the leaf's touch zones (none when the claim has none)."""
    try:
        zones = [z for z in (_clean(z) for z in resolve_target(repo_root, rec.node_id).touch_zones) if z]
    except ReviewTargetError:
        return []
    prefix = project_prefix(repo_root)
    paths = branch_commit_paths(Path(rec.worktree), f"{start}..{end}") or set()
    return sorted(p for p in paths if zones and not expected(p)
                  and not any(zone_matches(z, rebase_to_project(p, prefix) or p) for z in zones))


def git_findings(repo_root: Path, rec: WorkerRecord, before: GitState, after: GitState | None = None) -> list[dict[str, Any]]:
    """The worktree's git state now (``after``, read here when not given) against ``before``: anything beyond the
    leaf's own commits and bookkeeping."""
    wt = Path(rec.worktree)
    after = after or git_state(wt)
    prefix = project_prefix(repo_root)

    def expected(p: str) -> bool:   # what reconcile never counts as a breach
        return _bookkeeping(p, rec.node_id, prefix) or rebase_to_project(p, prefix) == "roadmap/registry.yaml"
    out: list[dict[str, Any]] = []
    if after.branch != before.branch:
        out.append({"kind": "branch", "summary": f"branch {before.branch or '(detached)'} -> {after.branch or '(detached)'}"})
    if before.head and after.head != before.head:
        if not after.head or not run(["merge-base", "--is-ancestor", before.head, after.head], wt).ok:
            out.append({"kind": "head", "summary": f"HEAD {before.head[:12]} -> {(after.head or '?')[:12]} "
                                                   "is not a descendant (reset, rebase or amend)"})
        elif outside := _outside_zones(repo_root, rec, before.head, after.head, expected):
            out.append({"kind": "committed_outside_zones", "paths": outside,
                        "summary": "committed outside the touch zones: " + ", ".join(outside[:10])})
    if after.stash != before.stash:
        out.append({"kind": "stash", "summary": "stash list changed during the turn (the stack is shared by every "
                                                "worktree of the repository)"})
    if after.dirty is None:
        out.append({"kind": "porcelain", "summary": "git status could not be read after the turn"})
    else:   # every path dirty at either end: new, changed, or gone (deleted, restored or committed) during the turn
        start = before.dirty or {}
        if extra := sorted(p for p in start.keys() | after.dirty.keys()
                           if start.get(p) != after.dirty.get(p) and not expected(p)):
            out.append({"kind": "porcelain", "paths": extra,
                        "summary": "dirty paths new, changed or gone during the turn: " + ", ".join(extra[:10])})
    return out


def close_turn(repo_root: Path, rec: WorkerRecord, watch: TurnWatch, *, pause: bool = True) -> bool:
    """Record the turn's findings and flag (or clear) the worker; ``True`` when a usage limit stopped the turn,
    which then has ``limit_reset_at`` set for the wrapper to move it to :data:`PAUSED_BY_LIMIT`.

    Every started turn ends here, a harness that could not start and a record already ``terminated``
    included. ``pause=False`` (the terminated record) still records a limit as a finding, but sets no
    ``limit_reset_at``: a terminated worker stays terminated."""
    found = _turn_findings(repo_root, rec, watch)
    limit = watch.limit or watch.pending
    if limit:
        found.append({"kind": "usage_limit", "summary": f"usage limit ({limit.get('source')}); resets "
                                                        f"{limit.get('reset_at') or 'at an unstated time'}", **limit})
    # Exactly one event per turn, a clean one included (empty findings): the log shows the check ran.
    append_event(repo_root, rec, "post_run_check", source="system",
                 detail={"findings": found},
                 summary=(f"post-run check: {len(found)} finding(s): " + "; ".join(f["summary"] for f in found))
                 if found else "post-run check: clean")
    if found:
        add_flag(repo_root, rec, FLAG_POST_RUN)
    else:
        clear_flag(repo_root, rec, FLAG_POST_RUN)
    if any(f["kind"] == "steering_file" for f in found):
        add_flag(repo_root, rec, FLAG_STEERING)   # sticky: a clean turn leaves it; worker reconcile clears it
    if limit and pause:
        mutate(repo_root, rec, lambda r: setattr(r, "limit_reset_at", limit.get("reset_at")))
    return bool(limit) and pause


def _turn_findings(repo_root: Path, rec: WorkerRecord, watch: TurnWatch) -> list[dict[str, Any]]:
    """The turn's findings. Git steering is compared first, from the
    filesystem: when it changed (or cannot be compared), no post-turn git command runs."""
    found, steer, sw = watch.stream_findings(), [], watch.steering
    if sw is None:
        found.append({"kind": "check_error", "summary": f"steering files not checked: {watch.steering_error}"})
    try:
        steer = sw.git_changes() if sw else []
    except Exception as e:  # noqa: BLE001 — the check must never cost the turn its exit record
        found.append({"kind": "check_error", "summary": f"git steering not checked: {e}; git probes skipped"})
        return found
    after = None
    if steer:
        found.append({"kind": "git_probes_skipped", "summary": "git steering changed: post-turn git probes skipped"})
    else:
        try:
            after = git_state(Path(rec.worktree))
            found += git_findings(repo_root, rec, watch.before, after)
        except Exception as e:  # noqa: BLE001
            found.append({"kind": "check_error", "summary": f"git state not checked: {e}"})
    if sw is not None:
        try:
            steer += sw.rest_changes(after.dirty if after else None, git_ok=after is not None)
        except Exception as e:  # noqa: BLE001
            found.append({"kind": "check_error", "summary": f"steering files not checked: {e}"})
        return sw.merged(found, steer)
    return found


def limit_gate(rec: WorkerRecord, now: datetime | None = None) -> None:
    """Refuse a turn for a worker paused by a usage limit before its reset: it would hit the limit again."""
    if rec.state != PAUSED_BY_LIMIT or not rec.limit_reset_at:
        return
    try:
        reset = datetime.fromisoformat(rec.limit_reset_at)
    except ValueError:
        return   # not a time this module wrote; the human decides
    if (now or _utcnow()) < reset:
        raise WorkerError(f"{rec.worker_id} is paused by a usage limit until {rec.limit_reset_at}; "
                          "`worker resume` picks it up after that")
