"""The operations behind ``specy-road worker`` (slice 7c).

Each function does one lifecycle step on a worker record and raises
:class:`WorkerError` (or :class:`Unsupported`) with the sentence the CLI
prints. The CLI module is argument parsing and output only.

``delegate`` runs **after pickup**: the leaf must already hold a registry
claim with a branch, because pickup switches branches and pushes the
registry, which is not something a coordinator's checkout should do on a
worker's behalf (design note, slice 7). The worker's worktree is the
coordinator's checkout when it has the claim's branch checked out, otherwise
a linked worktree under ``work/.worktrees/<codename>``.
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.git_subprocess import git_text, run
from specy_road.model_profiles import profile_for_entry
from specy_road.orchestrate_plan import ANY, is_available, may_handle, node_eligibility, node_sensitivity
from specy_road.orchestration_config import roster_entry
from specy_road.orchestration_pinned import pinned_config
from specy_road.review_files import reviews_root
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.worker_adapters import Unsupported, adapter_for
from specy_road.worker_runner import pid_alive, pid_verified, spawn
from specy_road.worker_state import (
    TERMINAL_STATES,
    WorkerError,
    WorkerRecord,
    active_for_node,
    append_event,
    create_record,
    list_records,
    load_record,
    mutate,
    require_writer,
    set_state,
    take_checkpoint,
    workers_lock,
)

#: ``completed`` is not closed: a review ``block`` goes back to it as a
#: ``message``, and it owns its leaf until ``terminate`` (docs/orchestration-workers.md).
CLOSED_STATES = TERMINAL_STATES

CONTINUE_PROMPT = ("Continue the task from where you stopped. Re-read the brief and the precondition "
                   "first; if the hand-off is already written, say so and stop.\n")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _target(repo_root: Path, node_id: str):
    try:
        t = resolve_target(repo_root, node_id)
    except ReviewTargetError as e:
        raise WorkerError(f"{e}; `delegate` runs after pickup (do-next-available-task --under {node_id})") from None
    if not t.entry or not t.entry.get("branch"):
        raise WorkerError(f"{node_id} has no registry claim with a branch; pick it up first")
    return t


def _entry_and_harness(repo_root: Path, model: str, harness: str | None) -> tuple[dict[str, Any], str]:
    config, err = pinned_config(repo_root)
    if err:
        raise WorkerError(f"orchestration config: {err}")
    entry = roster_entry(config, model)
    if entry is None:
        raise WorkerError(f"{model!r} is not in the roster (roadmap/orchestration.yaml)")
    configured = entry.get("harness")
    if harness and configured and harness != configured:
        # The roster is where routing is decided; a flag must not move a
        # model's prompt onto a harness the roster did not name for it.
        raise WorkerError(f"{model!r} is rostered on harness {configured!r}; change roadmap/orchestration.yaml "
                          f"rather than overriding with --harness {harness}")
    return entry, str(harness or configured or "generic")


def _check_eligible(entry: dict[str, Any], node: dict[str, Any], model: str) -> None:
    if "executor" not in (entry.get("roles") or []):
        raise WorkerError(f"{model!r} does not have the executor role in the roster")
    if not is_available(entry):
        raise WorkerError(f"{model!r} is unavailable until {entry.get('unavailable_until')}")
    sens = node_sensitivity(node)
    if not may_handle(entry, sens):
        raise WorkerError(f"{node['id']} is {sens!r}; {model!r} may not process it (`orchestrate plan`)")
    need = node_eligibility(node)
    if need != ANY and str(entry.get("class") or "") != need:
        raise WorkerError(f"{node['id']} needs executor class {need!r}; {model!r} is {entry.get('class') or 'unclassed'}")


def _check_tree(wt: Path, branch: str) -> Path:
    """``wt`` must be a git worktree rooted there with ``branch`` checked out: a stale directory is refused."""
    wt = wt.resolve()
    top = git_text(["rev-parse", "--show-toplevel"], wt) if wt.is_dir() else None
    if not top or Path(top).resolve() != wt:
        raise WorkerError(f"{wt} is not a git worktree; remove it or pass --worktree to a real one")
    current = git_text(["branch", "--show-current"], wt)
    if current != branch:
        raise WorkerError(f"{wt} has {current or 'a detached HEAD'} checked out, not the claim's branch {branch}")
    return wt


def _worktree_for(repo_root: Path, branch: str, codename: str, explicit: Path | None) -> Path:
    if explicit:
        return _check_tree(Path(explicit), branch)
    if git_text(["branch", "--show-current"], repo_root) == branch:
        return repo_root.resolve()
    wt = reviews_root(repo_root).parent / ".worktrees" / codename
    if not wt.exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        r = run(["worktree", "add", str(wt), branch], repo_root)
        if not r.ok:
            raise WorkerError(f"cannot create a worktree for {branch}: {r.err.strip()}")
    return _check_tree(wt, branch)


def _cli_for(repo_root: Path, entry: dict[str, Any]) -> tuple[str | None, str]:
    """``(custom cli, model id the harness is told)``."""
    prof = profile_for_entry(repo_root, entry)
    cli = (entry.get("channels") or {}).get("cli") or (prof.cli() if prof and prof.ok else None)
    return cli, (prof.api_id if prof and prof.ok else str(entry["id"]))


def _preflight(entry: dict[str, Any], repo_root: Path) -> None:
    """The roster entry's ``preflight`` command, as ``prompt --channel cli`` runs it, before any launch."""
    cmd = entry.get("preflight")
    if not cmd:
        return
    rc = subprocess.run(str(cmd), shell=True, cwd=repo_root, check=False).returncode  # noqa: S602 — adopter's own roster
    if rc != 0:
        raise WorkerError(f"preflight failed (exit {rc}): {cmd}; nothing was launched")


def _brief_into(wt: Path, repo_root: Path, node_id: str, t) -> None:
    """The executor's precondition wants ``work/brief-<id>.md`` in **its** tree, and ``work/`` is gitignored."""
    if wt == repo_root.resolve():
        return
    dest = wt / "work" / f"brief-{node_id}.md"
    src = repo_root / "work" / f"brief-{node_id}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        dest.write_text(render_brief(node_id, index(t.nodes), repo_root=repo_root, include_history=False), encoding="utf-8")


def delegate(repo_root: Path, node_id: str, model: str, *, harness: str | None = None,
             worktree: Path | None = None) -> tuple[WorkerRecord, bool]:
    """``(record, created)``: an active worker on the leaf is returned, not duplicated.

    The existing-worker check, the cap and the launch happen under the workers
    lock, so two concurrent delegates on one leaf launch one harness.
    """
    with workers_lock(repo_root):
        return _delegate_locked(repo_root, node_id, model, harness=harness, worktree=worktree)


def _delegate_locked(repo_root: Path, node_id: str, model: str, *, harness: str | None,
                     worktree: Path | None) -> tuple[WorkerRecord, bool]:
    existing = active_for_node(repo_root, node_id)
    if existing and not _wrapper_gone(repo_root, existing):
        return existing, False
    entry, harness = _entry_and_harness(repo_root, model, harness)
    config, _ = pinned_config(repo_root)
    limit = int(config["policy"]["max_workers"])
    active = list_records(repo_root, active_only=True)
    if len(active) >= limit:
        raise WorkerError(f"{len(active)} workers active, policy max_workers is {limit}; "
                          "wait for one to finish or raise the limit")
    t = _target(repo_root, node_id)
    _check_eligible(entry, t.node, model)
    _preflight(entry, repo_root)
    text, _prof, err = build_prompt(repo_root, node_id, role="executor", model=model)
    if err:
        raise WorkerError(err)
    prompt = repo_root / "work" / f"prompt-{node_id}-executor-{model}.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(text, encoding="utf-8")
    branch = str(t.entry["branch"])
    wt = _worktree_for(repo_root, branch, str(t.node.get("codename") or node_id), worktree)
    _brief_into(wt, repo_root, node_id, t)
    cli, api_id = _cli_for(repo_root, entry)
    launch = adapter_for(harness).launch(prompt, wt, api_id, cli)
    rec = create_record(repo_root, node_id, harness, model, wt, branch=branch,
                        contract_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        billing_route=entry.get("billing_route"))
    try:
        spawn(repo_root, rec, launch)
    except OSError as e:
        append_event(repo_root, rec, "error", source="system", summary=f"cannot start the wrapper: {e}")
        set_state(repo_root, rec, "failed", pid=None)
        raise WorkerError(f"{rec.worker_id}: cannot start the wrapper: {e}") from None
    return rec, True


def _wrapper_gone(repo_root: Path, rec: WorkerRecord) -> bool:
    """A record that says ``running``/``starting`` with no live wrapper: close it so the leaf is free again."""
    if rec.state not in ("running", "starting") or pid_alive(rec.pid, rec.worker_id):
        return False
    append_event(repo_root, rec, "error", source="system",
                 summary=f"wrapper pid {rec.pid or '-'} is gone without recording an exit; marked failed")
    set_state(repo_root, rec, "failed", pid=None)
    return True


def _send(repo_root: Path, rec: WorkerRecord, text: str, kind: str) -> WorkerRecord:
    require_writer(rec)
    _wrapper_gone(repo_root, rec)   # a crashed turn is a failure to record, not a worker to resume
    if rec.state in CLOSED_STATES:
        raise WorkerError(f"{rec.worker_id} is {rec.state}; delegate again instead")
    if pid_alive(rec.pid, rec.worker_id):
        raise WorkerError(f"{rec.worker_id} is still running (pid {rec.pid}); the CLI adapters cannot steer a "
                          "live turn — wait for it to end, or terminate it")
    adapter = adapter_for(rec.harness)
    if not adapter.caps.resume:
        raise Unsupported(f"unsupported by {rec.harness}: resume")
    if not rec.provider_session_id:
        raise WorkerError(f"{rec.worker_id} has no native session id yet; nothing to resume")
    entry, _ = _entry_and_harness(repo_root, rec.model, rec.harness)
    _check_eligible(entry, _target(repo_root, rec.node_id).node, rec.model)   # availability and sensitivity can change
    _preflight(entry, repo_root)
    cli, api_id = _cli_for(repo_root, entry)
    n = rec.last_event_seq + 1
    prompt = repo_root / "work" / f"prompt-{rec.worker_id}-{kind}-{n}.md"
    prompt.write_text(text, encoding="utf-8")
    launch = adapter.resume(rec.provider_session_id, prompt, Path(rec.worktree), api_id, cli)
    append_event(repo_root, rec, "message", source="orchestrator", authority="orchestrator",
                 summary=f"{kind}: {' '.join(text.split())[:300]}")
    spawn(repo_root, rec, launch, resumed=True)
    return rec


def message(repo_root: Path, worker_id: str, text: str) -> WorkerRecord:
    with workers_lock(repo_root):   # check, event and spawn as one transition
        return _send(repo_root, load_record(repo_root, worker_id), text, "message")


def resume(repo_root: Path, worker_id: str) -> WorkerRecord:
    with workers_lock(repo_root):
        return _send(repo_root, load_record(repo_root, worker_id), CONTINUE_PROMPT, "resume")


def interrupt(repo_root: Path, worker_id: str) -> None:
    rec = load_record(repo_root, worker_id)
    if not adapter_for(rec.harness).caps.interrupt:
        raise Unsupported(f"unsupported by {rec.harness}: interrupt (a one-shot CLI has no interrupt short of "
                          "`worker terminate`, which loses the turn)")


def terminate(repo_root: Path, worker_id: str) -> WorkerRecord:
    with workers_lock(repo_root):
        return _terminate_locked(repo_root, load_record(repo_root, worker_id))


def _terminate_locked(repo_root: Path, rec: WorkerRecord) -> WorkerRecord:
    if rec.state == "terminated":
        return rec
    if rec.lease.get("holder") == "human":
        raise WorkerError(f"{rec.worker_id} is handed off to a human; `worker reclaim` first")
    summary = "terminated by the coordinator"
    if rec.lease.get("holder") == "native":
        summary = "record closed; the adopted native session was not signalled (observe-only lease)"
    elif pid_alive(rec.pid, rec.worker_id):
        if not pid_verified(rec.pid, rec.worker_id):
            raise WorkerError(f"pid {rec.pid} cannot be verified as {rec.worker_id}'s wrapper (ps unavailable or "
                              "another command line); refusing to signal it")
        # The wrapper is a session leader (start_new_session), so its process
        # group holds the harness and everything the harness spawned.
        try:
            os.killpg(os.getpgid(int(rec.pid)), signal.SIGTERM)
        except OSError as e:
            raise WorkerError(f"cannot signal pid {rec.pid}: {e}") from None
    set_state(repo_root, rec, "terminated", pid=None)
    append_event(repo_root, rec, "terminated", source="orchestrator", authority="orchestrator", summary=summary)
    return rec


def adopt(repo_root: Path, node_id: str, harness: str, session_id: str, *,
          worktree: Path | None = None, model: str = "unknown") -> WorkerRecord:
    t = _target(repo_root, node_id)
    with workers_lock(repo_root):
        existing = active_for_node(repo_root, node_id)
        if existing:
            raise WorkerError(f"{node_id} already has an active worker ({existing.worker_id}, {existing.state})")
        if any(r.provider_session_id == session_id and r.active for r in list_records(repo_root)):
            raise WorkerError(f"session {session_id} is already a worker")
        wt = _worktree_for(repo_root, str(t.entry["branch"]), str(t.node.get("codename") or node_id), worktree)
        rec = create_record(repo_root, node_id, harness, model, wt, branch=str(t.entry["branch"]), lease="native")

        def fn(r: WorkerRecord) -> None:
            r.provider_session_id = session_id
            r.state = "idle"
        mutate(repo_root, rec, fn)
        take_checkpoint(repo_root, rec)
        append_event(repo_root, rec, "adopted", source="orchestrator", authority="orchestrator",
                     summary=f"adopted native {harness} session {session_id}; observe only")
    return rec


from specy_road.worker_lease import handoff, interventions_path, reclaim, record_hook_prompt  # noqa: E402,F401 — re-exported
from specy_road.worker_reconcile import reconcile, sync  # noqa: E402,F401 — re-exported; the CLI calls ops.reconcile/ops.sync


