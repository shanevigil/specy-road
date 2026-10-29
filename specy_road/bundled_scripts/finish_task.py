#!/usr/bin/env python3
"""Close the current roadmap feature branch: update status, deregister, validate, commit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path, load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.finish_task_args import parse_finish_args
from specy_road.git_workflow_config import (
    merge_request_requires_manual_approval,
    resolve_integration_defaults,
    resolve_on_complete,
    should_cleanup_work_artifacts_on_finish,
)
from specy_road.finish_implementation_check import implementation_or_exit
from specy_road.planning_scaffold_check import scaffold_planning_or_exit
from specy_road.review_gate import gate_holds_at_head_or_exit, review_required, trial_merge_or_exit
from specy_road.finish_pr_body import pr_body_modes, write_pr_body
from specy_road.finish_work_artifacts import (
    cleanup_session_sidecar,
    cleanup_work_artifacts,
    warn_if_pr_body_tracked,
)
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.finish_milestone_rollout import (
    rollup_session_applies,
    try_milestone_rollup_finish,
)
from specy_road.milestone_session import milestone_session_path, read_milestone_session
from specy_road.finish_modes import (
    apply_on_complete_mode,
    delete_branch_preflight,
    merge_landing_preflight,
)
from specy_road.feature_rm_registry import resolve_feature_rm_registry_context_for_finish
from specy_road.generated_files import (
    GENERATED_COMMITTED,
    gitignore_resolution_hint,
    unstageable_generated_files,
)
from specy_road.registry_yaml import registry_path, write_registry
from specy_road.on_complete_session import (
    on_complete_session_path,
    read_on_complete_session,
)
from specy_road.runtime_paths import resolve_repo_root
from specy_road.bundled_scripts.repo_ops import current_branch, git_run

#: Rebound by :func:`main` before any helper runs; this is only a placeholder
#: so the name exists at import. Resolving the real root here would make
#: importing the module shell out to git.
ROOT = Path.cwd()


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _save_registry(doc: dict) -> None:
    write_registry(registry_path(ROOT), doc)


# ---------------------------------------------------------------------------
# Main (split into focused helpers to stay within line limits)
# ---------------------------------------------------------------------------


def _resolve_context(
    branch: str,
    on_complete: str | None = None,
    *,
    delete_branch: bool = False,
    no_milestone_rollup: bool = False,
) -> tuple[str, dict, dict, list[dict]]:
    """Return (codename, registry_doc, entry, nodes) or raise SystemExit."""
    return resolve_feature_rm_registry_context_for_finish(
        ROOT, branch, on_complete, delete_branch=delete_branch,
        no_milestone_rollup=no_milestone_rollup,
    )


def _update_chunk_status(node_id: str) -> list[str]:
    """Patch status in JSON chunk file; return list of changed file paths."""
    chunk = find_chunk_path(ROOT, node_id)
    if not chunk:
        print(f"[warn] chunk file not found for {node_id} — set status manually.")
        return []
    if chunk.suffix.lower() != ".json":
        print(
            f"[warn] chunk {chunk.relative_to(ROOT)} is not .json — set status manually.",
            file=sys.stderr,
        )
        return []
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n.get("id") == node_id:
            n["status"] = "Complete"
            write_json_chunk(chunk, nodes)
            print(f"[ok] status -> Complete  ({chunk.relative_to(ROOT)})")
            return [str(chunk.relative_to(ROOT))]
    print(f"[warn] node {node_id} not found in {chunk.relative_to(ROOT)}")
    return []


def _validate_export_digest() -> None:
    """validate, export, digest — every generated-and-committed file refreshed.

    digest belongs here for the same reason export does: ``digest --check`` is
    advertised as a CI drift gate, so a finish that leaves ``roadmap-context.md``
    stale hands CI a failure the dev never saw.
    """
    rr = ["--repo-root", str(ROOT)]
    for command in ("validate", "export", "digest"):
        subprocess.check_call(
            [sys.executable, "-m", "specy_road.cli", command, *rr], cwd=ROOT
        )


def _impl_review_or_exit(entry: dict, node: dict) -> None:
    node_id = node["id"]
    if not review_required(ROOT):
        return
    if entry.get("implementation_review") == "approved":
        return gate_holds_at_head_or_exit(ROOT, node)
    print(
        "error: implementation review is required before finish-this-task.",
        file=sys.stderr,
    )
    print(
        "  Run: specy-road mark-implementation-reviewed "
        "(after work/implementation-summary-"
        f"{node_id}.md is written and a review is recorded — "
        f"see specy-road handoff status {node_id}).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _resolve_main_context(args: argparse.Namespace, branch: str) -> dict:
    """Resolve all main-time context in one call (keeps main() under cap)."""
    codename, reg, entry, nodes = _resolve_context(
        branch, args.on_complete, delete_branch=args.delete_branch,
        no_milestone_rollup=args.no_milestone_rollup,
    )
    node_id = entry["node_id"]
    node = next(n for n in nodes if n["id"] == node_id)
    work_dir = ROOT / "work"
    sess_path = on_complete_session_path(work_dir, node_id)
    session_oc = read_on_complete_session(
        sess_path, node_id=node_id, codename=codename,
    )
    on_mode = resolve_on_complete(
        ROOT, cli=args.on_complete, session=session_oc,
    )
    delete_branch_preflight(
        on_mode,
        delete_branch=args.delete_branch,
        rollup=rollup_session_applies(
            read_milestone_session(milestone_session_path(work_dir)),
            skip=args.no_milestone_rollup,
            node_id=node_id,
            nodes=nodes,
        ),
    )
    trial_merge_or_exit(ROOT)
    scaffold_planning_or_exit(ROOT, node, allow=args.allow_scaffold_planning)
    _impl_review_or_exit(entry, node)
    ib, gw_remote, _gw = resolve_integration_defaults(
        ROOT, explicit_base=None, explicit_remote=None,
    )
    implementation_or_exit(
        ROOT, node=node, entry=entry, node_id=node_id,
        remote=gw_remote, integration_branch=ib,
        allow_empty=args.allow_empty_implementation,
    )
    if on_mode == "merge":
        merge_landing_preflight(ROOT, ib)
    print(f"Finishing [{node_id}] {node.get('title', '')}")
    print(f"Branch:   {branch}")
    print(f"on_complete: {on_mode}\n")
    return {
        "codename": codename, "reg": reg, "entry": entry, "nodes": nodes,
        "node": node, "node_id": node_id, "work_dir": work_dir,
        "sess_path": sess_path, "on_mode": on_mode, "ib": ib,
        "gw_remote": gw_remote,
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


def _stageable_generated_files() -> list[str]:
    """The regenerated files to commit, minus any ``git add`` would refuse.

    Only an ignored *untracked* path aborts the whole ``git add``, and dropping
    more than that would be worse than the problem: a file that is ignored but
    already tracked stages fine, and skipping it would leave the regenerated
    copy out of every commit for good.     The resolution is the same one ``validate``, ``export --check`` and
    ``digest --check`` print, because leaving the file out of this commit is
    what makes those two gates fail later.
    """
    refused = set(unstageable_generated_files(ROOT))
    for name in refused:
        print(
            f"[warn] not staging {name}: it is gitignored and untracked, so "
            f"`git add` would refuse it and abort this commit."
        )
        hint = gitignore_resolution_hint(ROOT, name)
        if hint:
            print(f"  {hint}")
    return [name for name in GENERATED_COMMITTED if name not in refused]


def _bookkeeping_commit_phase(
    args: argparse.Namespace,
    codename: str,
    node_id: str,
    branch: str,
    reg: dict,
    *,
    pr_body_path: Path | None = None,
    sess_path: Path | None = None,
) -> None:
    changed_files = _update_chunk_status(node_id)
    for rel in complete_rolled_up_ancestors(ROOT, node_id):
        if rel not in changed_files:
            changed_files.append(rel)
    changed_files.append(str(registry_path(ROOT).relative_to(ROOT)))
    reg["entries"] = [e for e in reg.get("entries", []) if e.get("codename") != codename]
    _save_registry(reg)
    print(f"[ok] removed registry entry for '{codename}'\n")
    print("-> specy-road validate")
    print("-> specy-road export")
    print("-> specy-road digest")
    _validate_export_digest()
    if pr_body_path is not None:
        # Print AFTER export so the dev sees a clean post-commit pointer.
        rel = pr_body_path.relative_to(ROOT)
        print(f"[ok] wrote {rel} (snapshot for PR/MR body, F-015)")
        warn_if_pr_body_tracked(ROOT)
    work_tracked_removals: list[str] = []
    if should_cleanup_work_artifacts_on_finish(
        ROOT,
        no_cleanup_work_cli=args.no_cleanup_work,
    ):
        work_tracked_removals = cleanup_work_artifacts(ROOT, node_id)
    work_tracked_removals.extend(cleanup_session_sidecar(ROOT, sess_path))
    changed_files.extend(_stageable_generated_files())
    changed_files.extend(work_tracked_removals)
    git_run(ROOT, "add", *changed_files)
    git_run(ROOT, "commit", "-m", f"chore(rm-{codename}): complete, deregister")
    print("\n[ok] bookkeeping committed")
    if args.push:
        print(f"-> git push -u {args.remote} {branch}")
        git_run(ROOT, "push", "-u", args.remote, branch)


def main(argv: list[str] | None = None) -> None:
    global ROOT
    args = parse_finish_args(argv if argv is not None else sys.argv[1:])
    ROOT = resolve_repo_root(args)
    branch = current_branch(ROOT)
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ctx = _resolve_main_context(args, branch)
    codename, reg, nodes = ctx["codename"], ctx["reg"], ctx["nodes"]
    node, node_id = ctx["node"], ctx["node_id"]
    work_dir, sess_path, on_mode = ctx["work_dir"], ctx["sess_path"], ctx["on_mode"]
    ib, gw_remote = ctx["ib"], ctx["gw_remote"]

    # F-015: snapshot the work-packet brief + impl-summary into a PR body
    # markdown BEFORE the cleanup pass deletes the source files. Only when
    # a PR/MR is actually expected (on_mode == 'pr' or 'auto').
    pr_body_path = _maybe_write_pr_body(
        on_mode=on_mode,
        work_dir=work_dir,
        node_id=node_id,
        node=node,
        codename=codename,
        branch=branch,
        integration_branch=ib,
    )

    _bookkeeping_commit_phase(
        args, codename, node_id, branch, reg,
        pr_body_path=pr_body_path, sess_path=sess_path,
    )
    mr_manual = merge_request_requires_manual_approval(ROOT)

    if try_milestone_rollup_finish(
        ROOT,
        args,
        work_dir=work_dir,
        node_id=node_id,
        nodes=nodes,
        branch=branch,
        sess_path=sess_path,
        ib=ib,
        gw_remote=gw_remote,
    ):
        return

    apply_on_complete_mode(
        ROOT,
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
    )


if __name__ == "__main__":
    main()
