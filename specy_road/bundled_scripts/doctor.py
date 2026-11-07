#!/usr/bin/env python3
"""``specy-road doctor``: list what the task loop left behind; remove it with ``--fix``.

Four kinds, each its own section:

- ``feature/rm-*`` branches, local and on the remote, whose leaf is Complete on the integration
  branch (registry row or not), or that nothing claims: no registry row (in this checkout or on
  the integration branch) and not an open milestone rollup — the same "live" test ``branches
  prune`` uses. Each row says why: merged, its leaf Complete, or only that its claim is gone; an
  unmerged one also says how many commits the integration branch lacks.
- linked worktrees whose directory is missing, whose branch is gone (detached at a commit the
  integration branch contains or whose patch it has, the same test as a branch: how ``finish
  --delete-branch`` leaves a delegate worktree) or is merged, whether or not the branch itself is
  listed (a claimed branch whose leaf is not Complete stays), and every other detached worktree
  (a review recipe's). ``--fix`` leaves a detached one with uncommitted changes, with commits
  no branch holds, or in a temporary directory another command may be using (:data:`TEMP_WORKTREES`).
- registry rows on the integration branch whose branch is in neither this clone nor the remote
  (advisory: another clone's claim looks the same until its branch is pushed; ``--fix`` leaves
  the row and names ``specy-road registry-prune --remove <CODENAME>``), or whose leaf is Complete
  (``--fix`` still removes those through ``registry-prune --remove``).
- stashes the toolkit pushed (``specy-road: …``; pickup and review used to stash ``work/``, and
  a failed restore left the entry behind).

Merged is ancestry first. When ancestry fails, patch content decides: every
commit has an equivalent upstream (``git cherry``: a rebase), or the branch's
whole diff does (a squash). A rewritten landing is therefore still merged.
A branch with no commit of its own is "no commits yet", never merged; a branch an
open claim, open rollup or unfinished worker holds is "live", and ``--fix`` leaves
it and its worktree (:mod:`specy_road.doctor_worktrees`).

Nothing changes without ``--fix``, and ``--fix`` asks once per kind. A registry row with no
branch is listed and left; removing it is ``specy-road registry-prune --remove <CODENAME>``.

With no such git remote there is nothing to compare against, which is not a failure: doctor says
so in one line and lists only the stashes. A remote that is configured but cannot be fetched still
fails.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from specy_road.bundled_scripts.branches_cli import feature_branches, fetch_integration, live_branches
from specy_road.bundled_scripts.do_next_task_self_heal import detect_stale_claims
from specy_road.bundled_scripts.doctor_env_setup import report_checkout
from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.doctor_worktrees import (  # noqa: F401 — SAME_PATCH, TEMP_WORKTREES re-exported for callers
    NO_EVIDENCE, SAME_PATCH, TEMP_WORKTREES, Finding, classify, containment, evidence_kind, live_holders,
    merged_how, worktree_findings,
)
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_checked, git_code, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.nested_repos import report_unpushed
from specy_road.orchestrate_assign import guidance_bypass_lines
from specy_road.orchestration_pinned import pinned_config
from specy_road.orphaned_claims import orphaned_claims, report_lines
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.version_skew import print_install_report, warn_if_running_version_older
from specy_road.worker_adapter_cursor import force_warnings

TOOLKIT_STASH = re.compile(r"^On [^:]+: specy-road: ")


@dataclass
class _Ctx:
    root: Path
    target: str
    remote: str
    base: str
    live: set[str]
    complete: dict[str, str]   # codename -> node id of a Complete leaf
    held: dict[str, tuple[str, str]]        # branch -> (live source, "live: …"): doctor_worktrees.live_holders
    held_paths: dict[str, tuple[str, str]]  # resolved worktree path -> (live source, "live: …")


def _complete_leaves(nodes: list[dict]) -> dict[str, str]:
    parents = {n.get("parent_id") for n in nodes}
    return {n["codename"]: n["id"] for n in nodes if n.get("codename") and n.get("id") not in parents
            and (n.get("status") or "").lower() == "complete"}


def _branch_reason(ctx: _Ctx, ref: str, branch: str, node_id: str | None, kind: str
                   ) -> tuple[str, str, bool, tuple[str, str]]:
    """(reason, label, fix offered, (evidence, containment)): the verdict is :func:`classify`'s."""
    row = "; registry row remains" if branch in ctx.live else ""
    why = f"leaf {node_id} Complete" if node_id else "claim gone"
    leaf = f"; leaf {node_id} Complete" if row else ""
    how = merged_how(ctx.root, ref, ctx.target)
    inputs = (evidence_kind(ctx.root, ref, ctx.target), containment(how))
    source, live_why = ctx.held.get(branch, ("none", ""))
    label, fix = classify(source, *inputs, kind)
    if label == "not merged":
        ahead = git_checked(["rev-list", "--count", f"{ctx.target}..{ref}"], ctx.root)
        return f"{why}, not merged: {ahead} commit(s) {ctx.target} lacks{row}", label, fix, inputs
    reason = {"live": live_why, "no commits yet": f"{why}, no commits yet{row}",
              "merged, no evidence": f"merged{leaf}{row}; {NO_EVIDENCE}"}.get(label, f"{how}{leaf}{row}")
    return reason, label, fix, inputs


def _delete_local(root: Path, branch: str, sha: str | None) -> str | None:
    if git_text(["rev-parse", f"refs/heads/{branch}"], root) != sha:
        return "moved since it was listed; left alone"
    code, out = git_code(["branch", "-D", branch], root)
    return out if code else None


def _delete_remote(root: Path, branch: str, sha: str | None, remote: str) -> str | None:
    # Leased to the tip that was listed: a push since then is refused.
    code, out = git_code(["push", remote, f"--force-with-lease=refs/heads/{branch}:{sha}", "--delete", branch], root)
    return f"left on {remote}. {out}" if code else None


def _branch_findings(ctx: _Ctx) -> tuple[list[Finding], dict[str, tuple[str, str]]]:
    """Complete or unclaimed branches, and the classification inputs of every local ``feature/rm-*``.

    Those inputs feed the worktree section, which judges a worktree on a branch even when the
    branch itself is not listed. A claimed branch is in-progress work and is not listed; any other
    verdict without a fix (live worker or session, no commits yet, merged with no evidence) is
    listed with ``so --fix leaves it``.
    """
    found: list[Finding] = []
    local: dict[str, tuple[str, str]] = {}
    for prefix, where in (("refs/heads/", "local"), (f"refs/remotes/{ctx.remote}/", ctx.remote)):
        for b in feature_branches(ctx.root, prefix):
            node_id = ctx.complete.get(b.removeprefix("feature/rm-"))
            reason, label, fix, inputs = _branch_reason(ctx, prefix + b, b, node_id,
                                                        "local" if where == "local" else "remote")
            if where == "local":
                local[b] = inputs
            if ctx.held.get(b, ("none",))[0] == "claim":
                continue
            if not fix:
                found.append(Finding("branch", f"{where:<9} {b}", f"{reason}, so --fix leaves it", None, ""))
                continue
            sha = git_text(["rev-parse", prefix + b], ctx.root)
            if where == "local":
                remove, done = partial(_delete_local, ctx.root, b, sha), f"deleted local branch {b}"
            else:
                remove, done = partial(_delete_remote, ctx.root, b, sha, ctx.remote), f"deleted {b} on {ctx.remote}"
            found.append(Finding("branch", f"{where:<9} {b}", reason, remove, done))
    return found, local


def _prune_row(ctx: _Ctx, codename: str) -> str | None:
    """``registry-prune --remove``: it syncs, commits on the integration branch and pushes."""
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.bundled_scripts.registry_prune",
         "--remove", codename, "--base", ctx.base, "--remote", ctx.remote,
         "--repo-root", str(ctx.root)],
        capture_output=True, text=True, check=False,
    )
    return (r.stderr or r.stdout).strip() if r.returncode else None


def _registry_findings(ctx: _Ctx) -> list[Finding]:
    """Complete leaves are still removed. A row with no branch is advisory: another clone's claim
    looks the same, so ``--fix`` leaves it and names ``registry-prune --remove``.
    """
    reg = read_registry_at_ref(ctx.root, ctx.target, DEFAULT_TIMEOUT) or {}
    stale = {e["codename"] for e in detect_stale_claims(repo_root=ctx.root, reg=reg, remote=ctx.remote)}
    found = []
    for e in reg.get("entries") or []:
        codename = e["codename"]
        if codename in ctx.complete:
            why = f"leaf Complete; {e['branch']} is listed above"
            remove = partial(_prune_row, ctx, codename)
            done = f"removed registry row {codename} on {ctx.target}"
        elif codename in stale:
            why = (
                f"{e['branch']} is in neither this clone nor {ctx.remote} "
                "(advisory: another clone's claim looks the same until it pushes its branch; "
                "confirm that clone no longer holds the claim, then "
                f"specy-road registry-prune --remove {codename}), so --fix leaves it"
            )
            remove, done = None, ""
        else:
            continue
        found.append(Finding("registry", codename, f"node {e['node_id']}: {why}", remove, done))
    return found


def _drop_stash(root: Path, sha: str) -> str | None:
    # The stack is shared with every session here: find the entry again by sha.
    shas = (git_text(["stash", "list", "--format=%H"], root) or "").splitlines()
    if sha not in shas:
        return "no longer on the stash stack"
    code, out = git_code(["stash", "drop", f"stash@{{{shas.index(sha)}}}"], root)
    return out if code else None


def _stash_findings(root: Path) -> list[Finding]:
    out = git_text(["stash", "list", "--format=%H%x09%gs"], root) or ""
    found = []
    for line in out.splitlines():
        sha, _, subject = line.partition("\t")
        if TOOLKIT_STASH.match(subject):
            found.append(Finding(
                "stash", sha[:12], subject, partial(_drop_stash, root, sha),
                f"dropped stash {sha[:12]} (git stash apply {sha} restores it until git gc)",
            ))
    return found


def _stash_section(root: Path) -> tuple[str, str, list[Finding]]:
    return ("stash", "Stashes specy-road left behind (git stash show -p --include-untracked <sha>):",
            _stash_findings(root))


def _sections(ctx: _Ctx) -> list[tuple[str, str, list[Finding]]]:
    """(kind, heading, findings) in report order."""
    branches, merged_local = _branch_findings(ctx)
    return [
        ("branch", f"feature/rm-* branches whose leaf is Complete or that nothing claims (against {ctx.target}):", branches),
        ("worktree", "Worktrees whose branch is gone or merged, and detached worktrees:",
         worktree_findings(ctx, merged_local)),
        ("registry", (f"Registry rows on {ctx.target} with no branch (advisory: another clone's "
                      "claim looks the same until it pushes its branch; --fix leaves them — "
                      "specy-road registry-prune --remove <CODENAME>) or whose leaf is Complete:"),
         _registry_findings(ctx)),
        _stash_section(ctx.root),
    ]


# Worktrees before branches (a checked-out branch cannot be deleted); registry
# rows last, because registry-prune checks out the integration branch.
FIX_ORDER = ("worktree", "branch", "stash", "registry")


def _confirm(kind: str, n: int) -> bool | None:
    """True/False for the answer, ``None`` when stdin has none to give."""
    try:
        answer = input(f"Remove the {n} listed {kind} item(s)? [y/N] ")
    except EOFError:
        return None
    return answer.strip().lower() in ("y", "yes")


def _fix(sections: list[tuple[str, str, list[Finding]]], yes: bool) -> int:
    by_kind = {kind: found for kind, _h, found in sections if found}
    failures = 0
    for kind in FIX_ORDER:
        for f in by_kind.get(kind) or []:
            if f.remove is None:
                print(f"[kept] {' '.join(f.name.split())}: {f.reason}")
        found = [f for f in by_kind.get(kind) or [] if f.remove]
        if not found:
            continue
        ok = True if yes else _confirm(kind, len(found))
        if ok is None:
            print("\nNo answer on stdin; pass --yes to remove without asking. Stopped.", file=sys.stderr)
            return 1
        if not ok:
            print(f"Skipped the {kind} item(s).")
            continue
        for f in found:
            failure = f.remove()
            if failure is None:
                print(f"[ok] {f.done}")
            else:
                print(f"[warn] {' '.join(f.name.split())}: {failure}", file=sys.stderr)
                failures += 1
    return 1 if failures else 0


def _no_remote_sections(root: Path, ns: argparse.Namespace) -> list[tuple[str, str, list[Finding]]] | None:
    """Only the stash section when the remote :func:`fetch_integration` would fetch is not configured, else ``None``."""
    _base, remote, warns = resolve_integration_defaults(root, explicit_base=ns.base, explicit_remote=ns.remote)
    if git_code(["remote", "get-url", remote], root)[0] == 0 or git_code(["rev-parse", "--git-dir"], root)[0]:
        return None   # configured, or not a repository: fetch_integration resolves it again and reports either
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    print(f"doctor: no git remote named {remote!r} is configured; "
          "skipped fetch and the branch, worktree and registry checks that compare against it.")
    return [_stash_section(root)]


def _context(ns: argparse.Namespace) -> _Ctx | None:
    root = resolve_repo_root(ns)
    fetched = fetch_integration(root, ns)
    if fetched is None:
        return None
    base, remote = fetched
    target = f"{remote}/{base}"
    nodes = load_roadmap_nodes_at_ref(root, target)
    live = live_branches(root, target)
    if nodes is None or live is None:
        print(f"error: could not read the roadmap at {target}. Not listing anything.", file=sys.stderr)
        return None
    complete = _complete_leaves(nodes)
    return _Ctx(root, target, remote, base, live, complete, *live_holders(root, target, nodes, complete))


def _print_orphaned_claims(root: Path) -> None:
    """Report-only: ``--fix`` does not release these (they are not in :data:`FIX_ORDER`)."""
    lines = report_lines(orphaned_claims(root))
    if not lines:
        return
    print("Claims with no live worker (report only; --fix does not release them):")
    for line in lines:
        print(f"  {line}")


def _print_cursor_force(root: Path) -> None:
    """Advisory: one line per roster ``cursor`` entry that launches with ``--force`` (the roster launches read).
    An unreadable roster is left to ``validate`` and ``orchestrate plan``."""
    config, err = pinned_config(root)
    # M21.44: then each excluded or opted-in guidance-bypass model
    for line in ([] if err else force_warnings(config.get("roster") or [])) + guidance_bypass_lines(root):
        print(line, file=sys.stderr)


def cmd_doctor(ns: argparse.Namespace) -> int:
    print_install_report()
    root = resolve_repo_root(ns)
    warn_if_running_version_older(root)
    bad_config = report_checkout(root)   # gate mismatch, env_setup failure: exit 1 after the listing
    report_unpushed(root)   # advisory: nested-repo commits no remote has
    _print_cursor_force(root)   # advisory: cursor workers that run without the sandbox
    sections = _no_remote_sections(root, ns)
    clean = "Nothing to tidy: no toolkit stash."
    if sections is None:
        ctx = _context(ns)
        if ctx is None:
            return 1
        sections = _sections(ctx)
        clean = "Nothing to tidy: no stale branch, worktree, registry row or toolkit stash."
    if not any(found for _k, _h, found in sections):
        print(clean)
    else:
        for _kind, heading, found in sections:
            if found:
                print(heading)
                for f in found:
                    print(f"  {f.name}  — {f.reason}")
        if not ns.fix:
            print("Nothing removed. Re-run with --fix to remove them (it asks per kind).")
        else:
            bad_config = _fix(sections, ns.yes) or bad_config
    _print_orphaned_claims(root)   # after the branch section, so it is not read as one of those rows
    return int(bad_config)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road doctor",
        description=(
            "After git fetch --prune, list feature/rm-* branches (local and remote) whose leaf is "
            "Complete or that nothing claims — merged by ancestry or patch content, leaf Complete, or claim gone — worktrees whose branch is gone or merged, other detached worktrees, registry rows with no branch (listed; --fix leaves them for registry-prune --remove) or a Complete leaf, and stashes specy-road pushed; also nested-repo branches with commits no remote has. Dry-run unless --fix."
        ),
    )
    p.add_argument(
        "--fix", action="store_true",
        help="Remove what is listed, asking once per kind, and report each action. "
             "Leaves a registry row whose branch is in neither this clone nor the remote.",
    )
    p.add_argument("--yes", action="store_true", help="With --fix, do not ask.")
    p.add_argument("--base", default=None, metavar="BRANCH",
                   help="Integration branch (default: roadmap/git-workflow.yaml, else main).")
    p.add_argument("--remote", default=None, metavar="NAME",
                   help="Git remote (default: roadmap/git-workflow.yaml, else origin).")
    add_repo_root_arg(p)
    return p


def main(argv: list[str] | None = None) -> None:
    ns = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    raise SystemExit(cmd_doctor(ns))


if __name__ == "__main__":
    main()
