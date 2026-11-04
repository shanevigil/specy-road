"""The human lease: ``worker handoff`` / ``reclaim`` (slice 7c); the hook witness is :mod:`worker_witness`.
Below them, the slot lease other checkouts count against ``max_workers`` (M11.4).

Split from :mod:`specy_road.worker_ops` for the file limit; the CLI reaches
these through that module. Each transition runs under the workers lock as
one transaction, so a second ``reclaim`` sees the lease already returned
and a hook append cannot slip between a reclaim's read and its write.
``reclaim`` moves the record (epoch, lease, state, flag) in **one** write
before it appends its events, so a crash and a retry cannot count the same
intervention twice; a retry after that write only repairs the missing events.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import GitResult, git_text, run
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.orchestration_pinned import pinned_config
from specy_road.worker_adapters import Unsupported, adapter_for
from specy_road.worker_process import process_alive, require_branch, wrapper_gone
from specy_road.worker_sessions import check_session_id, render_command
from specy_road.worker_state import (
    FLAG_EXTERNAL,
    TERMINAL_STATES,
    WorkerError,
    WorkerRecord,
    append_event,
    events_since,
    list_records,
    load_record,
    mutate,
    require_writer,
    take_checkpoint,
    workers_lock,
)
from specy_road.worker_orphans import holding_slots, slot_breakdown
from specy_road.worker_witness import interventions_path, record_hook_prompt  # noqa: F401 — re-exported

CLOSED_STATES = TERMINAL_STATES


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def handoff(repo_root: Path, worker_id: str) -> tuple[WorkerRecord, list[str]]:
    """Lease the worker to a human; returns the native resume command."""
    with workers_lock(repo_root):
        return _handoff_locked(repo_root, load_record(repo_root, worker_id))


def _handoff_locked(repo_root: Path, rec: WorkerRecord) -> tuple[WorkerRecord, list[str]]:
    if rec.lease.get("holder") == "human":
        sid = check_session_id(rec.harness, rec.provider_session_id)
        return rec, adapter_for(rec.harness).human_resume(sid, Path(rec.worktree))
    require_writer(rec)
    wrapper_gone(repo_root, rec)   # a crashed turn is closed here; a surviving harness keeps it running
    if rec.state in CLOSED_STATES:
        raise WorkerError(f"{rec.worker_id} is {rec.state}; nothing to hand off")
    if process_alive(rec, repo_root):
        raise WorkerError(f"{rec.worker_id} is running (pid {rec.pid}); wait for idle or terminate first")
    adapter = adapter_for(rec.harness)
    if not adapter.caps.handoff or not rec.provider_session_id:
        raise Unsupported(f"unsupported by {rec.harness}: handoff (no native session to resume)")
    cmd = adapter.human_resume(check_session_id(rec.harness, rec.provider_session_id), Path(rec.worktree))
    take_checkpoint(repo_root, rec)
    # Prompts recorded before this line are an earlier lease's, whatever
    # their timestamp (the clock has one-second resolution).
    seen = _hook_lines(repo_root, rec)

    def move(r: WorkerRecord) -> None:   # one write: the lease never changes hands without its checkpoint
        r.checkpoint["interventions_seen"] = seen
        r.lease = {"holder": "human", "since": _now()}
        r.state = "handed_off"
    mutate(repo_root, rec, move)
    append_event(repo_root, rec, "handoff", source="orchestrator", authority="orchestrator",
                 summary=f"handed off; resume with: {render_command(cmd)} (in {rec.worktree})")
    return rec, cmd


def _hook_lines(repo_root: Path, rec: WorkerRecord) -> int:
    path = interventions_path(repo_root, rec.worker_id)
    return len(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else 0


def _hook_prompts(repo_root: Path, rec: WorkerRecord, skip: int) -> list[dict[str, Any]]:
    """The hook-recorded prompts after the first ``skip`` lines (those predate the hand-off)."""
    path = interventions_path(repo_root, rec.worker_id)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[skip:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _diff_stat(worktree: Path, since_sha: str | None) -> str:
    """``git diff --stat`` since the checkpoint plus the untracked files, which a diff omits."""
    stat = (git_text(["diff", "--stat", since_sha], worktree) or "") if since_sha else ""
    new = git_text(["ls-files", "--others", "--exclude-standard"], worktree) or ""
    return "\n".join(x for x in [stat, *(f" {p} | new" for p in new.splitlines() if p.strip())] if x)


def reclaim(repo_root: Path, worker_id: str, note: str = "") -> tuple[WorkerRecord, dict[str, Any]]:
    with workers_lock(repo_root):   # one transaction: a second reclaim sees the lease already returned
        return _reclaim_locked(repo_root, load_record(repo_root, worker_id), note)


def _events_behind(repo_root: Path, rec: WorkerRecord) -> bool:
    """The record's epoch moved but the matching ``intervention`` event never landed: a crash mid-reclaim."""
    logged = sum(1 for e in events_since(repo_root, rec.worker_id) if e.type == "intervention")
    return rec.instruction_epoch > logged


def _gather(repo_root: Path, rec: WorkerRecord, note: str) -> tuple[dict[str, Any], str, list[str]]:
    cp = rec.checkpoint or {}
    prompts = _hook_prompts(repo_root, rec, int(cp.get("interventions_seen") or 0))
    stat = _diff_stat(Path(rec.worktree), cp.get("git_head"))
    pre_existing = sorted(set(cp.get("dirty_paths") or []))
    if pre_existing:
        stat += "\n(already dirty at hand-off, not the human's: " + ", ".join(pre_existing) + ")"
    heard = [str(p.get("prompt", "")) for p in prompts]          # verbatim: the hook stores the whole prompt
    shown = [h[:200] for h in heard]
    summary = (f"human direction ({len(heard)} prompt(s) recorded by hook): " + " | ".join(shown)
               if heard else "human session returned without hook evidence")
    if note:
        summary += f" — note: {note}"
    detail = {"prompts": heard, "diff_stat": stat, "checkpoint": cp, "pre_existing_dirty": pre_existing}
    return detail, summary, heard


def _reclaim_locked(repo_root: Path, rec: WorkerRecord, note: str) -> tuple[WorkerRecord, dict[str, Any]]:
    repairing = rec.lease.get("holder") != "human" and _events_behind(repo_root, rec)
    if rec.lease.get("holder") != "human" and not repairing:
        raise WorkerError(f"{rec.worker_id} is not handed off (lease: {rec.lease.get('holder')})")
    require_branch(rec)   # the human may have switched branches; reclaim on the wrong one is refused (B12)
    detail, summary, heard = _gather(repo_root, rec, note)
    if not repairing:
        def move(r: WorkerRecord) -> None:   # one write: epoch, flag, lease and state together
            r.instruction_epoch += 1
            if not heard and FLAG_EXTERNAL not in r.flags:
                r.flags.append(FLAG_EXTERNAL)
            r.lease = {"holder": "broker", "since": _now()}
            r.state = "idle"
        mutate(repo_root, rec, move)
    else:
        summary += " (events repaired after an interrupted reclaim)"
    append_event(repo_root, rec, "intervention", source="hook" if heard else "human",
                 authority="human_authoritative", summary=summary, detail=detail)
    append_event(repo_root, rec, "reclaim", source="orchestrator", authority="orchestrator",
                 summary=f"lease back to broker; epoch {rec.instruction_epoch}")
    return rec, detail


# --- the slot lease: one ref per live worker on the integration remote (M11.4) ---------------------------------
#
# ``refs/specy-road/leases/<checkout-id>/<worker-id>``, pushed when a turn launches or resumes and deleted when the
# record goes ``failed`` or ``terminated`` (never on ``idle`` or ``completed``: those still hold their slot
# until their leaf is over, when ``sync`` releases it, M11.57). A
# checkout counts its own ``work/.workers/`` records plus every lease ref whose checkout id is not its own, so a
# clone's workers count wherever their branches happen to exist and whoever owns them. One id per repository:
# it lives in git's common dir, which linked worktrees share with the main checkout, as they share the records.

LEASES = "refs/specy-road/leases/"
LEASE_TIMEOUT = 20.0
OFFLINE_HINT = "retry, or pass --offline to count this checkout's workers only"
_CHECKOUT_ID = re.compile(r"[0-9a-f]{32}")
_WARNED: set[str] = set()        # remote URLs already warned about in this process (--offline)
_UNREACHABLE: set[str] = set()   # remote URLs a release timed out on: releases are not retried in this process


def checkout_id(repo_root: Path) -> str:
    """This repository's stable id, a uuid in ``<git-common-dir>/specy-road-checkout-id``; a :class:`WorkerError`
    when none can be had, never an empty id (with one, a checkout would count no leases and push none).

    A file holding a valid id is only ever read: never renamed, removed or rewritten, so an id once returned stays
    the id. Only an absent, empty or invalid file is initialised, under the workers lock and after reading it again
    there: a new uuid goes to a unique temporary file, installed with ``os.link`` when the file is absent (which
    fails if it now exists) or ``os.replace`` over an invalid one (no valid id can appear while the lock is held,
    since every initialisation takes it). After any failure the file is read again and a valid id there is used."""
    common = git_text(["rev-parse", "--git-common-dir"], repo_root)
    if not common:
        raise WorkerError(f"cannot find git's common dir from {repo_root}, so this checkout has no id for its leases")
    path = Path(repo_root, common) / "specy-road-checkout-id"
    if cid := _read_id(path):
        return cid
    with workers_lock(repo_root):
        if cid := _read_id(path):   # another caller initialised it while this one waited
            return cid
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(uuid.uuid4().hex + "\n", encoding="utf-8")
            if path.exists() or path.is_symlink():
                os.replace(tmp, path)   # empty or invalid: no lease was ever pushed under it
            else:
                os.link(tmp, path)
        except OSError as e:
            if cid := _read_id(path):
                return cid
            raise WorkerError(f"cannot write the checkout id {path}: {e}; nothing was launched") from None
        finally:
            tmp.unlink(missing_ok=True)
    if cid := _read_id(path):
        return cid
    raise WorkerError(f"{path} holds no usable checkout id after initialising it; nothing was launched")


def _read_id(path: Path) -> str | None:
    try:
        cid = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return cid if _CHECKOUT_ID.fullmatch(cid) else None


def _remote(repo_root: Path) -> tuple[str, str] | None:
    """``(name, url)`` of the integration remote; ``None`` when this repository has none (nothing to share)."""
    remote = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)[1]
    url = git_text(["remote", "get-url", remote], repo_root)
    return (remote, url) if url else None


def _warn_offline(url: str, remote: str) -> None:
    if url not in _WARNED:
        _WARNED.add(url)
        print(f"warning: --offline: the global max_workers limit was not verified; counted this checkout's workers "
              f"and the lease refs last fetched from {remote}, and pushed no lease", file=sys.stderr)


def _why(r) -> str:
    return r.message.splitlines()[-1] if r.message else str(r.failure)


def _known(remote: str) -> str:
    return f"refs/specy-road/known-leases/{remote}/"


def _lease_refs(repo_root: Path, remote: str, prefix: str, *, fetch: bool = True) -> list[str]:
    """``<checkout-id>/<worker-id>`` per lease ref under ``prefix``, from a local mirror that ``fetch`` refreshes
    (and prunes) from the remote first; a :class:`WorkerError` when it cannot. Without ``fetch``: as last fetched."""
    if fetch:
        r = run(["fetch", "--quiet", "--prune", "--no-tags", remote, f"+{LEASES}*:{_known(remote)}*"], repo_root,
                timeout=LEASE_TIMEOUT)
        if not r.ok:
            raise WorkerError(f"cannot reach {remote} to count other checkouts' workers ({_why(r)}); {OFFLINE_HINT}")
    out = git_text(["for-each-ref", "--format=%(refname)", _known(remote)], repo_root) or ""
    names = sorted(line[len(_known(remote)):] for line in out.splitlines())
    return [n for n in names if (LEASES + n).startswith(prefix)]


def foreign_leases(repo_root: Path, *, offline: bool = False) -> list[str]:
    """Live workers of other checkouts: their lease refs on the integration remote (none without that remote).

    Refused when the remote cannot be read. ``offline`` is the explicit local-only escape: no remote is read, the
    lease refs as last fetched are counted, and one warning says the global limit was not verified (a worker
    another checkout started since that fetch is not seen)."""
    rm = _remote(repo_root)
    if not rm:
        return []
    cid = checkout_id(repo_root)   # raises: with no id, every lease would look like another checkout's
    if offline:
        _warn_offline(rm[1], rm[0])
    return [n for n in _lease_refs(repo_root, rm[0], LEASES, fetch=not offline) if not n.startswith(cid + "/")]


def max_workers(repo_root: Path) -> int:
    config, err = pinned_config(repo_root)
    if err:
        raise WorkerError(f"orchestration config: {err}")
    return int(config["policy"]["max_workers"])


def slot_error(held: list[WorkerRecord], foreign: list[str], limit: int) -> WorkerError:
    """The refusal at the limit: running and held-but-idle workers named apart, and what frees a held slot."""
    where = f" (and {len(foreign)} leased by other checkouts: {', '.join(foreign)})" if foreign else ""
    return WorkerError(f"{len(held)} workers active{where}, policy max_workers is {limit}; {slot_breakdown(held)}")


def _push_lease(repo_root: Path, remote: str, cid: str, rec: WorkerRecord) -> GitResult:
    """Push ``rec``'s lease ref: a parentless commit on the empty tree naming the worker, so nothing else uploads."""
    tree = git_text(["hash-object", "-w", "-t", "tree", os.devnull], repo_root)
    sha = tree and git_text(["-c", "user.name=specy-road", "-c", "user.email=specy-road@localhost", "commit-tree", tree,
                             "-m", f"specy-road lease {rec.worker_id} {rec.node_id} {rec.harness}/{rec.model}"], repo_root)
    if not sha:
        return GitResult(-1, "", f"cannot build the lease commit for {rec.worker_id}", "error")
    return run(["push", "--quiet", "--force", remote, f"{sha}:{LEASES}{cid}/{rec.worker_id}"], repo_root,
               timeout=LEASE_TIMEOUT)


def acquire_lease(repo_root: Path, rec: WorkerRecord, *, new: bool, offline: bool = False, count: bool = True) -> None:
    """Push ``rec``'s lease, then count again, so of two checkouts launching at once neither goes over the limit
    (both may be refused; never one too many). ``new``: no lease existed, so a refusal deletes the one pushed.
    ``count=False`` pushes without the recount (``adopt``: the session already runs, refusing would not stop it).

    A push the remote rejects, or a remote that cannot be reached, refuses the turn; ``offline`` skips the push
    but still counts the lease refs last fetched (one warning); other checkouts count this worker once ``sync``
    pushes its lease. Run under the
    workers lock, as every caller does: ``sync_leases`` takes it too, so it cannot remove a lease being acquired."""
    rm = _remote(repo_root)
    if not rm:
        return
    remote, cid = rm[0], checkout_id(repo_root)   # refuses the turn when there is no usable id
    if not offline:
        r = _push_lease(repo_root, remote, cid, rec)
        if not r.ok:
            if run(["ls-remote", remote, LEASES + "*"], repo_root, timeout=LEASE_TIMEOUT).ok:   # reachable: rejected
                raise WorkerError(f"{remote} rejected the lease for {rec.worker_id} ({_why(r)}); nothing was launched")
            raise WorkerError(f"cannot reach {remote} to push the lease for {rec.worker_id} ({_why(r)}); {OFFLINE_HINT}")
    if not count:
        return
    try:
        limit, foreign = max_workers(repo_root), foreign_leases(repo_root, offline=offline)
        local = holding_slots(repo_root, [r for r in list_records(repo_root, active_only=True) if r.worker_id != rec.worker_id])
        if len(local) + len(foreign) >= limit:
            raise slot_error(local, foreign, limit)
    except WorkerError:
        if new and not offline:
            release_lease(repo_root, rec.worker_id)
        raise


def lease_adopted(repo_root: Path, rec: WorkerRecord) -> None:
    """``adopt``'s lease, pushed with no recount; one that cannot be pushed closes the record and refuses the adopt,
    since a worker other checkouts cannot see would let them launch past ``max_workers``."""
    try:
        acquire_lease(repo_root, rec, new=True, count=False)
    except WorkerError as e:
        append_event(repo_root, rec, "error", source="system", summary=f"adopt refused: {e}")
        mutate(repo_root, rec, lambda r: setattr(r, "state", "terminated"))
        raise


def release_lease(repo_root: Path, *worker_ids: str) -> None:
    """Delete these workers' lease refs; best effort (a ref left behind over-counts, and ``sync`` retries it)."""
    rm = _remote(repo_root)
    if not rm or not worker_ids or rm[1] in _UNREACHABLE:
        return
    try:
        cid = checkout_id(repo_root)
    except WorkerError:
        return   # no id: this checkout never pushed a lease under one
    r = run(["push", "--quiet", rm[0], "--delete", *(f"{LEASES}{cid}/{w}" for w in worker_ids)], repo_root,
            timeout=LEASE_TIMEOUT)
    if r.failure == "timeout":
        _UNREACHABLE.add(rm[1])
        print(f"warning: cannot reach {rm[0]} to release worker leases; `worker sync` retries", file=sys.stderr)


def sync_leases(repo_root: Path) -> tuple[list[str], list[str]]:
    """Make this checkout's lease refs match its active records; ``(released, pushed)`` worker ids.

    A ref whose worker is no longer active here, or no longer holds a slot (its leaf is over, M11.57), is deleted; a
    slot-holding worker with no ref (registered before leases existed, launched ``--offline``, or whose push failed)
    gets one, best effort. The remote is read unlocked; each
    candidate is then rechecked and every delete and push made under the workers lock, so a launch or resume (which
    pushes its lease under the same lock) cannot interleave."""
    rm = _remote(repo_root)
    if not rm:
        return [], []
    try:
        cid = checkout_id(repo_root)
        held = {n.split("/", 1)[1] for n in _lease_refs(repo_root, rm[0], f"{LEASES}{cid}/")}
    except WorkerError:
        return [], []   # unreachable, or no usable id: sync still reports; the next sync retries
    with workers_lock(repo_root):
        counted = holding_slots(repo_root, list_records(repo_root, active_only=True))
        stale = sorted(held - {r.worker_id for r in counted})   # closed, freed, or no record here: nothing holds it
        release_lease(repo_root, *stale)
        unleased = [r for r in counted if r.worker_id not in held]
        pushed = [r.worker_id for r in unleased if _push_lease(repo_root, rm[0], cid, r).ok]
    return stale, pushed
