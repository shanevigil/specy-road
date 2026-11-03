"""``worker delegate``: the roster and eligibility checks, the worktree, and the launch (slice 7c).

Split from :mod:`specy_road.worker_ops` for the file limit; callers reach
these through that module.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.generate_brief import index, render_brief
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.git_subprocess import git_text, run
from specy_road.orchestrate_plan import ANY, is_available, may_handle, node_eligibility, node_sensitivity
from specy_road.orchestration_config import roster_entry
from specy_road.orchestration_pinned import pinned_config, pinned_profile_for_entry
from specy_road.review_files import reviews_dir, reviews_root
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import git_root, project_prefix
from specy_road.worker_adapter_parsers import effort_note
from specy_road.worker_adapters import adapter_for
from specy_road.worker_lease import acquire_lease, foreign_leases, release_lease
from specy_road.worker_ops_slots import _slot_or_existing
from specy_road.worker_reconcile import _bookkeeping
from specy_road.worker_runner import spawn
from specy_road.worker_state import (
    WorkerError,
    WorkerRecord,
    append_event,
    create_record,
    set_state,
    status_entries,
    workers_lock,
)


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
        # The git root, not a nested project root: the harness runs in the recorded
        # tree, and the prompt and brief give their paths from the git root.
        return git_root(repo_root)
    wt = reviews_root(repo_root).parent / ".worktrees" / codename
    if not wt.exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        r = run(["worktree", "add", str(wt), branch], repo_root)
        if not r.ok:
            raise WorkerError(f"cannot create a worktree for {branch}: {r.err.strip()}")
    return _check_tree(wt, branch)


def _cli_for(repo_root: Path, entry: dict[str, Any], harness: str) -> tuple[str | None, str | None, str, str | None]:
    """``(custom cli, model id the harness is told, profile's access.launch_mode, executor effort level)``.

    ``channels.cli`` wins; a profile's ``access.cli`` stands in only for ``generic``, since a named
    harness's default command is what gives it JSON events and a session id. A worker is an
    executor, so its effort is the profile's ``effort_by_role.executor`` (``None``: the harness's own).
    """
    prof = pinned_profile_for_entry(repo_root, entry)   # the committed profile, as the roster is
    if prof is not None and not prof.ok:
        raise WorkerError(f"profile for {entry.get('id')!r}: " + "; ".join(prof.errors))
    cli = (entry.get("channels") or {}).get("cli")
    if not cli and harness == "generic" and prof is not None:
        cli = prof.cli()
    if prof is None:
        return cli, str(entry["id"]), "full", None
    api_id = None if prof.api_id.strip().lower() == "unknown" else prof.api_id   # unknown: harness default
    effort = prof.effort("executor")
    note = effort_note(cli, effort)
    if note:
        print(note, file=sys.stderr)
    return cli, api_id, prof.launch_mode(), effort


def _preflight(entry: dict[str, Any], repo_root: Path) -> None:
    """The roster entry's ``preflight`` command, as ``prompt --channel cli`` runs it, before any launch."""
    cmd = entry.get("preflight")
    if not cmd:
        return
    rc = subprocess.run(str(cmd), shell=True, cwd=repo_root, check=False).returncode  # noqa: S602 — adopter's own roster
    if rc != 0:
        raise WorkerError(f"preflight failed (exit {rc}): {cmd}; nothing was launched")


def _brief_into(wt: Path, repo_root: Path, node_id: str, t) -> None:
    """The executor's precondition wants ``work/brief-<id>.md`` under **its** tree's project root (the
    prompt names it from the git root in the nested layout), and ``work/`` may be gitignored."""
    dest = git_root(wt) / project_prefix(repo_root) / "work" / f"brief-{node_id}.md"   # wt is a checked git tree
    if dest.is_file():
        return
    src = repo_root / "work" / f"brief-{node_id}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        dest.write_text(render_brief(node_id, index(t.nodes), repo_root=repo_root, include_history=False), encoding="utf-8")


def delegate(repo_root: Path, node_id: str, model: str, *, harness: str | None = None,
             worktree: Path | None = None, offline: bool = False) -> tuple[WorkerRecord, bool]:
    """``(record, created)``: an active worker on the leaf is returned, not duplicated.

    The existing-worker check, the cap and the launch happen under the workers lock, so two concurrent delegates
    on one leaf launch one harness. The roster's ``preflight`` and the prompt build run **between** two lock
    sections, not under one: a hook witness must never queue behind them. ``offline`` counts this checkout's
    workers only and pushes no lease (worker_lease)."""
    entry, harness = _entry_and_harness(repo_root, model, harness)
    with workers_lock(repo_root):   # before any network read: a retry is answered while the remote is down
        if existing := _slot_or_existing(repo_root, node_id):
            return existing, False
    foreign = foreign_leases(repo_root, offline=offline)   # other checkouts' workers: a network read, so outside the lock
    with workers_lock(repo_root):
        if existing := _slot_or_existing(repo_root, node_id, foreign=foreign):
            return existing, False
    t = _target(repo_root, node_id)
    _check_eligible(entry, t.node, model)
    _preflight(entry, repo_root)
    text, _prof, err = build_prompt(repo_root, node_id, role="executor", model=model)
    if err:
        raise WorkerError(err)
    with workers_lock(repo_root):
        existing = _slot_or_existing(repo_root, node_id, foreign=foreign)   # re-checked: another delegate may have landed
        if existing:
            return existing, False
        return _launch_locked(repo_root, node_id, model, harness, entry, t, text, worktree, offline), True


def _launch_locked(repo_root: Path, node_id: str, model: str, harness: str, entry: dict[str, Any], t,
                   text: str, worktree: Path | None, offline: bool = False) -> WorkerRecord:
    branch = str(t.entry["branch"])
    wt = _worktree_for(repo_root, branch, str(t.node.get("codename") or node_id), worktree)
    # The worker edits this tree: uncommitted work in it could be overwritten, and
    # `reconcile` could not tell the worker's edits from it. Only the leaf's own
    # untracked bookkeeping is exempt (pickup leaves the brief there untracked).
    entries = status_entries(wt)
    if entries is None:
        raise WorkerError(f"cannot read `git status` in {wt}, so its uncommitted changes are unknown; "
                          "repair that checkout, then delegate again")
    prefix = project_prefix(repo_root)
    dirty = sorted(p for xy, p in entries if not (xy == "??" and _bookkeeping(p, node_id, prefix)))
    if dirty:
        raise WorkerError(f"{wt} has uncommitted changes the worker could overwrite: {', '.join(dirty)}; "
                          "commit or stash them, then delegate again")
    prompt = repo_root / "work" / f"prompt-{node_id}-executor-{model}.md"   # written only once the tree is clean
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(text, encoding="utf-8")
    _brief_into(wt, repo_root, node_id, t)
    cli, api_id, mode, effort = _cli_for(repo_root, entry, harness)
    reviews_dir(repo_root, node_id).mkdir(parents=True, exist_ok=True)   # a harness may refuse an --add-dir that is missing
    launch = adapter_for(harness).launch(prompt, wt, api_id, cli, node_id=node_id, repo_root=repo_root,
                                         launch_mode=mode, effort=effort)
    rec = create_record(repo_root, node_id, harness, model, wt, branch=branch,
                        contract_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        billing_route=entry.get("billing_route"))
    try:
        acquire_lease(repo_root, rec, new=True, offline=offline)   # before the harness: another checkout may hold the slot
    except WorkerError as e:
        append_event(repo_root, rec, "error", source="system", summary=str(e))
        set_state(repo_root, rec, "failed", pid=None)
        raise
    try:
        spawn(repo_root, rec, launch)
    except OSError as e:
        append_event(repo_root, rec, "error", source="system", summary=f"cannot start the wrapper: {e}")
        set_state(repo_root, rec, "failed", pid=None)
        release_lease(repo_root, rec.worker_id)
        raise WorkerError(f"{rec.worker_id}: cannot start the wrapper: {e}") from None
    return rec
