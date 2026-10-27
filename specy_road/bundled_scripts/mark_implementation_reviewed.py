#!/usr/bin/env python3
"""Close the implementation review gate for the current feature branch.

The gate passes only on review records under ``work/reviews/<NODE_ID>/`` that
satisfy ``roadmap/orchestration.yaml`` at the commit under review (see
``review_gate``). Under the default policy — one reviewer, ``human`` rostered —
an interactive approval files ``REVIEW-human.md`` and closes the gate in one
step. ``--yes`` never creates a review: it only commits an approval the
recorded reviews already earned, so an unattended coordinator cannot approve
its own work. The approving reviews are written as ``Reviewed-by`` trailers on
the registry commit.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

from specy_road.review_gate import (
    GateResult,
    commit_trailers,
    evaluate_gate,
    human_approval_completes,
    review_required,
    write_human_approval,
)
from specy_road.review_target import resolve_target_or_exit
from specy_road.feature_rm_registry import resolve_feature_rm_registry_context
from specy_road.registry_yaml import registry_path, write_registry
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.bundled_scripts.work_dir_stash import (
    restore_work_dir_changes as _restore_work,
    stash_work_dir_changes as _stash_work,
)
from specy_road.bundled_scripts.repo_ops import current_branch, git_run, working_tree_clean

#: Rebound by :func:`main` before any helper runs; this is only a placeholder
#: so the name exists at import. Resolving the real root here would make
#: importing the module shell out to git.
ROOT = Path.cwd()


def _save_registry(doc: dict) -> None:
    write_registry(registry_path(ROOT), doc)


def _stash_work_dir_changes() -> bool:
    return _stash_work(ROOT, "mark-implementation-reviewed")


def _restore_work_dir_changes(stashed: bool) -> None:
    _restore_work(ROOT, stashed)


def _summary_path(node_id: str) -> Path:
    return ROOT / "work" / f"implementation-summary-{node_id}.md"


def _extract_walkthrough(text: str) -> str | None:
    """Return body under a Markdown 'Walkthrough' heading, if present."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^#{1,2}\s+walkthrough\s*$", stripped, re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        return None
    out: list[str] = []
    for line in lines[start:]:
        if re.match(r"^#{1,2}\s+\S", line) and not re.match(
            r"^#{1,2}\s+walkthrough\s*$", line.strip(), re.IGNORECASE
        ):
            break
        out.append(line)
    body = "\n".join(out).strip()
    return body or None


_APPROVE_RECORDED = "[a] Approve — commit the approval the recorded reviews earned"
_APPROVE_AS_HUMAN = "[a] Approve as human — file REVIEW-human.md and close the gate"


def _run_interactive_menu(
    *,
    summary_text: str,
    walkthrough: str | None,
    approve_label: str = _APPROVE_RECORDED,
) -> bool:
    """Return True if user approves."""
    print()
    print("-" * 60)
    print("[w] Show Walkthrough section only")
    print(approve_label)
    print("[q] Quit without approving")
    print("-" * 60)
    while True:
        try:
            ch = input("Choice [w/a/q]: ").strip().lower()
        except EOFError:
            print("", file=sys.stderr)
            return False
        if ch == "q":
            return False
        if ch == "a":
            return True
        if ch == "w":
            if walkthrough:
                print()
                print(walkthrough)
                print()
            else:
                print(
                    "(No ## Walkthrough section in the summary file.)",
                    file=sys.stderr,
                )
            continue
        print("  Enter w, a, or q.", file=sys.stderr)


def _load_summary_text(
    args: argparse.Namespace,
    spath: Path,
) -> str:
    if spath.is_file():
        return spath.read_text(encoding="utf-8")
    if args.allow_missing_summary:
        print(
            f"warning: missing {spath.relative_to(ROOT)} — proceeding due to "
            "--allow-missing-summary.",
            file=sys.stderr,
        )
        return ""
    print(
        f"error: implementation summary not found: {spath}",
        file=sys.stderr,
    )
    print(
        "  Create this file (see docs/dev-workflow.md) or use "
        "--allow-missing-summary for emergencies.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _user_approves(
    args: argparse.Namespace,
    *,
    summary_text: str,
    walkthrough: str | None,
    approve_label: str = _APPROVE_RECORDED,
) -> bool:
    if sys.stdin.isatty() and not args.yes:
        return _run_interactive_menu(
            summary_text=summary_text,
            walkthrough=walkthrough,
            approve_label=approve_label,
        )
    if args.yes:
        return True
    print(
        "error: not a TTY — pass --yes to approve without the interactive menu.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _commit_registry_approved(codename: str, reg: dict, trailers: list[str]) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    for e in reg.get("entries", []):
        if e.get("codename") == codename:
            e["implementation_review"] = "approved"
            e["implementation_review_at"] = now
            break
    _save_registry(reg)
    print(f"[ok] registry: implementation_review -> approved ({now})\n")

    git_run(ROOT, "add", str(registry_path(ROOT).relative_to(ROOT)))
    message = f"chore(rm-{codename}): mark implementation reviewed"
    if trailers:
        message += "\n\n" + "\n".join(trailers)
    git_run(ROOT, "commit", "-m", message)
    print("[ok] committed registry update")
    print()
    print("Next: specy-road finish-this-task")


def _print_gate(gate: GateResult) -> None:
    print(f"Review policy: {gate.summary()} (commit {gate.commit})")
    for a in gate.approvals + gate.blocks:
        print(f"  {a.review.path.name}: {a.verdict} by {a.model} ({a.family})")
    for problem in gate.problems() if not gate.passed else []:
        print(f"  - {problem}")
    print()


def _gate_or_human_approval(
    args: argparse.Namespace,
    node: dict,
    *,
    summary_text: str,
    walkthrough: str | None,
) -> GateResult:
    """The passing gate, after an interactive human approval if one completes it.

    Exits 0 when the human declines, and 1 when the recorded reviews fall short
    and a human approval here could not (or may not) make up the difference.
    """
    gate = evaluate_gate(ROOT, node, resolve_target_or_exit(ROOT, node["id"], "HEAD").commit)
    _print_gate(gate)
    if gate.passed:
        if not _user_approves(args, summary_text=summary_text, walkthrough=walkthrough):
            print("Aborted (registry unchanged).")
            raise SystemExit(0)
        return gate
    interactive = sys.stdin.isatty() and not args.yes
    sign_key = Path(args.sign_key) if args.sign_key else None
    if interactive and human_approval_completes(ROOT, gate, sign_key):
        if not _user_approves(args, summary_text=summary_text, walkthrough=walkthrough,
                              approve_label=_APPROVE_AS_HUMAN):
            print("Aborted (registry unchanged).")
            raise SystemExit(0)
        written = write_human_approval(ROOT, node, gate.commit, sign_key)
        # From a linked worktree the review lands in the main worktree.
        print(f"[ok] wrote {written.relative_to(ROOT) if written.is_relative_to(ROOT) else written}")
        gate = evaluate_gate(ROOT, node, gate.commit)
        if gate.passed:
            return gate
    print(
        "error: the review gate is not met, so the implementation cannot be marked reviewed.\n"
        f"  Inspect: specy-road handoff status {node['id']}\n"
        f"  Reviewers read: specy-road review-packet {node['id']}\n"
        f"  Record each review: specy-road review record {node['id']} --model <id> "
        "--verdict approve|block --file <notes.md>",
        file=sys.stderr,
    )
    if args.yes:
        print("  --yes only commits an approval the recorded reviews already earned.", file=sys.stderr)
    if gate.config.get("policy", {}).get("signed_reviews"):
        print("  signed_reviews is on: a human approval needs --sign-key <your private key> and a "
              "public_key on the roster's human entry.", file=sys.stderr)
    raise SystemExit(1)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Close the implementation review gate: require review records under "
            "work/reviews/<NODE_ID>/ that satisfy roadmap/orchestration.yaml at the "
            "commit under review, then record approval in roadmap/registry.yaml."
        ),
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Never prompt: commit the approval only when recorded reviews already "
            "satisfy roadmap/orchestration.yaml. Does not create a review."
        ),
    )
    p.add_argument(
        "--sign-key",
        metavar="PATH",
        help="Sign the interactive human approval with this OpenSSH private key (policy.signed_reviews).",
    )
    p.add_argument(
        "--allow-missing-summary",
        action="store_true",
        help="Allow approving when the implementation summary file is missing (loud warning).",
    )
    add_repo_root_arg(p)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global ROOT
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = resolve_repo_root(args)

    if not review_required(ROOT):
        print(
            "require_implementation_review_before_finish is not enabled in "
            "roadmap/git-workflow.yaml — nothing to do.",
            file=sys.stderr,
        )
        print(
            "When disabled, use specy-road finish-this-task directly after implementation.",
        )
        raise SystemExit(0)

    branch = current_branch(ROOT)
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    codename, reg, entry, nodes = resolve_feature_rm_registry_context(ROOT, branch)
    node_id = entry["node_id"]
    node = next(n for n in nodes if n["id"] == node_id)

    spath = _summary_path(node_id)
    summary_text = _load_summary_text(args, spath)

    print(f"Implementation review — [{node_id}]")
    print(f"Summary file: {spath.relative_to(ROOT)}\n")
    if summary_text:
        print(summary_text)
        print()

    walkthrough = _extract_walkthrough(summary_text) if summary_text else None
    gate = _gate_or_human_approval(args, node, summary_text=summary_text, walkthrough=walkthrough)

    # F-011: stash any work/ changes so the registry commit is clean,
    # then restore on top of the feature branch (where they belong).
    stashed = _stash_work_dir_changes()
    try:
        if not working_tree_clean(ROOT):
            print(
                "error: working tree is not clean (commit, stash, or "
                "discard changes outside work/ first).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        _commit_registry_approved(codename, reg, commit_trailers(gate))
    finally:
        _restore_work_dir_changes(stashed)


if __name__ == "__main__":
    main()
