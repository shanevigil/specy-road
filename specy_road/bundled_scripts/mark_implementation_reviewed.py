#!/usr/bin/env python3
"""Close the implementation review gate for the current feature branch.

The gate passes only on review records under ``work/reviews/<NODE_ID>/`` that
satisfy ``roadmap/orchestration.yaml`` at the commit under review (see
``review_gate``). Under the default policy — one reviewer, ``human`` rostered —
an interactive approval files ``REVIEW-human.md`` and closes the gate in one
step. ``--yes`` never creates a review: it only commits an approval the
recorded reviews already earned, so an unattended coordinator cannot approve
its own work. The approving reviews are written as ``Reviewed-by`` trailers on
the registry commit, followed by the leaf's ``Review-tally`` (``review_tally``).

When counted reviewer blocks are why a leaf's gate is not met, a person at a terminal (no ``--yes``) may
approve over them: after every refusal check, it records an operator decision (``review_override``) in one
commit on the integration branch, made in a temporary worktree and pushed (or the local branch moved), then
writes the marker and commits the registry approval (M22.67).

With a milestone id it closes that milestone's full review instead: the same gate
at the integration tip, then the milestone and the stale ancestors above it are
set Complete in one roadmap commit (``policy.milestone_full_review``).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from specy_road.cli import run as run_command
from specy_road.cli_entry import run_reporting
from specy_road.clock import utc_now_iso
from specy_road.decisions import DECISIONS_REL
from specy_road.git_subprocess import git_code, git_run, git_text
from specy_road.nested_repos_land import checked_out_in, in_temp_worktree, move_ref
from specy_road.review_gate import (
    SigningError,
    GateResult,
    commit_trailers,
    evaluate_gate,
    human_approval_completes,
    review_required,
    trial_merge_or_exit,
    write_human_approval,
)
from specy_road.review_override import (APPROVE, append_decision, as_if_decided, blocks_to_settle, finding_texts,
                                        recorder, role_refusal, write_operator_marker)
from specy_road.review_policy_ref import policy_source
from specy_road.review_tally import tally_trailers
from specy_road.review_target import is_milestone, milestone_close_problem, resolve_target_or_exit
from specy_road import safe_write
from specy_road.review_files import project_of, reviews_dir
from specy_road.review_lock import ReviewRunBusy, filing_busy
from specy_road.feature_rm_registry import resolve_feature_rm_registry_context
from specy_road.finish_ancestor_rollup import complete_reviewed_milestone
from specy_road.generated_files import GENERATED_COMMITTED, unstageable_generated_files
from specy_road.registry_yaml import registry_path, write_registry
from specy_road.runtime_paths import add_repo_root_arg, project_prefix, resolve_repo_root
from specy_road.repo_ops import assert_working_tree_clean, current_branch


def _summary_path(root: Path, node_id: str) -> Path:
    return root / "work" / f"implementation-summary-{node_id}.md"


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
    root: Path,
    args: argparse.Namespace,
    spath: Path,
) -> str:
    if spath.is_file():
        return spath.read_text(encoding="utf-8")
    if args.allow_missing_summary:
        print(
            f"warning: missing {spath.relative_to(root)} — proceeding due to "
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


def _commit_registry_approved(root: Path, codename: str, reg: dict, trailers: list[str]) -> None:
    now = utc_now_iso()
    for e in reg.get("entries", []):
        if e.get("codename") == codename:
            e["implementation_review"] = "approved"
            e["implementation_review_at"] = now
            break
    write_registry(registry_path(root), reg)
    print(f"[ok] registry: implementation_review -> approved ({now})\n")

    rel = str(registry_path(root).relative_to(root))
    git_run(root, "add", rel)
    message = f"chore(rm-{codename}): mark implementation reviewed"
    if trailers:
        message += "\n\n" + "\n".join(trailers)
    git_run(root, "commit", "-m", message, "--", rel)   # only the registry, whatever else is staged
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


def _approval_failure(node_id: str, error: BaseException) -> str:
    """Why a human-approval write was refused, for the ``error:`` line."""
    if isinstance(error, SigningError):
        return f"could not sign: {error}"
    if isinstance(error, ReviewRunBusy):
        return filing_busy(node_id)
    return str(error)


def _write_human_or_exit(root: Path, node: dict, commit: str, sign_key: Path | None) -> Path:
    """Write the human approval, or exit 1 with ``error:`` and no traceback."""
    try:
        return write_human_approval(root, node, commit, sign_key)
    except (SigningError, ReviewRunBusy, safe_write.SafeWriteError) as e:
        # a reviewer run holds the hand-off directory, or a symlink is on the path: nothing written
        print(f"error: {_approval_failure(node['id'], e)}", file=sys.stderr)
        raise SystemExit(1) from None


def _refuse_linked_handoff(root: Path, node_id: str) -> None:
    """A symlink at ``work``, ``work/reviews`` or the node directory refuses before the gate is read."""
    d = reviews_dir(root, node_id)
    try:
        safe_write.check(project_of(d), d, safe_write.DIRECTORY)
    except safe_write.SafeWriteError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


_APPROVE_OVER_BLOCK = "[a] Approve over the block — record your decision on the integration branch and close the gate"


def _integration(ref: str) -> tuple[str | None, str]:
    """``(remote or None, branch)`` of the ref the gate reads policy from."""
    if ref.startswith("refs/remotes/"):
        remote, ib = ref.removeprefix("refs/remotes/").split("/", 1)
        return remote, ib
    return None, ref.removeprefix("refs/heads/")


def _over_block_preflight(
    root: Path, node: dict, gate: GateResult, branch: str
) -> tuple[GateResult, str | None, str | None]:
    """``(the gate at the integration tip, the integration ref, why approving over the block is withheld)``.

    Every check that can refuse runs here, before the menu and before anything is written.
    """
    assert_working_tree_clean(root, except_work=True)   # a decision never sits beside an unstamped registry
    if why := role_refusal():
        return gate, None, why
    if not recorder(root):
        return gate, None, "git identity: set git user.name and user.email; the decision entry names who recorded it"
    ref, err = policy_source(root)
    if ref is None:
        return gate, None, err or "no integration branch to record the decision on"
    remote, ib = _integration(ref)
    if remote:   # the gate reads only the remote-tracking ref: read the policy at the fetched tip
        code, out = git_code(["fetch", remote, ib], root)
        if code != 0:
            return gate, ref, f"git fetch {remote} {ib} failed: {out}"
        gate = evaluate_gate(root, node, gate.commit, branch=branch)
    elif (holder := checked_out_in(root, ib)) is not None:
        status = git_text(["status", "--porcelain", "--untracked-files=no"], holder)
        if status is None or status:
            return gate, ref, (f"{ib} is checked out in {holder} with uncommitted changes (or an unreadable "
                               "status); commit or stash them there first")
    after = as_if_decided(gate)
    if not after.passed:
        return gate, ref, "settling the block(s) would not pass the gate: " + "; ".join(after.problems())
    return gate, ref, None


def _read_reason(gate: GateResult) -> str:
    """Show each blocking record's findings, offer the approval over the block and read the reason; ``""``: quit."""
    for b in gate.blocks:
        print(f"{b.model} blocks {gate.commit} ({b.review.path.name}):")
        for text in finding_texts(b.review.data.get("findings")) or ["(no findings listed)"]:
            print(f"  - {text}")
    print()
    print("-" * 60)
    print(_APPROVE_OVER_BLOCK)
    print("[q] Quit without approving")
    print("-" * 60)
    try:
        while (ch := input("Choice [a/q]: ").strip().lower()) not in ("a", "q"):
            print("  Enter a or q.", file=sys.stderr)
        return input("Why, in your own words (empty to quit): ").strip() if ch == "a" else ""
    except EOFError:
        return ""


def _record_over_block(
    root: Path, node: dict, gate: GateResult, ref: str, reason: str, branch: str
) -> GateResult:
    """Commit the operator decision on the integration branch from a temporary worktree of the tip the gate read,
    push it (or move the local branch), then write the marker here; the passing gate, or exit 1."""
    sha, (remote, ib) = str(gate.commit), _integration(ref)
    where = f"{remote}/{ib}" if remote else f"local {ib}"
    tip, prefix = git_text(["rev-parse", ref], root) or "", project_prefix(root)
    rel = f"{prefix}{DECISIONS_REL.as_posix()}"
    ns = argparse.Namespace(node_id=node["id"], decision=APPROVE, quote=reason, rule=None, limit=[],
                            session=f"mark-implementation-reviewed {utc_now_iso()}")
    blocks, who, done = blocks_to_settle(root, gate, sha), str(recorder(root)), {}

    def commit(tree: Path) -> str | None:
        try:
            entry, _settles = append_decision(tree / prefix, ns, gate, blocks, who)
        except ValueError as e:   # a copied schema from before decided_by
            return f"{e}; run `specy-road refresh-schemas`"
        git_code(["add", "--", rel], tree)
        code, out = git_code(["commit", "-q", "-m", f"roadmap: operator decision {entry['id']} approves "
                                                    f"{node['id']} over the block", "--", rel], tree)
        if code != 0:
            return f"the decision commit failed: {out}"
        done.update(entry=entry, new=git_text(["rev-parse", "HEAD"], tree) or "")
        if remote:
            code, out = git_code(["push", remote, f"HEAD:refs/heads/{ib}"], tree)
            return f"git push {remote} HEAD:refs/heads/{ib} was refused: {out}" if code != 0 else None
        return move_ref(root, f"refs/heads/{ib}", tip, done["new"], checked_out_in(root, ib), "the decision commit")

    if err := in_temp_worktree(root, tip, commit):
        print(f"error: {err}\n  Nothing was recorded. The coordinator can record the decision from the "
              f"integration-branch checkout: specy-road review operator-decision {node['id']} --decision approve "
              "--quote '<the operator's words>' --session <id>", file=sys.stderr)
        raise SystemExit(1)
    marker = write_operator_marker(root, done["entry"], sha, ns.session)
    print(f"[ok] decision {done['entry']['id']} committed on {where} as {done['new']}; wrote {marker}")
    gate = evaluate_gate(root, node, sha, branch=branch)
    if not gate.passed:
        for problem in gate.problems():
            print(f"  - {problem}", file=sys.stderr)
        print(f"error: decision {done['entry']['id']} is recorded on {where}, but the review gate is still not "
              "met; the registry was not stamped.", file=sys.stderr)
        raise SystemExit(1)
    return gate


def _approve_over_block(
    root: Path, node: dict, gate: GateResult, branch: str
) -> tuple[GateResult | None, str | None]:
    """``(the passing gate after the person approved over the block, why the approval is withheld)``.

    Exits 0 when the person quits or gives no reason, and 1 when recording fails.
    """
    gate, ref, why = _over_block_preflight(root, node, gate, branch)
    if why or ref is None:
        return None, why
    reason = _read_reason(gate)
    if not reason:
        print("Aborted (nothing recorded).")
        raise SystemExit(0)
    return _record_over_block(root, node, gate, ref, reason, branch), None


def _refuse_unmet(args: argparse.Namespace, node: dict, gate: GateResult, block_branch: str | None,
                  withheld: str | None) -> None:
    """Exit 1 naming what can still close the gate; ``block_branch``: a leaf's branch while a counted block stands."""
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
    if block_branch:
        print(f"  To approve over the block: run `specy-road mark-implementation-reviewed` on {block_branch} in an "
              "interactive terminal, without --yes; or the coordinator records the operator's decision: "
              f"specy-road review operator-decision {node['id']} --decision approve --quote "
              "'<the operator's words>' --session <id>", file=sys.stderr)
    if withheld:
        print(f"  Approval over the block withheld: {withheld}", file=sys.stderr)
    if gate.config.get("policy", {}).get("signed_reviews"):
        print("  signed_reviews is on: a human approval needs --sign-key <your private key> and a "
              "public_key on the roster's human entry.", file=sys.stderr)
    raise SystemExit(1)


def _gate_or_human_approval(
    root: Path,
    args: argparse.Namespace,
    node: dict,
    *,
    branch: str | None,
    summary_text: str,
    walkthrough: str | None,
    commit: str | None = None,
) -> GateResult:
    """The passing gate, after an interactive human approval if one completes it.

    Exits 0 when the human declines, and 1 when the recorded reviews fall short
    and a human approval here could not (or may not) make up the difference.
    ``commit`` is the commit under review when it is not ``HEAD`` (a milestone's integration tip).
    """
    _refuse_linked_handoff(root, node["id"])
    gate = evaluate_gate(
        root,
        node,
        commit or resolve_target_or_exit(root, node["id"], "HEAD").commit,
        branch=branch,
    )
    _print_gate(gate)
    if gate.passed:
        if not _user_approves(args, summary_text=summary_text, walkthrough=walkthrough):
            print("Aborted (registry unchanged).")
            raise SystemExit(0)
        return gate
    interactive = sys.stdin.isatty() and not args.yes
    sign_key = Path(args.sign_key) if args.sign_key else None
    if interactive and human_approval_completes(root, gate, node, sign_key):
        if not _user_approves(args, summary_text=summary_text, walkthrough=walkthrough,
                              approve_label=_APPROVE_AS_HUMAN):
            print("Aborted (registry unchanged).")
            raise SystemExit(0)
        written = _write_human_or_exit(root, node, gate.commit, sign_key)
        # From a linked worktree the review lands in the main worktree.
        print(f"[ok] wrote {written.relative_to(root) if written.is_relative_to(root) else written}")
        gate = evaluate_gate(root, node, gate.commit, branch=branch)
        if gate.passed:
            return gate
        for problem in gate.problems():   # say why the record just written does not count
            print(f"  - {problem}", file=sys.stderr)
    over_block, withheld = bool(gate.blocks and branch), None   # a leaf: an operator decision is for one leaf
    if over_block and interactive:
        decided, withheld = _approve_over_block(root, node, gate, branch)
        if decided is not None:
            return decided
    _refuse_unmet(args, node, gate, branch if over_block else None, withheld)


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road mark-implementation-reviewed`` parser."""
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
    p.add_argument("node_id", nargs="?", help="A milestone id: close its full review at the integration tip and set "
                   "it Complete (policy.milestone_full_review). Without it, the current feature branch's leaf.")
    add_repo_root_arg(p)
    return p


def _close_milestone(root: Path, args: argparse.Namespace, node_id: str) -> None:
    """Pass the milestone's gate at the integration tip, then commit its Complete status."""
    from specy_road.roadmap_load import compute_rollup_status, load_roadmap

    nodes = load_roadmap(root)["nodes"]
    node = next((n for n in nodes if n.get("id") == node_id), None)
    if node is None:
        print(f"error: unknown node id: {node_id}", file=sys.stderr)
        raise SystemExit(1)
    if not is_milestone(nodes, node_id):
        print(f"error: {node_id} is not a milestone (no leaf children); a leaf is marked reviewed from its "
              "feature branch, without a node id.", file=sys.stderr)
        raise SystemExit(1)
    leaf_rollup = compute_rollup_status(nodes).get(node_id)
    if leaf_rollup != "Complete":
        print(f"error: {node_id} still has unfinished leaves ({leaf_rollup}); its full review "
              "closes it only after the last one lands.", file=sys.stderr)
        raise SystemExit(1)
    target = resolve_target_or_exit(root, node_id)
    if why := milestone_close_problem(root, target):   # before a human reads, approves, or a record is written
        print(f"error: {why}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Milestone full review — [{node_id}] at {target.ref}\n")
    gate = _gate_or_human_approval(root, args, node, branch=None, summary_text="", walkthrough=None,
                                   commit=target.commit)
    assert_working_tree_clean(root, except_work=True)
    changed = complete_reviewed_milestone(root, node_id)   # the checks above make its ValueError unreachable
    if not changed:
        print(f"{node_id} is already Complete; nothing to commit.")
        return
    _refresh_generated(root)
    refused = set(unstageable_generated_files(root))
    paths = changed + [n for n in GENERATED_COMMITTED if n not in refused and (root / n).exists()]
    message = f"roadmap: {node_id} full review approved; status -> Complete"
    trailers = commit_trailers(gate)
    if trailers:
        message += "\n\n" + "\n".join(trailers)
    git_run(root, "add", *paths)
    git_run(root, "commit", "-m", message, "--", *paths)
    print(f"[ok] committed {node_id} -> Complete")


def _refresh_generated(root: Path) -> None:
    """validate, export and digest, in this process: the generated files follow the status.

    As in finish. A failing one has printed why; stop before anything is staged or committed.
    """
    for command in ("validate", "export", "digest"):
        if status := run_command([command, "--repo-root", str(root)]):
            print(f"error: specy-road {command} exited {status}; nothing was committed.",
                  file=sys.stderr)
            raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    """Close the implementation review. A command error is printed once and exits with its code."""
    run_reporting(lambda: _mark(argv))


def _mark(argv: list[str] | None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    root = resolve_repo_root(args)

    if not review_required(root):
        print(
            "require_implementation_review_before_finish is not enabled in roadmap/git-workflow.yaml, "
            "so the review gate is not enforced at finish-this-task — nothing to do.",
            file=sys.stderr,
        )
        print(
            "When disabled, use specy-road finish-this-task directly after implementation; it lands "
            "without reviews. To enforce them, set require_implementation_review_before_finish: true.",
        )
        raise SystemExit(0)

    if args.node_id:
        _close_milestone(root, args, args.node_id)
        return

    branch = current_branch(root)
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    codename, reg, entry, nodes = resolve_feature_rm_registry_context(root, branch)
    node_id = entry["node_id"]
    node = next(n for n in nodes if n["id"] == node_id)

    trial_merge_or_exit(root)   # before a human reads, approves, or a record is written
    spath = _summary_path(root, node_id)
    summary_text = _load_summary_text(root, args, spath)

    print(f"Implementation review — [{node_id}]")
    print(f"Summary file: {spath.relative_to(root)}\n")
    if summary_text and sys.stdin.isatty() and not args.yes:   # for the human about to approve
        print(summary_text)
        print()

    walkthrough = _extract_walkthrough(summary_text) if summary_text else None
    gate = _gate_or_human_approval(
        root, args, node, branch=entry.get("branch"), summary_text=summary_text,
        walkthrough=walkthrough,
    )

    # work/ changes stay where they are: the registry commit names its one path.
    assert_working_tree_clean(root, except_work=True)
    try:
        trailers = commit_trailers(gate) + tally_trailers(root, gate)
        _commit_registry_approved(root, codename, reg, trailers)
    except subprocess.CalledProcessError:
        if not gate.accepted:
            raise
        rel = registry_path(root).relative_to(root).as_posix()
        print(f"error: the operator decision is recorded ({'; '.join(gate.accepted)}), but the registry commit "
              f"failed. To finish: restore {rel} (`git restore --staged --worktree {rel}`), then re-run "
              "`specy-road mark-implementation-reviewed --yes`.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
