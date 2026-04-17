"""PR/MR tail and merge-to-integration after finish-this-task bookkeeping."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.on_complete_session import remove_on_complete_session


def print_finish_tail(
    args: argparse.Namespace,
    *,
    node_id: str,
    node: dict,
    branch: str,
    integration_branch: str,
    mr_manual: bool,
    heading_merge_pending: bool = False,
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
    print(
        f'  gh pr create --base {integration_branch} --head {branch} '
        f'--title "{title}"'
    )
    print(
        "  (GitLab: `glab mr create` or web UI — same idea as a GitHub PR.)",
    )
    if mr_manual:
        print(
            "  Merge requests require manual approval — wait for review, "
            "then merge.",
        )
    print("-" * 60)


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
) -> None:
    """PR tail, or merge/auto land integration (exit 1 on merge failure)."""
    if on_mode == "pr":
        print_finish_tail(
            args,
            node_id=node_id,
            node=node,
            branch=branch,
            integration_branch=ib,
            mr_manual=mr_manual,
        )
        remove_on_complete_session(sess_path)
        return

    ok, err_msg = land_merge_feature_into_integration(
        repo,
        remote=gw_remote,
        integration_branch=ib,
        feature_branch=branch,
    )
    if ok:
        print(f"\n[ok] merged {branch} into {ib} and pushed to {gw_remote}")
        remove_on_complete_session(sess_path)
        return

    print(
        f"\nerror: could not land merge to {ib}: {err_msg}",
        file=sys.stderr,
    )
    if on_mode == "merge":
        # F-012: --on-complete merge means MERGE. Do NOT print PR
        # instructions as a fallback — that's exactly the bug being fixed.
        # Exit hard so the user investigates the integration-branch issue.
        print(
            "\n--on-complete merge cannot fall back to PR instructions. "
            "Fix the integration branch (see error above) and re-run, or "
            "rerun finish-this-task with --on-complete pr if you intend to "
            "open a PR instead.",
            file=sys.stderr,
        )
        raise SystemExit(1)

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
    )
    raise SystemExit(1)
