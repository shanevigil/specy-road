#!/usr/bin/env python3
"""``specy-road doctor``: list what the task loop left behind; remove it with ``--fix``.

Four kinds, each its own section:

- ``feature/rm-*`` branches, local and on the remote, that nothing claims: no
  registry row (in this checkout or on the integration branch) and not an open
  milestone rollup — the same "live" test ``branches prune`` uses. Each row says
  why: merged, its leaf Complete, or only that its claim is gone; an unmerged
  one also says how many commits the integration branch lacks.
- linked worktrees whose directory is missing, whose branch is gone (detached at
  a commit the integration branch contains, which is how ``finish
  --delete-branch`` leaves a delegate worktree) or is one of the merged branches.
- registry rows on the integration branch whose branch is in neither this clone
  nor the remote. Advisory, as in ``registry-prune``: another clone's claim looks
  the same until its branch is pushed.
- stashes the toolkit pushed (``specy-road: …``; pickup and review used to stash
  ``work/``, and a failed restore left the entry behind).

Merged is ancestry first. When ancestry fails, patch content decides: every
commit has an equivalent upstream (``git cherry``: a rebase), or the branch's
whole diff does (a squash). A rewritten landing is therefore still merged.

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
from typing import Callable

from specy_road.bundled_scripts.branches_cli import (
    feature_branches,
    fetch_integration,
    live_branches,
)
from specy_road.bundled_scripts.do_next_task_self_heal import detect_stale_claims
from specy_road.bundled_scripts.grind_session_cleanup import merged_into
from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_checked, git_code, git_text
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

TOOLKIT_STASH = re.compile(r"^On [^:]+: specy-road: ")
# commit-tree needs an identity, and a CI runner may have none configured.
_PROBE_IDENT = ["-c", "user.name=specy-road", "-c", "user.email=doctor@specy-road.invalid"]
SAME_PATCH = "merged (same patch content)"


@dataclass
class Finding:
    kind: str
    name: str
    reason: str
    remove: Callable[[], str | None]   # the failure message, or None
    done: str


@dataclass
class _Ctx:
    root: Path
    target: str
    remote: str
    base: str
    live: set[str]
    complete: dict[str, str]   # codename -> node id of a Complete leaf


def _all_upstream(root: Path, target: str, ref: str) -> bool:
    lines = (git_text(["cherry", target, ref], root) or "").splitlines()
    return bool(lines) and all(line.startswith("-") for line in lines)


def merged_how(root: Path, ref: str, target: str) -> str | None:
    """``"merged"``, :data:`SAME_PATCH`, or ``None`` when ``target`` lacks ``ref``'s work."""
    if merged_into(root, ref, target):
        return "merged"
    if _all_upstream(root, target, ref):
        return SAME_PATCH
    base = git_text(["merge-base", target, ref], root)
    if base is None:   # an orphan branch shares no history with target
        return None
    # The whole branch as one commit on its merge base: what a squash lands.
    squash = git_checked(
        [*_PROBE_IDENT, "commit-tree", f"{ref}^{{tree}}", "-p", base, "-m", "doctor squash probe"],
        root,
    )
    return SAME_PATCH if _all_upstream(root, target, squash) else None


def _complete_leaves(nodes: list[dict]) -> dict[str, str]:
    parents = {n.get("parent_id") for n in nodes}
    return {
        n["codename"]: n["id"]
        for n in nodes
        if n.get("codename") and n.get("id") not in parents
        and (n.get("status") or "").lower() == "complete"
    }


def _branch_reason(ctx: _Ctx, ref: str, branch: str) -> tuple[str, bool]:
    how = merged_how(ctx.root, ref, ctx.target)
    if how:
        return how, True
    ahead = git_checked(["rev-list", "--count", f"{ctx.target}..{ref}"], ctx.root)
    node_id = ctx.complete.get(branch.removeprefix("feature/rm-"))
    why = f"leaf {node_id} Complete" if node_id else "claim gone"
    return f"{why}, not merged: {ahead} commit(s) {ctx.target} lacks", False


def _delete_local(root: Path, branch: str, sha: str | None) -> str | None:
    if git_text(["rev-parse", f"refs/heads/{branch}"], root) != sha:
        return "moved since it was listed; left alone"
    code, out = git_code(["branch", "-D", branch], root)
    return out if code else None


def _delete_remote(root: Path, branch: str, sha: str | None, remote: str) -> str | None:
    # Leased to the tip that was listed: a push since then is refused.
    code, out = git_code(
        ["push", remote, f"--force-with-lease=refs/heads/{branch}:{sha}", "--delete", branch],
        root,
    )
    return f"left on {remote}. {out}" if code else None


def _branch_findings(ctx: _Ctx) -> tuple[list[Finding], set[str]]:
    """Unclaimed branches, and the local ones among them that are merged."""
    found: list[Finding] = []
    merged_local: set[str] = set()
    for prefix, where in (("refs/heads/", "local"), (f"refs/remotes/{ctx.remote}/", ctx.remote)):
        for b in feature_branches(ctx.root, prefix):
            if b in ctx.live:
                continue
            reason, merged = _branch_reason(ctx, prefix + b, b)
            sha = git_text(["rev-parse", prefix + b], ctx.root)
            if where == "local":
                if merged:
                    merged_local.add(b)
                remove, done = partial(_delete_local, ctx.root, b, sha), f"deleted local branch {b}"
            else:
                remove = partial(_delete_remote, ctx.root, b, sha, ctx.remote)
                done = f"deleted {b} on {ctx.remote}"
            found.append(Finding("branch", f"{where:<9} {b}", reason, remove, done))
    return found, merged_local


def _worktrees(root: Path) -> list[dict[str, str]]:
    out = git_text(["worktree", "list", "--porcelain"], root) or ""
    blocks = []
    for chunk in out.split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in chunk.splitlines())
        if "worktree" in wt:
            blocks.append(wt)
    return blocks


def _worktree_reason(ctx: _Ctx, wt: dict[str, str], merged_local: set[str]) -> str | None:
    if "prunable" in wt:
        return "directory missing"
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    if not branch:
        head = wt.get("HEAD", "")
        if head and merged_into(ctx.root, head, ctx.target):
            return f"branch gone: detached at {head[:12]}, which {ctx.target} contains"
        return None
    if branch in merged_local:
        return f"branch {branch} is merged"
    return None


def _ignored_note(path: Path) -> str:
    """``git worktree remove`` deletes ignored files (``work/``…) without asking: say which."""
    if not path.is_dir():
        return ""
    out = git_text(["status", "--porcelain", "--ignored"], path) or ""
    ignored = [line[3:] for line in out.splitlines() if line.startswith("!! ")]
    return f"; removing it deletes ignored {', '.join(ignored)}" if ignored else ""


def _remove_worktree(root: Path, path: str) -> str | None:
    code, out = git_code(["worktree", "remove", path], root)
    return out if code else None


def _worktree_findings(ctx: _Ctx, merged_local: set[str]) -> list[Finding]:
    here = Path(git_checked(["rev-parse", "--show-toplevel"], ctx.root)).resolve()
    found = []
    for wt in _worktrees(ctx.root)[1:]:   # the first is the main worktree
        path = wt["worktree"]
        if "locked" in wt or Path(path).resolve() == here:
            continue
        reason = _worktree_reason(ctx, wt, merged_local)
        if reason:
            found.append(Finding(
                "worktree", path, reason + _ignored_note(Path(path)),
                partial(_remove_worktree, ctx.root, path), f"removed worktree {path}",
            ))
    return found


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
    return [
        Finding(
            "registry", e["codename"],
            f"node {e['node_id']}: {e['branch']} is in neither this clone nor {ctx.remote}",
            partial(_prune_row, ctx, e["codename"]),
            f"removed registry row {e['codename']} on {ctx.target}",
        )
        for e in detect_stale_claims(repo_root=ctx.root, reg=reg, remote=ctx.remote)
    ]


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
        ("branch", f"feature/rm-* branches nothing claims (against {ctx.target}):", branches),
        ("worktree", "Worktrees whose branch is gone or merged:", _worktree_findings(ctx, merged_local)),
        ("registry", (f"Registry rows on {ctx.target} with no branch (advisory: another "
                      "clone's claim looks the same until it pushes its branch):"),
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
        found = by_kind.get(kind)
        if not found:
            continue
        ok = True if yes else _confirm(kind, len(found))
        if ok is None:
            print("\nNo answer on stdin; pass --yes to remove without asking. "
                  "Stopped.", file=sys.stderr)
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
        print(f"error: could not read the roadmap at {target}. Not listing anything.",
              file=sys.stderr)
        return None
    return _Ctx(root, target, remote, base, live, _complete_leaves(nodes))


def cmd_doctor(ns: argparse.Namespace) -> int:
    ctx = _context(ns)
    if ctx is None:
        return 1
    sections = _sections(ctx)
    if not any(found for _k, _h, found in sections):
        print("Nothing to tidy: no stale branch, worktree, registry row or toolkit stash.")
        return 0
    for _kind, heading, found in sections:
        if found:
            print(heading)
            for f in found:
                print(f"  {f.name}  — {f.reason}")
    if not ns.fix:
        print("Nothing removed. Re-run with --fix to remove them (it asks per kind).")
        return 0
    return _fix(sections, ns.yes)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road doctor",
        description=(
            "After git fetch --prune, list feature/rm-* branches (local and "
            "remote) nothing claims — merged by ancestry or patch content, "
            "leaf Complete, or claim gone — worktrees whose branch is gone or "
            "merged, registry rows with no branch, and stashes specy-road "
            "pushed. Dry-run unless --fix."
        ),
    )
    p.add_argument("--fix", action="store_true",
                   help="Remove what is listed, asking once per kind, and report each action.")
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
