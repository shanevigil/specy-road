"""PR/MR tail and merge-to-integration after finish-this-task bookkeeping."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path
from typing import NoReturn

from specy_road.bundled_scripts.grind_session_cleanup import delete_merged_branch
from specy_road.finish_bookkeeping_undo import (
    BookkeepingSnapshot, UndoOutcome, one_line, undo_bookkeeping, undo_report,
)
from specy_road.finish_land_deterministic import codename_from_branch
from specy_road.runtime_paths import project_prefix
from specy_road.finish_land_integration import (
    integration_worktree,
    integration_worktree_problem,
    tracking_ref_snapshot,
)
from specy_road.finish_land_local import land_on_integration
from specy_road.finish_on_complete_override import OVERRIDE_FLAG, needs_override
from specy_road.bundled_scripts.repo_ops import current_branch
from specy_road.finish_work_artifacts import remove_main_checkout_pickup_files
from specy_road.git_subprocess import git_ok
from specy_road.git_workflow_config import should_cleanup_work_artifacts_on_finish
from specy_road.on_complete_session import remove_on_complete_session
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.workflow_prefs import LAND_LOCAL, root_land


def print_finish_tail(
    args: argparse.Namespace,
    *,
    node_id: str,
    node: dict,
    branch: str,
    integration_branch: str,
    mr_manual: bool,
    heading_merge_pending: bool = False,
    pr_body_path: Path | None = None,
) -> None:
    title = f"[{node_id}] {node.get('title', '')}"
    print()
    print("-" * 60)
    if heading_merge_pending:
        print(
            "Merge pending — open a PR/MR (GitHub: PR, GitLab: MR), "
            "or resolve locally:",
        )
        print()
    if not args.push:
        print("Branch ready. Push and open a PR/MR:")
        print(f"  git push -u {args.remote} {branch}")
    else:
        print("Branch pushed. Open a PR/MR:")
    # F-015: pass --body-file (gh) / --description-file (glab) so the PR
    # opens with the impl-summary + work-packet brief snapshot inlined.
    body_arg_gh = ""
    body_arg_glab = ""
    if pr_body_path is not None:
        body_arg_gh = f' --body-file "{pr_body_path}"'
        body_arg_glab = f' --description-file "{pr_body_path}"'
    print(
        f'  gh pr create --base {integration_branch} --head {branch} '
        f'--title "{title}"{body_arg_gh}'
    )
    print(
        "  (GitLab: `glab mr create --target-branch "
        f"{integration_branch} --source-branch {branch} "
        f'--title "{title}"{body_arg_glab}`)',
    )
    if pr_body_path is not None:
        print(
            f"  (Body snapshot: {pr_body_path} — F-015. The roadmap may "
            "evolve after the PR opens; this snapshot does not.)"
        )
    if mr_manual:
        print(
            "  Merge requests require manual approval — wait for review, "
            "then merge.",
        )
    print("-" * 60)


def print_pr_gated_state(
    *, node_id: str, branch: str, integration_branch: str
) -> None:
    """Spell out the two-branch state ``on_complete: pr`` leaves behind.

    The node is Complete and the claim released on the feature branch, while
    the integration branch still shows neither — correct under F-007, and the
    single most misread moment in the workflow, because "finished" and
    "available again" look identical from the integration branch alone.
    """
    print()
    print(f"Where things stand (on_complete: pr) — until the PR merges into {integration_branch}:")
    print(f"  {node_id:<22} Complete on {branch}; unchanged on {integration_branch}")
    print(f"  {'registry claim':<22} released on {branch}; still held on {integration_branch}")
    print(
        "  The claim is what keeps this leaf off the available list, so leave "
        "it in place.\n"
        "  Merging the PR is what closes the node on "
        f"{integration_branch}. Do not re-pick it,\n"
        "  and do not abort it — `abort-task-pickup` deletes the branch and "
        "the work with it.\n"
        f"  Cleaning up stops here: do not merge {branch} into "
        f"{integration_branch} yourself or delete it;\n"
        "  the PR is the team's review step, and `branches prune --delete` "
        "removes the branch once the PR has merged it."
    )


def landing_error_line(ib: str, err_msg: str) -> str:
    """The one outcome line; a multi-line reason goes to stdout in full first (M15.40 A1)."""
    if "\n" in err_msg.strip():
        print(f"\nlanding to {ib} failed:\n" + "\n".join(f"  {ln}" for ln in err_msg.strip().splitlines()))
    sys.stdout.flush()
    return f"\nerror: could not land merge to {ib}: {one_line(err_msg)}"


def merge_landing_failed(
    ib: str, err_msg: str, *, delete_branch: bool = False, land_check_cmd: str | None = None,
    repo: Path | None = None, undo: UndoOutcome | None = None,
) -> NoReturn:
    """Exit 1 after a failed merge landing, naming the re-run that retries it.

    ``undo`` is what this run's undo of its own bookkeeping commit did (M15.40);
    :func:`undo_report` turns it into the next commands. The re-run is then a
    plain ``finish-this-task``, naming the merge override when merge is not the
    configured mode. Without it the branch is one an earlier finish already
    committed, and the re-run has no pickup session file (the bookkeeping commit
    removed it), so when merge is not the configured mode the re-run names the
    acknowledgement flag that mode needs.
    """
    again = "specy-road finish-this-task"
    override = repo is not None and needs_override(repo, "merge")
    if undo is None or override:   # after an undo, merge is re-chosen only when it was an override
        again += " --on-complete merge"
    if override:
        again += f" {OVERRIDE_FLAG}"
    if delete_branch:
        again += " --delete-branch"
    if land_check_cmd is not None:
        again += f" --land-check-cmd {shlex.quote(land_check_cmd)}"
    print(landing_error_line(ib, err_msg), file=sys.stderr)
    if undo is None:
        state = (f"run `{again}` again on this branch: the bookkeeping is already committed, so it "
                 "retries only the landing. Or rerun with --on-complete pr to open a PR instead.")
    else:
        undo_error, state = undo_report(undo, again)
        if undo_error is not None:
            print(undo_error, file=sys.stderr)
    print(
        "\n--on-complete merge cannot fall back to PR instructions. "
        "Fix what the error above names, then " + state,
        file=sys.stderr,
    )
    raise SystemExit(1)


def merge_landing_preflight(repo: Path, ib: str) -> None:
    """Exit 1 before the bookkeeping commit when the merge could not land."""
    problem = integration_worktree_problem(repo, ib)
    if problem is not None:
        print(f"error: cannot land merge to {ib}: {problem}", file=sys.stderr)
        raise SystemExit(1)


def delete_branch_preflight(on_mode: str, *, delete_branch: bool, rollup: bool = False) -> None:
    """Exit 1 before the bookkeeping commit when --delete-branch could delete unlanded work.

    A milestone rollup finish merges the leaf into the rollup branch, so ``pr``
    does not leave that leaf as the only copy.
    """
    if delete_branch and on_mode == "pr" and not rollup:
        print(
            "error: --delete-branch needs a merge landing (--on-complete merge "
            "or auto). Under pr the feature branch is the only copy of the "
            "work until the PR merges; delete it after that with "
            "`specy-road branches prune --delete`.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def delete_landed_branch(
    repo: Path, *, branch: str, ib: str, remote: str, contained_in: str | None = None,
    local_only: bool = False,
) -> None:
    """Delete ``branch`` here and on ``remote`` now that it has landed.

    ``contained_in`` is the ref that holds the branch (the rollup branch, when
    the leaf merged there instead of into ``ib``). The checkout still moves to
    ``ib``, because a checked-out branch cannot be deleted; when another
    worktree holds ``ib``, this checkout detaches at it. Failures are reported,
    never fatal: the work has already landed. ``local_only`` (root ``land:
    local``, which pushes nothing) leaves the remote copy alone.
    """
    holder = integration_worktree(repo, ib)
    # A failed checkout needs no check of its own: git branch -d then refuses and says why.
    git_ok(["checkout", "--detach", ib] if holder else ["checkout", ib], repo)
    pushed = not local_only and git_ok(["rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"], repo)[0]
    local_ok, remote_ok, failure = delete_merged_branch(
        repo, branch, contained_in or ib, remote, push=pushed,
    )
    if local_ok:
        where = f"detached at {ib} ({ib} is checked out in {holder})" if holder else f"on {ib}"
        print(f"[ok] deleted local branch {branch}; this checkout is now {where}")
    if remote_ok:
        print(f"[ok] deleted {branch} on {remote}")
    if failure is not None:
        sys.stdout.flush()
        print(f"[warn] --delete-branch: {failure['message']}", file=sys.stderr)


def drop_main_checkout_pickup_files(repo: Path, node_id: str, *, no_cleanup_work: bool) -> None:
    """Remove the main checkout's untracked brief and prompt when cleanup is on."""
    if should_cleanup_work_artifacts_on_finish(repo, no_cleanup_work_cli=no_cleanup_work):
        remove_main_checkout_pickup_files(repo, node_id)


def close_merged_checkout(
    repo: Path, *, node_id: str, branch: str, ib: str, on_mode: str,
    delete_branch: bool, no_cleanup_work: bool,
) -> None:
    """After finish returns: remove the main checkout's pickup files, then the checkout line.

    A pr finish removes the files and does not print the line. The line is the
    final one, and only for a merge or auto landing that left this checkout on
    ``branch`` without ``--delete-branch``.
    """
    drop_main_checkout_pickup_files(repo, node_id, no_cleanup_work=no_cleanup_work)
    if on_mode not in ("merge", "auto") or delete_branch or current_branch(repo) != branch:
        return
    print(f"[ok] this checkout is still on {branch} (landed into {ib}); next: git switch {ib}")


def report_landed(
    repo: Path, outcome: str, *, branch: str, ib: str, remote: str, delete_branch: bool,
    local_only: bool, sess_path: Path | None = None,
) -> None:
    """Print ``[ok] <outcome>`` after session cleanup and ``--delete-branch``.

    Those steps print first. The outcome is not finish's last line: the main
    checkout's pickup files are removed after this returns, and a checkout that
    stays on the feature branch then prints the switch guidance.
    """
    if sess_path is not None:
        remove_on_complete_session(sess_path)
    if delete_branch:
        delete_landed_branch(repo, branch=branch, ib=ib, remote=remote, local_only=local_only)
    sys.stdout.flush()
    sys.stderr.flush()
    print(f"\n[ok] {outcome}", flush=True)


# What finish-this-task's bookkeeping commit writes; anything else in that commit was never reviewed.
_FINISH_WRITES = ("roadmap/", "roadmap.md", "roadmap-context.md", "work/", "planning/")


def stray_finish_paths(repo: Path, branch: str) -> list[str]:
    """Paths the branch tip changed that finish's bookkeeping never writes.

    git names paths from the repository root, so the finish writes are matched
    under the project prefix (``sr/roadmap/`` in the nested layout).
    """
    _ok, changed = git_ok(["diff", "--name-only", f"{branch}^", branch], repo)
    prefix = project_prefix(repo)
    writes = tuple(prefix + w for w in _FINISH_WRITES)
    return [p for p in changed.splitlines() if not p.startswith(writes)]


def _holds_claim_row(repo: Path, ref: str, codename: str | None) -> bool:
    doc = read_registry_at_ref(repo, ref, 30.0) or {}
    entries = doc.get("entries") or []
    return any(isinstance(e, dict) and e.get("codename") == codename for e in entries)


def refuse_unless_finish_tip(repo: Path, branch: str) -> None:
    """Exit 1 unless ``branch``'s tip is the finish bookkeeping commit.

    A commit added after it was never reviewed. The tip must be the commit
    that removed this leaf's registry row, and that commit must change only
    paths finish itself writes.
    """
    codename = codename_from_branch(branch)
    moved = (
        stray_finish_paths(repo, branch)
        or _holds_claim_row(repo, branch, codename)
        or not _holds_claim_row(repo, f"{branch}^", codename)
    )
    if not moved:
        return
    sys.stdout.flush()
    print(
        f"error: {branch} has moved past its finish-this-task commit; new commits "
        "need review before they land. Re-pick the leaf or open a new leaf for them.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def retry_merge_landing(
    repo: Path, *, branch: str, ib: str, remote: str, delete_branch: bool = False,
    land_check_cmd: str | None = None,
) -> NoReturn:
    """Land a branch whose finish bookkeeping is committed but whose merge failed.

    Only the finish commit itself -- the tip that removed this leaf's registry
    row -- is landed: a commit added after it was never reviewed or checked.
    ``--delete-branch`` on this re-run still deletes the branch once it is on
    ``remote/ib``, including when an earlier run already got it there. Either
    result then removes the main checkout's pickup files and, when this
    checkout is still on ``branch`` and the branch was not deleted, prints the
    switch guidance. This re-run has no ``--no-cleanup-work`` argument; the
    yaml cleanup flag still applies.
    """
    refuse_unless_finish_tip(repo, branch)
    local = root_land(repo) == LAND_LOCAL   # land: local fetches nothing and checks the local branch
    tracking_before = None if local else tracking_ref_snapshot(repo, remote=remote, integration_branch=ib)
    if not local:
        git_ok(["fetch", "-q", remote, ib], repo)
    target, where = (f"refs/heads/{ib}", f"local {ib}") if local else (f"refs/remotes/{remote}/{ib}", f"{ib} on {remote}")
    if git_ok(["merge-base", "--is-ancestor", branch, target], repo)[0]:
        done = "" if delete_branch else "; nothing to do"
        err_msg, outcome = "", f"{branch} is already merged into {where}{done}"
    else:
        ok, err_msg, outcome = land_on_integration(
            repo, remote=remote, ib=ib, branch=branch, land_check_cmd=land_check_cmd,
            tracking_before=tracking_before,
        )
        if not ok:
            merge_landing_failed(
                ib, err_msg, delete_branch=delete_branch, land_check_cmd=land_check_cmd,
                repo=repo,
            )
    if err_msg:
        print(err_msg, file=sys.stderr)
    report_landed(repo, outcome, branch=branch, ib=ib, remote=remote,
                  delete_branch=delete_branch, local_only=local)
    from specy_road.feature_rm_registry import finish_already_done_on_branch
    done_node = finish_already_done_on_branch(repo, branch)
    close_merged_checkout(
        repo, node_id=done_node["id"], branch=branch, ib=ib, on_mode="merge",
        delete_branch=delete_branch, no_cleanup_work=False,
    )
    raise SystemExit(0)


def _land_reporting_errors(
    repo: Path, *, on_mode: str, remote: str, ib: str, branch: str, land_check_cmd: str | None,
) -> tuple[bool, str, str]:
    """:func:`land_on_integration`; in merge mode an exception becomes a failure to undo and report."""
    try:
        return land_on_integration(repo, remote=remote, ib=ib, branch=branch, land_check_cmd=land_check_cmd)
    except Exception as e:  # noqa: BLE001 -- merge mode must still undo its bookkeeping and report
        if on_mode != "merge":
            raise
        return False, f"{type(e).__name__}: {e}", ""


def apply_on_complete_mode(
    repo: Path,
    args: argparse.Namespace,
    *,
    on_mode: str,
    branch: str,
    sess_path: Path,
    ib: str,
    gw_remote: str,
    mr_manual: bool,
    node_id: str,
    node: dict,
    pr_body_path: Path | None = None,
    undo: BookkeepingSnapshot | None = None,
) -> None:
    """PR tail, or merge/auto land integration (exit 1 on merge failure).

    ``undo``: the state before this run's bookkeeping commit, put back when a merge landing fails.
    """
    if on_mode == "pr":
        print_finish_tail(
            args,
            node_id=node_id,
            node=node,
            branch=branch,
            integration_branch=ib,
            mr_manual=mr_manual,
            pr_body_path=pr_body_path,
        )
        print_pr_gated_state(
            node_id=node_id, branch=branch, integration_branch=ib
        )
        remove_on_complete_session(sess_path)
        return

    ok, err_msg, done_msg = _land_reporting_errors(
        repo, on_mode=on_mode, remote=gw_remote, ib=ib, branch=branch,
        land_check_cmd=args.land_check_cmd,
    )
    if ok:
        if err_msg:
            print(err_msg, file=sys.stderr)
        report_landed(repo, done_msg, branch=branch, ib=ib, remote=gw_remote, sess_path=sess_path,
                      delete_branch=args.delete_branch, local_only=root_land(repo) == LAND_LOCAL)
        return

    if on_mode == "merge":
        # F-012: --on-complete merge means MERGE. Do NOT print PR
        # instructions as a fallback — that's exactly the bug being fixed.
        merge_landing_failed(
            ib, err_msg, delete_branch=args.delete_branch,
            land_check_cmd=args.land_check_cmd, repo=repo,
            undo=None if undo is None else undo_bookkeeping(repo, undo),
        )

    print(landing_error_line(ib, err_msg), file=sys.stderr)   # M15.40: after the check output
    # on_mode == "auto": fall back to PR tail only here.
    print(
        "\n(auto) Merge to integration failed — use PR/MR or fix locally "
        "(merge pending).",
        file=sys.stderr,
    )
    print_finish_tail(
        args,
        node_id=node_id,
        node=node,
        branch=branch,
        integration_branch=ib,
        mr_manual=mr_manual,
        heading_merge_pending=True,
        pr_body_path=pr_body_path,
    )
    raise SystemExit(1)
