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
  (advisory, as in ``registry-prune``: another clone's claim looks the same until its branch is
  pushed), or whose leaf is Complete.
- stashes the toolkit pushed (``specy-road: …``; pickup and review used to stash ``work/``, and
  a failed restore left the entry behind).

Merged is ancestry first. When ancestry fails, patch content decides: every
commit has an equivalent upstream (``git cherry``: a rebase), or the branch's
whole diff does (a squash). A rewritten landing is therefore still merged.
A branch with no commit of its own is "no commits yet", never merged; a branch an
open claim, open rollup or unfinished worker holds is "live", and ``--fix`` leaves
it and its worktree (:mod:`specy_road.doctor_worktrees`).

Nothing changes without ``--fix``, and ``--fix`` asks once per kind.
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
    SAME_PATCH, TEMP_WORKTREES, Finding, has_own_commits, live_holders, merged_how, worktree_findings,
)
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_checked, git_code, git_text
from specy_road.nested_repos import report_unpushed
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.version_skew import print_install_report, warn_if_running_version_older

TOOLKIT_STASH = re.compile(r"^On [^:]+: specy-road: ")


@dataclass
class _Ctx:
    root: Path
    target: str
    remote: str
    base: str
    live: set[str]
    complete: dict[str, str]   # codename -> node id of a Complete leaf
    held: dict[str, str]       # branch -> "live: …": never offered for removal (doctor_worktrees.live_holders)


def _complete_leaves(nodes: list[dict]) -> dict[str, str]:
    parents = {n.get("parent_id") for n in nodes}
    return {n["codename"]: n["id"] for n in nodes if n.get("codename") and n.get("id") not in parents
            and (n.get("status") or "").lower() == "complete"}


def _branch_reason(ctx: _Ctx, ref: str, branch: str, node_id: str | None) -> tuple[str, bool | None]:
    """The reason, and ``None`` when not merged, else whether the branch has a commit of its own."""
    row = "; registry row remains" if branch in ctx.live else ""
    why = f"leaf {node_id} Complete" if node_id else "claim gone"
    how = merged_how(ctx.root, ref, ctx.target)
    if how and not has_own_commits(ctx.root, ref, ctx.target):
        return f"{why}, no commits yet{row}", False   # its tip is a commit target already had
    if how:
        leaf = f"; leaf {node_id} Complete" if row else ""
        return f"{how}{leaf}{row}", True
    ahead = git_checked(["rev-list", "--count", f"{ctx.target}..{ref}"], ctx.root)
    return f"{why}, not merged: {ahead} commit(s) {ctx.target} lacks{row}", None


def _delete_local(root: Path, branch: str, sha: str | None) -> str | None:
    if git_text(["rev-parse", f"refs/heads/{branch}"], root) != sha:
        return "moved since it was listed; left alone"
    code, out = git_code(["branch", "-D", branch], root)
    return out if code else None


def _delete_remote(root: Path, branch: str, sha: str | None, remote: str) -> str | None:
    # Leased to the tip that was listed: a push since then is refused.
    code, out = git_code(["push", remote, f"--force-with-lease=refs/heads/{branch}:{sha}", "--delete", branch], root)
    return f"left on {remote}. {out}" if code else None


def _branch_findings(ctx: _Ctx) -> tuple[list[Finding], dict[str, bool]]:
    """Complete or unclaimed branches, and every local ``feature/rm-*`` that is merged.

    The merged map (branch -> has a commit of its own) feeds the worktree section,
    which judges a worktree on a merged branch even when the branch itself is not listed.
    A live branch (:attr:`_Ctx.held`) or one with no commits yet is listed without a fix.
    """
    found: list[Finding] = []
    merged_local: dict[str, bool] = {}
    for prefix, where in (("refs/heads/", "local"), (f"refs/remotes/{ctx.remote}/", ctx.remote)):
        for b in feature_branches(ctx.root, prefix):
            node_id = ctx.complete.get(b.removeprefix("feature/rm-"))
            reason, own = _branch_reason(ctx, prefix + b, b, node_id)
            if where == "local" and own is not None:
                merged_local[b] = own
            if b in ctx.live and not node_id:
                continue
            if b in ctx.held or own is False:
                found.append(Finding("branch", f"{where:<9} {b}", f"{ctx.held.get(b, reason)}, so --fix leaves it", None, ""))
                continue
            sha = git_text(["rev-parse", prefix + b], ctx.root)
            if where == "local":
                remove, done = partial(_delete_local, ctx.root, b, sha), f"deleted local branch {b}"
            else:
                remove, done = partial(_delete_remote, ctx.root, b, sha, ctx.remote), f"deleted {b} on {ctx.remote}"
            found.append(Finding("branch", f"{where:<9} {b}", reason, remove, done))
    return found, merged_local


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
    reg = read_registry_at_ref(ctx.root, ctx.target, DEFAULT_TIMEOUT) or {}
    stale = {e["codename"] for e in detect_stale_claims(repo_root=ctx.root, reg=reg, remote=ctx.remote)}
    found = []
    for e in reg.get("entries") or []:
        if e["codename"] in stale:
            why = f"{e['branch']} is in neither this clone nor {ctx.remote}"
        elif e["codename"] in ctx.complete:
            why = f"leaf Complete; {e['branch']} is listed above"
        else:
            continue
        found.append(Finding(
            "registry", e["codename"], f"node {e['node_id']}: {why}",
            partial(_prune_row, ctx, e["codename"]),
            f"removed registry row {e['codename']} on {ctx.target}",
        ))
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


def _sections(ctx: _Ctx) -> list[tuple[str, str, list[Finding]]]:
    """(kind, heading, findings) in report order."""
    branches, merged_local = _branch_findings(ctx)
    return [
        ("branch", f"feature/rm-* branches whose leaf is Complete or that nothing claims (against {ctx.target}):", branches),
        ("worktree", "Worktrees whose branch is gone or merged, and detached worktrees:",
         worktree_findings(ctx, merged_local)),
        ("registry", (f"Registry rows on {ctx.target} with no branch (advisory: another clone's "
                      "claim looks the same until it pushes its branch) or whose leaf is Complete:"),
         _registry_findings(ctx)),
        ("stash", "Stashes specy-road left behind (git stash show -p --include-untracked <sha>):",
         _stash_findings(ctx.root)),
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
    return _Ctx(root, target, remote, base, live, complete, live_holders(root, target, nodes, complete))


def cmd_doctor(ns: argparse.Namespace) -> int:
    print_install_report()
    warn_if_running_version_older(resolve_repo_root(ns))
    bad_config = report_checkout(resolve_repo_root(ns))   # gate mismatch, env_setup failure: exit 1 after the listing
    report_unpushed(resolve_repo_root(ns))   # advisory: nested-repo commits no remote has
    ctx = _context(ns)
    if ctx is None:
        return 1
    sections = _sections(ctx)
    if not any(found for _k, _h, found in sections):
        print("Nothing to tidy: no stale branch, worktree, registry row or toolkit stash.")
        return int(bad_config)
    for _kind, heading, found in sections:
        if found:
            print(heading)
            for f in found:
                print(f"  {f.name}  — {f.reason}")
    if not ns.fix:
        print("Nothing removed. Re-run with --fix to remove them (it asks per kind).")
        return int(bad_config)
    return _fix(sections, ns.yes) or int(bad_config)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road doctor",
        description=(
            "After git fetch --prune, list feature/rm-* branches (local and remote) whose leaf is "
            "Complete or that nothing claims — merged by ancestry or patch content, leaf Complete, or claim gone — worktrees whose branch is gone or merged, other detached worktrees, registry rows with no branch or a Complete leaf, and stashes specy-road pushed; also nested-repo branches with commits no remote has. Dry-run unless --fix."
        ),
    )
    p.add_argument("--fix", action="store_true", help="Remove what is listed, asking once per kind, and report each action.")
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
