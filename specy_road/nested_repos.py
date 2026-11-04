"""Separately versioned repositories under the project root: ``nested_repos`` in ``roadmap/git-workflow.yaml``.

A project whose code lives in several git repositories below its root names
them there, by project-relative path. A leaf's linked worktree holds none of
them, so ``worker delegate`` and ``do-next-available-task --worktree`` give
each one a worktree of its own at the same path inside the leaf's worktree: on
the leaf's branch when the leaf's touch zones cover the repository, detached at
its integration tip otherwise (read-only in practice). ``worker reconcile``
diffs them, ``finish-this-task`` in merge mode merges and pushes each leaf
branch before the main repository moves, and ``review-packet`` adds their
diffs. ``doctor`` and ``grind-session --plan`` list their branches whose
commits no remote has (:func:`unpushed_branches`): finish pushes nothing else.

A path git reports inside a nested repository is prefixed with that
repository's path, so touch zones match it as they match the main
repository's files.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from specy_road.finish_implementation_check import _clean, base_ref, in_zones, zone_matches
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_code, git_ok, git_text
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.runtime_paths import project_prefix, rebase_to_project


class NestedRepoError(RuntimeError):
    """A configured nested repository cannot be given its worktree."""


@dataclass(frozen=True)
class NestedRepo:
    path: str                 # project-relative, no trailing slash
    integration_branch: str   # the main repository's unless the entry names its own
    remote: str


def nested_repos(repo_root: Path) -> list[NestedRepo]:
    """The configured nested repositories; none when the config is absent or unreadable."""
    data, err = load_git_workflow_config(repo_root)
    if err or not data:
        return []
    out = []
    for item in data.get("nested_repos") or []:
        spec = {"path": item} if isinstance(item, str) else item
        path = "/".join(seg for seg in spec["path"].split("/") if seg)   # one spelling per directory
        out.append(NestedRepo(path, spec.get("integration_branch", data["integration_branch"]),
                              spec.get("remote", data["remote"])))
    return out


def is_repo_top(path: Path) -> bool:
    """``path`` is the top of a git worktree (its own repository, not a directory of an enclosing one)."""
    top = git_text(["rev-parse", "--show-toplevel"], path) if path.is_dir() else None
    return bool(top) and Path(top).resolve() == path.resolve()


def covers(zones, path: str, prefix: str) -> bool:
    """Any of ``zones`` names the repository at project-relative ``path``, or something inside it."""
    for z in filter(None, (_clean(z) for z in zones or [])):
        for form in {z, rebase_to_project(z, prefix) or z}:
            if zone_matches(form, path) or form.startswith(f"{path}/"):
                return True
    return False


def nested_prefixes(repo_root: Path) -> tuple[str, ...]:
    """Each nested repository's directory, git-root-relative with a trailing ``/``, as the main repo names it."""
    prefix = project_prefix(repo_root)
    return tuple(f"{prefix}{nr.path}/" for nr in nested_repos(repo_root))


def in_nested(path: str, prefixes: tuple[str, ...]) -> bool:
    """A main-repository status or diff path that is, or lies in, a nested repository's directory."""
    return bool(prefixes) and f"{path.rstrip('/')}/".startswith(prefixes)


def _has_branch(repo: Path, branch: str) -> bool:
    return git_ok(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], repo)[0]


def _common_dir(repo: Path) -> Path | None:
    out = git_text(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo)
    return Path(out).resolve() if out else None


def existing_worktree_problem(src: Path, dest: Path, branch: str | None, tip: str) -> str | None:
    """Why ``dest``, already there, is not ``src``'s worktree on ``branch``, or detached at ``tip`` when
    ``branch`` is ``None``; else ``None``.

    A directory left by a build or an earlier failed setup must not pass for
    the worktree: the worker would edit something no branch carries. A detached
    one at another commit would show the worker code the integration tip does
    not have. ``tip`` is the ref a new worktree would be made at, read in ``src``.
    """
    if not is_repo_top(dest):
        return f"{dest} exists but is not a git worktree"
    if _common_dir(dest) != _common_dir(src):
        return f"{dest} is a worktree of another repository, not of {src}"
    current = git_text(["branch", "--show-current"], dest) or ""
    if branch and current != branch:
        return f"{dest} has {current or 'a detached HEAD'} checked out, not {branch}"
    if not branch and current:
        return f"{dest} has {current} checked out; outside the touch zones it must be detached"
    if not branch:
        want, head = git_text(["rev-parse", "--verify", "--quiet", f"{tip}^{{commit}}"], src), \
            git_text(["rev-parse", "HEAD"], dest)
        if not want or head != want:
            return (f"{dest} is detached at {(head or '?')[:12]}, not at the integration tip {tip} "
                    f"({(want or '?')[:12]})")
    return None


def _source_and_tip(repo_root: Path, nr: NestedRepo) -> tuple[Path, str]:
    """The configured repository and the ref of its integration tip, or :class:`NestedRepoError`.

    No ref for the configured branch (misspelt, or never fetched) is refused:
    any other commit, ``HEAD`` included, would give the worker code from a
    branch nobody named.
    """
    src = repo_root / nr.path
    if not is_repo_top(src):
        raise NestedRepoError(f"nested repo {nr.path!r} (roadmap/git-workflow.yaml): {src} is not "
                              "the top of a git repository")
    tip = base_ref(src, nr.remote, nr.integration_branch)
    if not tip:
        raise NestedRepoError(f"nested repo {nr.path!r}: neither {nr.remote}/{nr.integration_branch} nor a local "
                              f"{nr.integration_branch} exists in {src}; fetch it, or fix integration_branch/remote "
                              "for it in roadmap/git-workflow.yaml")
    return src, tip


def add_nested_worktrees(repo_root: Path, leaf_root: Path, branch: str, zones) -> list[str]:
    """Give each nested repository a worktree at its path under ``leaf_root``; one line per worktree made.

    ``repo_root`` is the main checkout's project root, where the repositories
    themselves live; ``leaf_root`` the project root inside the leaf's worktree.
    A repository the zones cover gets ``branch`` (created at its integration
    tip, or the existing branch); any other one a detached HEAD at that tip.
    One already there in that state is left alone, so a re-run adds only what
    is missing; one in any other state (:func:`existing_worktree_problem`) is
    refused. Nothing is fetched: the tip is the remote-tracking ref as it stands,
    else the local branch; with neither, the repository is refused.
    """
    prefix, made = project_prefix(repo_root), []
    for nr in nested_repos(repo_root):
        src, tip = _source_and_tip(repo_root, nr)
        dest = leaf_root / nr.path
        covered = covers(zones, nr.path, prefix)
        if dest.exists():
            problem = existing_worktree_problem(src, dest, branch if covered else None, tip)
            if problem:
                raise NestedRepoError(f"nested repo {nr.path!r}: {problem}; remove it (`git -C {src} worktree "
                                      "remove <path>`, or delete the directory), then re-run")
            continue
        if covered:
            how = f"on {branch}"
            args = [str(dest), branch] if _has_branch(src, branch) else ["-b", branch, str(dest), tip]
        else:
            how, args = f"detached at {tip} (outside the touch zones)", ["--detach", str(dest), tip]
        dest.parent.mkdir(parents=True, exist_ok=True)
        code, out = git_code(["worktree", "add", *args], src)
        if code != 0:
            raise NestedRepoError(f"cannot create a worktree of nested repo {nr.path!r} at {dest}: {out}")
        made.append(f"{nr.path}: {how}")
    return made


def align_nested_checkouts(repo_root: Path, branch: str, zones) -> list[str]:
    """For a worker in the main checkout itself (already on ``branch``): put each nested repository there in the
    state :func:`add_nested_worktrees` gives a leaf worktree; one line per repository switched.

    The worker edits these checkouts directly, so a covered one must be on
    ``branch`` (created at the integration tip when missing), else its work
    would land on whatever it had checked out and finish would skip it; an
    uncovered one is detached at the tip. One already in that state is left
    alone. A checkout is switched only when it has no tracked or untracked
    changes; otherwise, or when git refuses the switch, :class:`NestedRepoError`.
    """
    prefix, moved = project_prefix(repo_root), []
    for nr in nested_repos(repo_root):
        src, tip = _source_and_tip(repo_root, nr)
        want = branch if covers(zones, nr.path, prefix) else None
        if existing_worktree_problem(src, src, want, tip) is None:
            continue
        status = git_text(["status", "--porcelain", "--untracked-files=all"], src)
        if status is None or status:
            raise NestedRepoError(f"nested repo {nr.path!r}: {src} is not on {want or f'a detached {tip}'} and has "
                                  "uncommitted changes (or an unreadable status); commit or stash them there, "
                                  "then delegate again")
        if want:
            args = [want] if _has_branch(src, want) else ["-b", want, tip]
        else:
            args = ["--detach", tip]
        code, out = git_code(["checkout", "-q", *args], src)
        if code != 0:
            raise NestedRepoError(f"nested repo {nr.path!r}: cannot check out {want or tip} in {src}: {out}")
        moved.append(f"{nr.path}: " + (f"on {want}" if want else f"detached at {tip} (outside the touch zones)"))
    return moved


def announce_nested_worktrees(repo_root: Path, leaf_root: Path, branch: str, zones) -> None:
    """:func:`add_nested_worktrees` for pickup, whose claim is already pushed: a failure is a warning."""
    try:
        for line in add_nested_worktrees(repo_root, leaf_root, branch, zones):
            print(f"nested repo {line}")
    except NestedRepoError as e:
        print(f"warning: {e}; fix it, then `specy-road worker delegate` adds the missing worktrees")


def nested_worktree_dirs(repo_root: Path, leaf_root: Path) -> list[tuple[str, Path]]:
    """``(git-root-relative path, directory)`` of each nested repository present under ``leaf_root``.

    What ``worker delegate`` checks for uncommitted work before a launch, as it checks the main tree.
    """
    prefix = project_prefix(repo_root)
    return [(f"{prefix}{nr.path}", leaf_root / nr.path) for nr in nested_repos(repo_root)
            if is_repo_top(leaf_root / nr.path)]


def _merge_base(repo: Path, nr: NestedRepo, tip: str) -> str | None:
    base = base_ref(repo, nr.remote, nr.integration_branch)
    return git_text(["merge-base", base, tip], repo) if base else None


def nested_changes(repo_root: Path, leaf_root: Path) -> tuple[list[str], list[str]]:
    """``(changed, untracked)`` in the nested repositories under ``leaf_root``, git-root-relative to the main repo.

    Changed is everything since the repository's merge base with its
    integration branch, committed or not: a detached, read-only one shows only
    its uncommitted edits.
    """
    prefix, changed, untracked = project_prefix(repo_root), [], []
    for nr in nested_repos(repo_root):
        d = leaf_root / nr.path
        mb = _merge_base(d, nr, "HEAD") if is_repo_top(d) else None
        if not mb:
            continue
        lead = f"{prefix}{nr.path}/"
        changed += [lead + p for p in diff_paths(d, mb) or []]
        out = git_text(["ls-files", "--others", "--exclude-standard"], d) or ""
        untracked += [lead + p for p in out.splitlines() if p.strip()]
    return sorted(changed), sorted(untracked)


def branch_tip(repo: Path, nr: NestedRepo, branch: str) -> str | None:
    """The commit ``branch`` names in ``repo``: the local branch, else the remote-tracking one."""
    for ref in (f"refs/heads/{branch}", f"refs/remotes/{nr.remote}/{branch}"):
        sha = git_text(["rev-parse", "--verify", "--quiet", ref], repo)
        if sha:
            return sha
    return None


def branch_diff_range(repo_root: Path, nr: NestedRepo, branch: str) -> str | None:
    """``<merge base>...<tip>`` of ``branch`` in the nested repository, or ``None`` when it has no such branch."""
    d = repo_root / nr.path
    tip = branch_tip(d, nr, branch) if is_repo_top(d) else None
    mb = _merge_base(d, nr, tip) if tip else None
    return f"{mb}...{tip}" if mb else None


def nested_zone_paths(repo_root: Path, zones) -> list[str]:
    """Project-relative paths the current branch changed, inside ``zones``, in the nested repositories.

    For finish's implementation gate: a leaf whose work lives only in a nested
    repository changes nothing in the main one but its bookkeeping.
    """
    branch = git_text(["branch", "--show-current"], repo_root)
    prefix, out = project_prefix(repo_root), []
    for nr in nested_repos(repo_root) if branch else []:
        rng = branch_diff_range(repo_root, nr, branch)
        paths = (diff_paths(repo_root / nr.path, rng) or []) if rng else []
        out += [f"{nr.path}/{p}" for p in paths if in_zones(zones, f"{prefix}{nr.path}/{p}", prefix)]
    return out


def _land_one(repo: Path, nr: NestedRepo, feature_branch: str) -> str | None:
    """Merge ``feature_branch`` onto ``remote/integration_branch`` in a temporary worktree and push; why not, or ``None``.

    No checkout of the repository is touched: the merge is made detached and
    pushed straight to the remote. A branch already on the remote's tip (a
    re-run after the main repository failed) is skipped.
    """
    ib, rm = nr.integration_branch, nr.remote
    code, out = git_code(["fetch", rm], repo)
    if code != 0:
        return f"git fetch {rm} failed: {out}"
    tip = git_text(["rev-parse", "--verify", "--quiet", f"refs/remotes/{rm}/{ib}"], repo)
    if not tip:
        return f"no {rm}/{ib} to merge into"
    if git_ok(["merge-base", "--is-ancestor", feature_branch, tip], repo)[0]:
        return None
    holder = Path(tempfile.mkdtemp(prefix="specy-road-nested-land-"))
    tree = holder / "tree"
    try:
        code, out = git_code(["worktree", "add", "--detach", str(tree), tip], repo)
        if code != 0:
            return f"could not create a worktree of {tip[:12]}: {out}"
        code, out = git_code(["merge", "--no-ff", "--no-edit", feature_branch], tree)
        if code != 0:
            git_code(["merge", "--abort"], tree)
            return f"merging {feature_branch} into {rm}/{ib} failed: {out}"
        code, out = git_code(["push", rm, f"HEAD:refs/heads/{ib}"], tree)
        if code != 0:
            return f"git push {rm} {ib} failed: {out}"
        print(f"[ok] nested repo {nr.path}: merged {feature_branch} into {ib} and pushed to {rm}")
        return None
    finally:
        git_code(["worktree", "remove", "--force", str(tree)], repo)
        shutil.rmtree(holder, ignore_errors=True)


def land_nested_branches(repo_root: Path, feature_branch: str) -> tuple[bool, str]:
    """Merge and push ``feature_branch`` in every nested repository that has it, before the main repository.

    ``(True, "")`` when each landed or had nothing to land (a repository
    without the branch); the first failure stops here, so the main repository
    has not moved. A configured path that is not a repository is a failure,
    not nothing to land: whether it held the leaf's work cannot be told.
    Repositories already landed stay landed: a re-run skips them.
    """
    for nr in nested_repos(repo_root):
        repo = repo_root / nr.path
        if not is_repo_top(repo):
            err = (f"{repo} is not the top of a git repository (roadmap/git-workflow.yaml names it), so its "
                   "leaf branch cannot be landed; restore it or drop it from nested_repos")
        elif not _has_branch(repo, feature_branch):
            continue
        else:
            err = _land_one(repo, nr, feature_branch)
        if err:
            return False, (f"nested repo {nr.path!r}: {err}. The main repository was not merged; "
                           "fix it there, then re-run (nested repos already landed are skipped)")
    return True, ""


def _unpushed(repo: Path, branch: str, upstream: str, track: str, has_remote: bool) -> tuple[str, int]:
    """``(state, commits)`` for one local branch; ``commits`` 0 when every one is on a remote."""
    if not has_remote:
        return "no remote", int(git_text(["rev-list", "--count", f"refs/heads/{branch}"], repo) or 0)
    if not upstream or track == "gone":
        count = git_text(["rev-list", "--count", f"refs/heads/{branch}", "--not", "--remotes"], repo)
        return "no upstream", int(count or 0)
    ahead = re.search(r"ahead (\d+)", track)
    return "ahead", int(ahead.group(1)) if ahead else 0


def unpushed_branches(repo_root: Path) -> list[dict]:
    """Each local branch of a configured nested repository holding commits its remotes lack.

    ``{"repo", "branch", "commits", "state", "upstream"}``: ``state`` is
    ``ahead`` (``commits`` past ``upstream``), ``no upstream`` (``commits`` on
    no remote branch; also when the upstream was deleted) or ``no remote`` (the
    repository has none, so every commit counts). A branch with nothing to push
    is left out, and so is a configured path that is not a repository: delegate
    and finish report that one.
    """
    fmt = "%(refname:short)%09%(upstream:short)%09%(upstream:track,nobracket)"
    out = []
    for nr in nested_repos(repo_root):
        repo = repo_root / nr.path
        if not is_repo_top(repo):
            continue
        has_remote = bool(git_text(["remote"], repo))
        for line in (git_text(["for-each-ref", f"--format={fmt}", "refs/heads"], repo) or "").splitlines():
            branch, upstream, track = (line.split("\t") + ["", ""])[:3]   # git_text strips trailing tabs
            state, commits = _unpushed(repo, branch, upstream, track, has_remote)
            if commits:
                out.append({"repo": nr.path, "branch": branch, "commits": commits, "state": state,
                            "upstream": upstream if state == "ahead" else None})
    return out


def describe_unpushed(u: dict) -> str:
    """One line for a :func:`unpushed_branches` entry, naming the repository, branch and commit count."""
    where = {"ahead": f"ahead of {u['upstream']}", "no upstream": "on no remote branch (no upstream)",
             "no remote": "in a repository with no remote"}[u["state"]]
    return f"{u['repo']}: {u['branch']} has {u['commits']} commit(s) {where}"


def report_unpushed(repo_root: Path) -> None:
    """``doctor``'s advisory listing of :func:`unpushed_branches`; nothing when there are none."""
    found = unpushed_branches(repo_root)
    if found:
        print("Nested repos with commits no remote has (finish pushes only the leaf branch it lands):")
        for u in found:
            print(f"  {describe_unpushed(u)}")
