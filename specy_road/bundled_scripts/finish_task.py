#!/usr/bin/env python3
"""Close the current roadmap feature branch: update status, deregister, validate, commit."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from specy_road.brief_acceptance import acceptance_ids
from specy_road.cli_args import add_remote_arg
from specy_road.cli_entry import run_reporting
from specy_road.decisions import DECISIONS_REL
from specy_road.feature_rm_registry import resolve_feature_rm_registry_context_for_finish
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.finish_bookkeeping_undo import bookkeeping_guard, merge_undo_snapshot
from specy_road.finish_milestone_rollout import (
    rollup_session_applies,
    try_milestone_rollup_finish,
)
from specy_road.finish_implementation_check import base_ref
from specy_road.finish_modes import (
    apply_on_complete_mode,
    close_merged_checkout,
    delete_branch_preflight,
    merge_landing_preflight,
)
from specy_road.finish_on_complete_override import on_complete_override_or_exit
from specy_road.finish_pr_body import pr_body_modes, write_pr_body
from specy_road.finish_pr_merge import pr_merge_integration_or_exit
from specy_road.finish_work_artifacts import (
    cleanup_session_sidecar,
    cleanup_work_artifacts,
    remove_main_checkout_pickup_files,
    warn_if_pr_body_tracked,
    worker_logs_to_stage,
)
from specy_road.generated_files import (
    GENERATED_COMMITTED,
    gitignore_resolution_hint,
    unstageable_generated_files,
)
from specy_road.git_subprocess import git_run
from specy_road.git_workflow_config import (
    ON_COMPLETE_MODES,
    merge_request_requires_manual_approval,
    resolve_integration_defaults,
    resolve_on_complete,
    should_cleanup_work_artifacts_on_finish,
)
from specy_road.milestone_session import milestone_session_path, read_milestone_session
from specy_road.on_complete_session import (
    on_complete_session_path,
    read_on_complete_session,
)
from specy_road.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.planning_scaffold_check import scaffold_planning_or_exit
from specy_road.registry_yaml import registry_path, write_registry
from specy_road.repo_lock import pickup_finish_lock
from specy_road.repo_ops import current_branch
from specy_road.review_gate import gate_holds_at_head_or_exit, review_required, trial_merge_or_exit
from specy_road.review_override import OPERATOR, PM_GUI
from specy_road.review_policy_pin import pin_holds_or_exit
from specy_road.review_policy_ref import committed_yaml
from specy_road.roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.steering_gate import zones_or_exit
from specy_road.worker_orphans import end_finished_workers
from specy_road.worker_state import WorkerError

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "Mark the current roadmap task complete, validate, export, digest, commit.\n"
    "\n"
    "Finishing the last open leaf under a parent also flips that parent "
    "to Complete, in the same bookkeeping commit, walking up as far as "
    "the rollup reaches. Nothing is printed when there is nothing to "
    "close, so a run that leaves other leaves open looks the same as "
    "one with no parents to close.\n"
    "\n"
    "The exception is a node carrying a milestone_execution block "
    "(written by start-milestone-session): its status belongs to the "
    "milestone-rollup state machine, which closes it only once the "
    "rollup branch is proven merged. Use "
    "specy-road reconcile-milestone-status for those.\n"
    "\n"
    "--on-complete merge (and auto when merge succeeds) lands on the "
    "integration branch and pushes it. --push only pushes the feature "
    "branch; it does not open the PR. The printed gh/glab command is pasteable."
)


def _add_landing_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--push",
        action="store_true",
        help=(
            "After the bookkeeping commit, run git push -u <remote> <branch>. "
            "Does not open the PR — the gh/glab line is printed for you."
        ),
    )
    add_remote_arg(p, help="Remote for --push (default: origin).", default="origin")
    p.add_argument(
        "--on-complete",
        choices=sorted(ON_COMPLETE_MODES),
        default=None,
        metavar="MODE",
        help=(
            "Override completion workflow: pr, merge, or auto. "
            "merge lands on the integration branch and pushes it. "
            "Default: session file from do-next-available-task, then "
            "SPECY_ROAD_ON_COMPLETE / roadmap/git-workflow.yaml. A value other "
            "than pr that differs from that default is refused unless "
            "--override-on-complete is also passed."
        ),
    )
    p.add_argument(
        "--override-on-complete",
        action="store_true",
        help=(
            "Acknowledge that --on-complete changes the repository's configured "
            "landing mode. A person's choice: agents do not pass it on their own."
        ),
    )
    p.add_argument(
        "--delete-branch",
        action="store_true",
        help=(
            "Once the merge lands on the integration branch (merge, or auto "
            "when its merge succeeds), delete the feature branch locally and "
            "on the remote. Refused under pr: there the branch is the only "
            "copy of the work until the PR merges."
        ),
    )
    p.add_argument(
        "--land-check-cmd",
        default=None,
        metavar="CMD",
        help=(
            "Shell command run at the project root of a detached worktree of "
            "the local merge commit, before merge mode pushes it; a non-zero "
            "exit pushes nothing and resets the integration branch. An empty "
            "value skips the check for this run. Default: the checks: entries "
            "with when: land in roadmap/git-workflow.yaml. pr mode never runs it."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road finish-this-task`` parser."""
    p = argparse.ArgumentParser(
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_landing_args(p)
    add_repo_root_arg(p)
    p.add_argument(
        "--no-cleanup-work",
        action="store_true",
        help=(
            "Keep work/brief-, work/prompt-, and work/implementation-summary- for this node "
            "(default: delete after successful validate/export/digest)."
        ),
    )
    p.add_argument(
        "--allow-empty-implementation",
        action="store_true",
        help=(
            "Finish even though the branch changes no file under the node's "
            "declared touch zones. For a leaf that genuinely needs no code "
            "change; otherwise fix the zones or abort the pickup."
        ),
    )
    p.add_argument(
        "--allow-scaffold-planning",
        action="store_true",
        help=(
            "Finish even though the node's planning sheet still has the "
            "scaffold-planning or brainstorm promote placeholder text. "
            "Otherwise write the sheet and commit it on this branch."
        ),
    )
    p.add_argument(
        "--no-milestone-rollup",
        action="store_true",
        help=(
            "Skip milestone dual-land (cherry-pick bookkeeping to integration + merge "
            "leaf into rollup) when work/.milestone-session.yaml exists; use normal "
            "on_complete instead."
        ),
    )
    return p


def parse_finish_args(argv: list[str] | None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main (split into focused helpers to stay within line limits)
# ---------------------------------------------------------------------------


def _resolve_context(
    root: Path,
    branch: str,
    on_complete: str | None = None,
    *,
    delete_branch: bool = False,
    no_milestone_rollup: bool = False,
    land_check_cmd: str | None = None,
) -> tuple[str, dict, dict, list[dict]]:
    """Return (codename, registry_doc, entry, nodes) or raise SystemExit."""
    return resolve_feature_rm_registry_context_for_finish(
        root, branch, on_complete, delete_branch=delete_branch,
        no_milestone_rollup=no_milestone_rollup, land_check_cmd=land_check_cmd,
    )


def _update_chunk_status(root: Path, node_id: str) -> list[str]:
    """Patch status in JSON chunk file; return list of changed file paths."""
    chunk = find_chunk_path(root, node_id)
    if not chunk:
        print(f"[warn] chunk file not found for {node_id} — set status manually.")
        return []
    if chunk.suffix.lower() != ".json":
        print(
            f"[warn] chunk {chunk.relative_to(root)} is not .json — set status manually.",
            file=sys.stderr,
        )
        return []
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n.get("id") == node_id:
            n["status"] = "Complete"
            write_json_chunk(chunk, nodes)
            print(f"[ok] status -> Complete  ({chunk.relative_to(root)})")
            return [str(chunk.relative_to(root))]
    print(f"[warn] node {node_id} not found in {chunk.relative_to(root)}")
    return []


def _validate_export_digest(root: Path) -> None:
    """validate, export, digest — every generated-and-committed file refreshed.

    digest belongs here for the same reason export does: ``digest --check`` is
    advertised as a CI drift gate, so a finish that leaves ``roadmap-context.md``
    stale hands CI a failure the dev never saw.
    """
    rr = ["--repo-root", str(root)]
    for command in ("validate", "export", "digest"):
        subprocess.check_call(
            [sys.executable, "-m", "specy_road.cli", command, *rr], cwd=root
        )


# ---------------------------------------------------------------------------
# Acceptance items only a person can satisfy
# ---------------------------------------------------------------------------
#
# A criterion such as *a named person approves the wording* or *a link only a
# person can supply* cannot be judged from a diff. Marked ``human:``, it is
# ``n/a`` for reviewers (:func:`role_prompt_rca.reviewer_preamble` says so and
# ``review_semantic_errors`` never counts ``n/a`` as a fail), and
# ``finish-this-task`` instead requires a person's decision for it in the
# decisions ledger (M22.69): a closed ``kind: human-action`` entry with ``node``
# the leaf, ``criterion: A#``, ``decided_by: operator`` and ``channel``
# ``terminal`` (``decisions close`` at an interactive terminal) or ``pm-gui``
# (the PM GUI's answer). Only ``roadmap/decisions.yaml`` as committed at the leaf
# branch's HEAD or at the integration branch tip counts; the working tree,
# ``decisions.local.yaml`` and a planning-sheet ``A#:`` line do not, since any
# agent can write those.

HUMAN_PREFIX = "human:"
TERMINAL = "terminal"   # the ``channel`` of a criterion decision confirmed at a person's terminal
PERSON_CHANNELS = (TERMINAL, PM_GUI)


def is_human_item(text: str) -> bool:
    return text.strip().lower().startswith(HUMAN_PREFIX)


def human_criteria(node: dict) -> dict[str, str]:
    """``A#`` -> text of ``node``'s criteria that start with ``human:``."""
    items = [a for a in node.get("acceptance") or [] if isinstance(a, str) and a.strip()]
    return {aid: text for aid, text in zip(acceptance_ids(node), items) if is_human_item(text)}


def human_acceptance_ids(node: dict) -> list[str]:
    """The ``A#`` ids of ``node``'s criteria that start with ``human:``."""
    return list(human_criteria(node))


def undecided_human_items(root: Path, node: dict, integration_ref: str | None, head: str = "HEAD") -> list[str]:
    """The ``human:`` ids with no person's closed ledger entry at ``head`` or at ``integration_ref``."""
    human = human_acceptance_ids(node)
    if not human:
        return []
    decided: set[str] = set()
    for ref in (head, integration_ref):
        if not ref:
            continue
        for e in committed_yaml(root, ref, DECISIONS_REL.as_posix()).get("entries") or []:
            if isinstance(e, dict) and e.get("kind") == "human-action" and e.get("node") == node["id"] \
                    and e.get("status") == "closed" and e.get("decided_by") == OPERATOR \
                    and e.get("channel") in PERSON_CHANNELS:
                decided.add(str(e.get("criterion")))
    return [aid for aid in human if aid not in decided]


def human_acceptance_or_exit(root: Path, node: dict, integration_ref: str | None) -> None:
    """Stop ``finish-this-task`` while a ``human:`` item has no person's decision in the committed ledger."""
    missing = undecided_human_items(root, node, integration_ref)
    if not missing:
        return
    nid, first = node["id"], missing[0]
    where = "this branch or the integration branch" if integration_ref else "this branch"
    print(
        f"error: {nid} has human acceptance item(s) with no person's decision: {', '.join(missing)}.\n"
        "  Reviewers mark a `human:` item n/a; the person it names decides it in roadmap/decisions.yaml.\n"
        "  A planning-sheet `A#:` line no longer counts.\n"
        f"  Open one entry per item: specy-road decisions add {nid} --kind human-action --criterion {first} "
        "--summary ... --why ... --option ... --recommendation ... --recommendation-reason ... --default ...\n"
        "  A person then closes it: `specy-road decisions close <ID> --answer ...` in their own terminal, or the\n"
        f"  answer in the PM GUI's Status window. The closed entry must be committed on {where}; then run\n"
        "  finish-this-task again.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _impl_review_or_exit(root: Path, entry: dict, node: dict) -> None:
    node_id = node["id"]
    # Before the switch: turning it off after the claim is a policy change too.
    pin_holds_or_exit(root, node)
    if not review_required(root):
        return
    if entry.get("implementation_review") == "approved":
        return gate_holds_at_head_or_exit(root, node)
    print(
        "error: implementation review is required before finish-this-task.",
        file=sys.stderr,
    )
    print(
        "  Run: specy-road mark-implementation-reviewed "
        "(after work/implementation-summary-"
        f"{node_id}.md is written and a review is recorded — "
        f"see specy-road review status {node_id}).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _resolve_main_context(root: Path, args: argparse.Namespace, branch: str) -> dict:
    """Resolve all main-time context in one call (keeps main() under cap)."""
    codename, reg, entry, nodes = _resolve_context(
        root, branch, args.on_complete, delete_branch=args.delete_branch,
        no_milestone_rollup=args.no_milestone_rollup, land_check_cmd=args.land_check_cmd,
    )
    node_id = entry["node_id"]
    node = next(n for n in nodes if n["id"] == node_id)
    work_dir = root / "work"
    sess_path = on_complete_session_path(work_dir, node_id)
    session_oc = read_on_complete_session(
        sess_path, node_id=node_id, codename=codename,
    )
    on_mode = resolve_on_complete(
        root, cli=args.on_complete, session=session_oc,
    )
    rollup = rollup_session_applies(
        read_milestone_session(milestone_session_path(work_dir)),
        skip=args.no_milestone_rollup,
        node_id=node_id,
        nodes=nodes,
    )
    delete_branch_preflight(on_mode, delete_branch=args.delete_branch, rollup=rollup)
    trial_merge_or_exit(root)
    scaffold_planning_or_exit(root, node, allow=args.allow_scaffold_planning)
    ib, gw_remote, _gw = resolve_integration_defaults(
        root, explicit_base=None, explicit_remote=None,
    )
    human_acceptance_or_exit(root, node, base_ref(root, gw_remote, ib))
    _impl_review_or_exit(root, entry, node)
    zones_or_exit(   # the implementation check, then the steering files
        root, node=node, entry=entry, node_id=node_id,
        remote=gw_remote, integration_branch=ib,
        allow_empty=args.allow_empty_implementation,
    )
    if on_mode == "merge":
        merge_landing_preflight(root, ib)
    print(f"Finishing [{node_id}] {node.get('title', '')}")
    print(f"Branch:   {branch}")
    print(f"on_complete: {on_mode}\n")
    return {
        "codename": codename, "reg": reg, "entry": entry, "nodes": nodes,
        "node": node, "node_id": node_id, "work_dir": work_dir,
        "sess_path": sess_path, "on_mode": on_mode, "ib": ib,
        "gw_remote": gw_remote, "rollup": rollup,
    }


def _maybe_write_pr_body(
    *,
    on_mode: str,
    work_dir: Path,
    node_id: str,
    node: dict,
    codename: str,
    branch: str,
    integration_branch: str,
) -> Path | None:
    """F-015: snapshot the impl-summary + brief into work/pr-body-<NODE>.md
    BEFORE cleanup runs. Skip for on_mode=='merge' (no PR is opened)."""
    if on_mode not in pr_body_modes():
        return None
    return write_pr_body(
        work_dir=work_dir,
        node_id=node_id,
        title=node.get("title", ""),
        codename=codename,
        branch=branch,
        integration_branch=integration_branch,
    )


def _stageable_generated_files(root: Path) -> list[str]:
    """The regenerated files to commit, minus any ``git add`` would refuse.

    Only an ignored *untracked* path aborts the whole ``git add``, and dropping
    more than that would be worse than the problem: a file that is ignored but
    already tracked stages fine, and skipping it would leave the regenerated
    copy out of every commit for good. The resolution is the same one
    ``validate``, ``export --check`` and ``digest --check`` print, because
    leaving the file out of this commit is what makes those two gates fail later.
    """
    refused = set(unstageable_generated_files(root))
    for name in refused:
        print(
            f"[warn] not staging {name}: it is gitignored and untracked, so "
            f"`git add` would refuse it and abort this commit."
        )
        hint = gitignore_resolution_hint(root, name)
        if hint:
            print(f"  {hint}")
    return [name for name in GENERATED_COMMITTED if name not in refused]


def _bookkeeping_commit_phase(
    root: Path,
    args: argparse.Namespace,
    codename: str,
    node_id: str,
    branch: str,
    reg: dict,
    *,
    pr_body_path: Path | None = None,
    sess_path: Path | None = None,
    pr_integration: tuple[str, str] | None = None,
) -> None:
    """Commit the bookkeeping, then push under ``--push``.

    ``pr_integration`` is ``(integration branch, remote)`` under
    ``on_complete: pr``: before anything is pushed, the integration tip is
    merged in when only bookkeeping conflicts, and finish exits 1 when
    anything else does, so the PR never opens conflicted.
    """
    changed_files = _update_chunk_status(root, node_id)
    for rel in complete_rolled_up_ancestors(root, node_id):
        if rel not in changed_files:
            changed_files.append(rel)
    changed_files.append(str(registry_path(root).relative_to(root)))
    reg["entries"] = [e for e in reg.get("entries", []) if e.get("codename") != codename]
    write_registry(registry_path(root), reg)
    print(f"[ok] removed registry entry for '{codename}'\n")
    print("-> specy-road validate")
    print("-> specy-road export")
    print("-> specy-road digest")
    _validate_export_digest(root)
    if pr_body_path is not None:
        # Print AFTER export so the dev sees a clean post-commit pointer.
        rel = pr_body_path.relative_to(root)
        print(f"[ok] wrote {rel} (snapshot for PR/MR body, F-015)")
        warn_if_pr_body_tracked(root)
    work_tracked_removals: list[str] = []
    if should_cleanup_work_artifacts_on_finish(
        root,
        no_cleanup_work_cli=args.no_cleanup_work,
    ):
        work_tracked_removals = cleanup_work_artifacts(root, node_id)
    work_tracked_removals.extend(cleanup_session_sidecar(root, sess_path))
    changed_files.extend(worker_logs_to_stage(root, node_id))
    changed_files.extend(_stageable_generated_files(root))
    changed_files.extend(work_tracked_removals)
    git_run(root, "add", *changed_files)
    git_run(root, "commit", "-m", f"chore(rm-{codename}): complete, deregister")
    print("\n[ok] bookkeeping committed")
    if pr_integration is not None:
        pr_merge_integration_or_exit(
            root, branch=branch, ib=pr_integration[0], remote=pr_integration[1],
        )
    if args.push:
        print(f"-> git push -u {args.remote} {branch}")
        git_run(root, "push", "-u", args.remote, branch)


def _end_leaf_workers(root: Path, node_id: str) -> None:
    """The finished leaf's idle and completed workers can get no fix round now: terminate them.

    Each records a ``terminated`` event, so their ``max_workers`` slots free. Best effort: a
    failure here never fails the finish.
    """
    try:
        ended = end_finished_workers(root, node_id)
    except (WorkerError, OSError) as e:
        print(f"[warn] could not terminate {node_id}'s workers ({e}); "
              "`specy-road worker terminate --orphaned` ends them once the leaf lands")
        return
    for rec, why in ended:
        print(f"[ok] terminated worker {rec.worker_id}: {why}")


def main(argv: list[str] | None = None) -> None:
    """Finish the current leaf. A command error is printed once and becomes its exit code."""
    run_reporting(lambda: _finish(argv))


def _finish(argv: list[str] | None) -> None:
    args = parse_finish_args(argv if argv is not None else sys.argv[1:])
    root = resolve_repo_root(args)
    with pickup_finish_lock(root, operation="finish-this-task"):
        _finish_locked(root, args)


def _finish_locked(root: Path, args) -> None:
    branch = current_branch(root)
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    on_complete_override_or_exit(
        root, cli=args.on_complete, branch=branch,
        acknowledged=args.override_on_complete,
    )

    ctx = _resolve_main_context(root, args, branch)
    codename, reg, nodes = ctx["codename"], ctx["reg"], ctx["nodes"]
    node, node_id = ctx["node"], ctx["node_id"]
    work_dir, sess_path, on_mode = ctx["work_dir"], ctx["sess_path"], ctx["on_mode"]
    ib, gw_remote = ctx["ib"], ctx["gw_remote"]

    # Validate first; a failure before the bookkeeping commit puts every path back.
    with bookkeeping_guard(root, node_id, sess_path):
        # F-015: snapshot the work-packet brief + impl-summary into a PR body
        # markdown BEFORE the cleanup pass deletes the source files. Only when
        # a PR/MR is actually expected (on_mode == 'pr' or 'auto').
        pr_body_path = _maybe_write_pr_body(
            on_mode=on_mode, work_dir=work_dir, node_id=node_id, node=node,
            codename=codename, branch=branch, integration_branch=ib,
        )

        undo = merge_undo_snapshot(root, branch, ctx)   # a failed merge landing restores this
        _bookkeeping_commit_phase(
            root, args, codename, node_id, branch, reg,
            pr_body_path=pr_body_path, sess_path=sess_path,
            pr_integration=(ib, gw_remote) if on_mode == "pr" and not ctx["rollup"] else None,
        )
    _end_leaf_workers(root, node_id)
    mr_manual = merge_request_requires_manual_approval(root)
    cleanup = should_cleanup_work_artifacts_on_finish(
        root, no_cleanup_work_cli=args.no_cleanup_work,
    )

    if try_milestone_rollup_finish(
        root,
        args,
        work_dir=work_dir,
        node_id=node_id,
        nodes=nodes,
        branch=branch,
        sess_path=sess_path,
        ib=ib,
        gw_remote=gw_remote,
    ):
        if cleanup:
            remove_main_checkout_pickup_files(root, node_id)
        return

    apply_on_complete_mode(
        root,
        args,
        on_mode=on_mode,
        branch=branch,
        sess_path=sess_path,
        ib=ib,
        gw_remote=gw_remote,
        mr_manual=mr_manual,
        node_id=node_id,
        node=node,
        pr_body_path=pr_body_path,
        undo=undo,
    )
    close_merged_checkout(
        root, node_id=node_id, branch=branch, ib=ib, on_mode=on_mode,
        delete_branch=args.delete_branch, cleanup=cleanup,
    )


if __name__ == "__main__":
    main()
