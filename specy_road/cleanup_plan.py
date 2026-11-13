"""The one cleanup planner: what ``doctor --prune`` and its aliases remove, as a list of findings.

Four kinds, each its own section (:data:`KINDS`):

- ``feature/rm-*`` branches, local and on the remote, whose leaf is Complete on the integration
  branch (registry row or not), or that nothing claims: no registry row (in this checkout or on
  the integration branch) and not an open milestone rollup. Each row says why: merged, its leaf
  Complete, or only that its claim is gone; an unmerged one also says how many commits the
  integration branch lacks, and is listed and left (the merged-only rule below). A local
  branch checked out in a worktree this run does not remove (the main checkout included) is
  left: git cannot delete it.
- linked worktrees whose directory is missing, whose branch is gone (detached at a commit the
  integration branch contains or whose patch it has, the same test as a branch: how ``finish
  --delete-branch`` leaves a delegate worktree) or is merged, whether or not the branch itself is
  listed (a claimed branch whose leaf is not Complete stays), and every other detached worktree
  (a review recipe's). ``--prune`` leaves one with uncommitted changes, a detached one with
  commits no branch holds, or one in a temporary directory another command may be using
  (:data:`~specy_road.doctor_worktrees.TEMP_WORKTREES`).
- registry rows on the integration branch whose branch is in neither this clone nor the remote
  and whose leaf is not Complete (advisory: another clone's claim looks the same until its branch
  is pushed; ``--prune`` leaves the row and names ``specy-road registry-prune --remove
  <CODENAME>``), or whose leaf is Complete (``--prune`` removes it; the report says the branch is
  listed above only when that branch is in this clone or on the remote).
- stashes the toolkit pushed (``specy-road: …``; pickup and review used to stash ``work/``, and
  a failed restore left the entry behind).

One merged rule and one live rule decide every branch and worktree
(:func:`specy_road.doctor_worktrees.classify`): merged is ancestry first, then patch content
(every commit upstream, ``git cherry``: a rebase; or the branch's whole diff: a squash). A branch
with no commit of its own is "no commits yet", never merged. **Merged-only rule:** a branch is
removed only when it is merged (ancestry, or the same patch) with evidence of its own commits;
every other branch is listed and left, so no form of the cleanup path, alias or not, ever
deletes work the integration branch lacks. Live is an open claim or rollup, or a
worker or session the orchestration state reads (:func:`~specy_road.doctor_worktrees.live_holders`).

Planning changes nothing. :func:`apply` removes exactly the findings that carry a removal, in
:data:`FIX_ORDER`, asking once per kind. The aliases select a subset of the same findings
(:func:`branches_prune_scope`); ``worktree prune <ID>`` and the grind cleanup read the same live
rule (:func:`held_branches`).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from specy_road.bundled_scripts.do_next_task_self_heal import detect_stale_claims
from specy_road.cli import run_captured
from specy_road.doctor_worktrees import (
    NO_EVIDENCE, Finding, classify, containment, evidence_kind, live_holders, merged_how,
    worktree_branches, worktree_findings,
)
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_checked, git_code, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.roadmap_load_at_ref import load_roadmap_nodes_at_ref

PATTERN = "feature/rm-*"
TOOLKIT_STASH = re.compile(r"^On [^:]+: specy-road: ")
#: ``--kind`` value -> the finding kind it selects.
KINDS = {"branches": "branch", "worktrees": "worktree", "registry": "registry", "stashes": "stash"}
#: Worktrees before branches (a checked-out branch cannot be deleted); registry rows last,
#: because the row removal checks out the integration branch.
FIX_ORDER = ("worktree", "branch", "stash", "registry")

Section = tuple[str, str, list[Finding]]


def feature_branches(root: Path, prefix: str) -> list[str]:
    """The ``feature/rm-*`` branch names under ``prefix`` (``refs/heads/`` or
    ``refs/remotes/<remote>/``)."""
    out = git_text(["for-each-ref", "--format=%(refname)", prefix + PATTERN], root) or ""
    return [ref.removeprefix(prefix) for ref in out.splitlines()]


def _open_rollups(root: Path, target: str) -> set[str] | None:
    """Rollup branches ``target``'s roadmap still has open, or ``None`` if unreadable.

    The working tree can be behind the integration branch the planner just fetched.
    Its roadmap would miss a rollup the remote still marks active, and a delete
    would remove it.
    """
    nodes = load_roadmap_nodes_at_ref(root, target)
    if nodes is None:
        return None
    return {
        me.get("rollup_branch")
        for node in nodes
        if isinstance(me := node.get("milestone_execution"), dict)
        and me.get("state") != "closed"
    }


def live_branches(root: Path, target: str) -> set[str] | None:
    """Branches a registry row or open rollup names, or ``None`` when the remote roadmap cannot be
    read."""
    rollups = _open_rollups(root, target)
    if rollups is None:
        return None
    live: set[str] = set(rollups)
    for reg in (read_registry(registry_path(root)),
                read_registry_at_ref(root, target, DEFAULT_TIMEOUT) or {}):
        live.update(e.get("branch") for e in reg.get("entries") or [] if isinstance(e, dict))
    return live


def fetch_integration(root: Path, ns: argparse.Namespace) -> tuple[str, str] | None:
    """``(base, remote)`` from ``--base``/``--remote`` or config, after ``git fetch --prune``.

    ``None`` when the fetch failed, which is printed.
    """
    base, remote, warns = resolve_integration_defaults(
        root, explicit_base=ns.base, explicit_remote=ns.remote
    )
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    code, out = git_code(["fetch", "--prune", remote], root)
    if code != 0:
        print(
            f"error: git fetch --prune {remote} failed: {out}\n"
            f"  Merged means contained in {remote}/{base}, and a stale copy of "
            "it could delete work pushed since. Fix the remote, then re-run.",
            file=sys.stderr,
        )
        return None
    return base, remote


@dataclass
class PlanContext:
    root: Path
    target: str
    remote: str
    base: str
    live: set[str]   # every branch a registry row or open rollup names (:func:`live_branches`)
    complete: dict[str, str]   # codename -> node id of a Complete leaf
    # branch -> (live source, "live: …"): doctor_worktrees.live_holders
    held: dict[str, tuple[str, str]]
    held_paths: dict[str, tuple[str, str]]  # resolved worktree path -> (live source, "live: …")


def complete_leaves(nodes: list[dict]) -> dict[str, str]:
    """Codename -> id of each leaf whose status is Complete."""
    parents = {n.get("parent_id") for n in nodes}
    return {n["codename"]: n["id"] for n in nodes
            if n.get("codename") and n.get("id") not in parents
            and (n.get("status") or "").lower() == "complete"}


def held_branches(root: Path, target: str) -> tuple[dict[str, tuple[str, str]],
                                                    dict[str, tuple[str, str]]]:
    """The live rule alone, against ``target``'s roadmap: (by branch, by worktree path)."""
    nodes = load_roadmap_nodes_at_ref(root, target) or []
    return live_holders(root, target, nodes, complete_leaves(nodes))


def _branch_reason(ctx: PlanContext, ref: str, branch: str, node_id: str | None, kind: str
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
              "merged, no evidence": f"merged{leaf}{row}; {NO_EVIDENCE}"}.get(
                  label, f"{how}{leaf}{row}")
    return reason, label, fix, inputs


def _delete_local(root: Path, branch: str, sha: str | None) -> str | None:
    if git_text(["rev-parse", f"refs/heads/{branch}"], root) != sha:
        return "moved since it was listed; left alone"
    code, out = git_code(["branch", "-D", branch], root)
    return out if code else None


def _delete_remote(root: Path, branch: str, sha: str | None, remote: str) -> str | None:
    # Leased to the tip that was listed: a push since then is refused.
    code, out = git_code(
        ["push", remote, f"--force-with-lease=refs/heads/{branch}:{sha}", "--delete", branch], root)
    return f"left on {remote}. {out}" if code else None


def _branch_findings(ctx: PlanContext) -> tuple[list[Finding], dict[str, tuple[str, str]]]:
    """Complete or unclaimed branches, and the classification inputs of every local
    ``feature/rm-*``.

    Those inputs feed the worktree section, which judges a worktree on a branch even when the
    branch itself is not listed. A claimed branch is in-progress work and is not listed; any other
    verdict without a fix (live worker or session, no commits yet, merged with no evidence) is
    listed with ``so --prune leaves it``.
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
            name = f"{where:<9} {b}"
            if not fix:
                found.append(Finding("branch", name, f"{reason}, so --prune leaves it", None, "",
                                     label, b))
                continue
            sha = git_text(["rev-parse", prefix + b], ctx.root)
            if where == "local":
                remove, done = partial(_delete_local, ctx.root, b, sha), f"deleted local branch {b}"
            else:
                remove = partial(_delete_remote, ctx.root, b, sha, ctx.remote)
                done = f"deleted {b} on {ctx.remote}"
            found.append(Finding("branch", name, reason, remove, done, label, b))
    return found, local


def _keep_checked_out(ctx: PlanContext, branches: list[Finding], removed: set[str]
                      ) -> list[Finding]:
    """Leave each local branch a worktree outside ``removed`` has checked out: git refuses to
    delete it."""
    checked_out = {b: p for p, b in worktree_branches(ctx.root) if p not in removed}
    out = []
    for f in branches:
        path = checked_out.get(f.branch) if f.remove and f.name.startswith("local ") else None
        out.append(f if path is None else Finding(
            f.kind, f.name, f"{f.reason}; checked out in {path}, so --prune leaves it", None, "",
            f.label, f.branch))
    return out


def _prune_row(ctx: PlanContext, codename: str) -> str | None:
    """``registry-prune --remove``: it syncs, commits on the integration branch and pushes.

    Its output is captured and only a failure's is reported: a finding's one line.
    """
    status, out, err = run_captured(
        "registry_prune",
        ["--remove", codename, "--base", ctx.base, "--remote", ctx.remote,
         "--repo-root", str(ctx.root)],
    )
    return (err or out).strip() if status else None


# True when the branch is in this clone or on the remote, so the branch section lists it.
_COMPLETE_REASON = {
    True: "leaf Complete; {branch} is listed above",
    False: "leaf Complete",
}


def _registry_findings(ctx: PlanContext) -> list[Finding]:
    """Remove a Complete row. Say its branch is listed above only when that branch is in this
    clone or on the remote. Any other row with no branch is advisory and ``--prune`` leaves it.
    """
    reg = read_registry_at_ref(ctx.root, ctx.target, DEFAULT_TIMEOUT) or {}
    stale = {e["codename"]
             for e in detect_stale_claims(repo_root=ctx.root, reg=reg, remote=ctx.remote)}
    found = []
    for e in reg.get("entries") or []:
        codename = e["codename"]
        if codename in ctx.complete:
            why = _COMPLETE_REASON[codename not in stale].format(branch=e["branch"])
            remove = partial(_prune_row, ctx, codename)
            done = f"removed registry row {codename} on {ctx.target}"
        elif codename in stale:
            why = (
                f"{e['branch']} is in neither this clone nor {ctx.remote} "
                "(advisory: another clone's claim looks the same until it pushes its branch; "
                "confirm that clone no longer holds the claim, then "
                f"specy-road registry-prune --remove {codename}), so --prune leaves it"
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


def stash_section(root: Path) -> Section:
    return ("stash",
            "Stashes specy-road left behind (git stash show -p --include-untracked <sha>):",
            _stash_findings(root))


def plan(ctx: PlanContext, kinds: set[str]) -> list[Section]:
    """(kind, heading, findings) in report order, for the finding kinds in ``kinds``."""
    branches, merged_local = _branch_findings(ctx)
    worktrees = worktree_findings(ctx, merged_local)
    removed = {f.name for f in worktrees if f.remove} if "worktree" in kinds else set()
    sections = [
        ("branch", ("feature/rm-* branches whose leaf is Complete or that nothing claims "
                    f"(against {ctx.target}):"), _keep_checked_out(ctx, branches, removed)),
        ("worktree", "Worktrees whose branch is gone or merged, and detached worktrees:",
         worktrees),
        ("registry", (f"Registry rows on {ctx.target} with no branch (advisory: another clone's "
                      "claim looks the same until it pushes its branch; --prune leaves them — "
                      "specy-road registry-prune --remove <CODENAME>) or whose leaf is Complete:"),
         _registry_findings(ctx) if "registry" in kinds else []),
        stash_section(ctx.root),
    ]
    return [s for s in sections if s[0] in kinds]


def branches_prune_scope(ctx: PlanContext, found: list[Finding]) -> list[Finding]:
    """``branches prune``'s selection: merged by ancestry, with no registry row or open rollup."""
    return [f for f in found if f.remove and f.label == "merged" and f.branch not in ctx.live]


def _confirm(kind: str, n: int) -> bool | None:
    """True/False for the answer, ``None`` when stdin has none to give."""
    try:
        answer = input(f"Remove the {n} listed {kind} item(s)? [y/N] ")
    except EOFError:
        return None
    return answer.strip().lower() in ("y", "yes")


def apply(sections: list[Section], yes: bool) -> int:
    """Remove each planned finding, asking once per kind unless ``yes``; 1 when any failed."""
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
            print("\nNo answer on stdin; pass --yes to remove without asking. Stopped.",
                  file=sys.stderr)
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


def no_remote(root: Path, ns: argparse.Namespace) -> bool:
    """True, printed, when the remote :func:`fetch_integration` would fetch is not configured."""
    _base, remote, warns = resolve_integration_defaults(
        root, explicit_base=ns.base, explicit_remote=ns.remote)
    if (git_code(["remote", "get-url", remote], root)[0] == 0
            or git_code(["rev-parse", "--git-dir"], root)[0]):
        # configured, or not a repository: fetch_integration resolves it again and reports either
        return False
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    print(f"doctor: no git remote named {remote!r} is configured; "
          "skipped fetch and the branch, worktree and registry checks that compare against it.")
    return True


def context(root: Path, ns: argparse.Namespace) -> PlanContext | None:
    """Fetch, then read what the planner judges against; ``None``, printed, when it cannot."""
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
    complete = complete_leaves(nodes)
    return PlanContext(root, target, remote, base, live, complete,
                       *live_holders(root, target, nodes, complete))
