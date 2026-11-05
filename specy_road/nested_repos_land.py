"""Landing a leaf's branch in each ``nested_repos`` repository, and the branches no remote has.

Split from :mod:`specy_road.nested_repos`, which re-exports the public names.
Each entry's ``land`` decides how ``finish-this-task`` (merge mode) lands the
leaf's branch there, before the main repository moves: ``push`` merges onto
``<remote>/<integration_branch>`` and pushes; ``local`` merges onto the local
integration branch and moves only that ref, pushing nothing; ``manual`` lands
nothing and stops finish with the merge command to run by hand.
"""

from __future__ import annotations

import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from specy_road.git_subprocess import git_code, git_ok, git_text

if TYPE_CHECKING:
    from specy_road.nested_repos import NestedRepo
# nested_repos re-exports this module's public names, so its own are imported inside the functions that use them.


def _checked_out_in(repo: Path, branch: str) -> Path | None:
    """The worktree of ``repo`` that has ``branch`` checked out, if any."""
    current = None
    for line in (git_text(["worktree", "list", "--porcelain"], repo) or "").splitlines():
        if line.startswith("worktree "):
            current = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}":
            return current
    return None


def _merge_in_temp_tree(repo: Path, tip: str, feature_branch: str, onto: str, finish) -> str | None:
    """Merge ``feature_branch`` onto ``tip`` in a detached temporary worktree, then ``finish(tree)``; why not, or ``None``.

    No checkout of the repository is touched by the merge itself.
    """
    holder = Path(tempfile.mkdtemp(prefix="specy-road-nested-land-"))
    tree = holder / "tree"
    try:
        code, out = git_code(["worktree", "add", "--detach", str(tree), tip], repo)
        if code != 0:
            return f"could not create a worktree of {tip[:12]}: {out}"
        code, out = git_code(["merge", "--no-ff", "--no-edit", feature_branch], tree)
        if code != 0:
            git_code(["merge", "--abort"], tree)
            return f"merging {feature_branch} into {onto} failed: {out}"
        return finish(tree)
    finally:
        git_code(["worktree", "remove", "--force", str(tree)], repo)
        shutil.rmtree(holder, ignore_errors=True)


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

    def push(tree: Path) -> str | None:
        code, out = git_code(["push", rm, f"HEAD:refs/heads/{ib}"], tree)
        if code != 0:
            return f"git push {rm} {ib} failed: {out}"
        print(f"[ok] nested repo {nr.path}: merged {feature_branch} into {ib} and pushed to {rm}")
        return None

    return _merge_in_temp_tree(repo, tip, feature_branch, f"{rm}/{ib}", push)


def _follow_in_checkout(repo: Path, holder: Path, ref: str, tip: str, merge: str) -> str | None:
    """Update ``holder``'s index and files from ``tip`` to ``merge`` after ``ref`` moved; why not, or ``None``.

    Only while ``holder`` still has ``ref`` checked out; on any failure ``ref``
    is put back to ``tip`` (compare-and-swap: only if it still names ``merge``).
    """
    switched = git_text(["symbolic-ref", "-q", "HEAD"], holder) != ref
    code, out = (1, "it switched branch or detached") if switched else \
        git_code(["read-tree", "-m", "-u", tip, merge], holder)
    if code == 0:
        return None
    git_code(["update-ref", ref, tip, merge], repo)
    ib = ref.removeprefix("refs/heads/")
    return f"could not update the checkout of {ib} in {holder}: {out}; {ib} was not moved; re-run"


def _land_one_locally(repo: Path, nr: NestedRepo, feature_branch: str) -> str | None:
    """``land: local``: merge ``feature_branch`` onto the local integration branch and move only that ref.

    Nothing is fetched or pushed. ``refs/heads/<ib>`` itself moves, by
    compare-and-swap from the commit the merge was made on, so a branch moved
    meanwhile is refused. Where the branch is checked out, that worktree must be
    clean, and must still have ``<ib>`` checked out after the merge (not
    detached, not another branch, even at the same commit); its index and files
    then follow the ref, and the ref is put back if they cannot. Success is
    reported only once ``refs/heads/<ib>`` contains the merge. Already merged (a
    re-run) is skipped.
    """
    ib = nr.integration_branch
    tip = git_text(["rev-parse", "--verify", "--quiet", f"refs/heads/{ib}"], repo)
    if not tip:
        return f"no local {ib} to merge into (land: local)"
    if git_ok(["merge-base", "--is-ancestor", feature_branch, tip], repo)[0]:
        return None
    holder = _checked_out_in(repo, ib)
    if holder is not None:
        status = git_text(["status", "--porcelain", "--untracked-files=no"], holder)
        if status is None or status:
            return (f"{ib} is checked out in {holder} with uncommitted changes (or an unreadable status); "
                    "commit or stash them there, then re-run")

    ref = f"refs/heads/{ib}"

    def move_ref(tree: Path) -> str | None:
        merge = git_text(["rev-parse", "HEAD"], tree) or ""
        if holder is not None and git_text(["symbolic-ref", "-q", "HEAD"], holder) != ref:
            return (f"{holder} no longer has {ib} checked out (switched branch or detached during the merge); "
                    f"{ib} was not moved; re-run")
        code, out = git_code(["update-ref", ref, merge, tip], repo)   # compare-and-swap on the named ref
        if code != 0:
            return f"could not move {ib} to the merge {merge[:12]} ({ib} moved meanwhile?): {out}; re-run"
        err = _follow_in_checkout(repo, holder, ref, tip, merge) if holder is not None else None
        if err:
            return err
        if not git_ok(["merge-base", "--is-ancestor", merge, ref], repo)[0]:
            return f"{ib} does not contain the merge {merge[:12]} after moving it; re-run"
        print(f"[ok] nested repo {nr.path}: merged {feature_branch} into local {ib} (land: local; nothing pushed)")
        return None

    return _merge_in_temp_tree(repo, tip, feature_branch, f"local {ib}", move_ref)


def _merged_somewhere(repo: Path, nr: NestedRepo, feature_branch: str) -> bool:
    """``feature_branch`` is in the local integration branch or its remote-tracking one (nothing fetched)."""
    for ref in (f"refs/heads/{nr.integration_branch}", f"refs/remotes/{nr.remote}/{nr.integration_branch}"):
        if git_text(["rev-parse", "--verify", "--quiet", ref], repo) and \
                git_ok(["merge-base", "--is-ancestor", feature_branch, ref], repo)[0]:
            return True
    return False


def land_nested_branches(repo_root: Path, feature_branch: str) -> tuple[bool, str]:
    """Land ``feature_branch`` in every nested repository that has it, per entry's ``land``, before the main repository.

    ``(True, "")`` when each landed or had nothing to land (a repository
    without the branch); the first failure stops here, so the main repository
    has not moved. A configured path that is not a repository is a failure,
    not nothing to land: whether it held the leaf's work cannot be told.
    Repositories already landed stay landed: a re-run skips them. A
    ``land: manual`` repository whose integration branch (local or
    remote-tracking) lacks the branch is not-ok too, with the merge command to
    run there; once merged by hand, a re-run passes it.
    """
    from specy_road.nested_repos import _has_branch, is_repo_top, nested_repos   # noqa: PLC0415

    manual = []
    for nr in nested_repos(repo_root):
        repo = repo_root / nr.path
        if not is_repo_top(repo):
            err = (f"{repo} is not the top of a git repository (roadmap/git-workflow.yaml names it), so its "
                   "leaf branch cannot be landed; restore it or drop it from nested_repos")
        elif not _has_branch(repo, feature_branch):
            continue
        elif nr.land == "manual":
            if not _merged_somewhere(repo, nr, feature_branch):
                manual.append(f"  git -C {shlex.quote(str(repo))} merge --no-ff {shlex.quote(feature_branch)}   "
                              f"# with {nr.integration_branch} checked out there")
            continue
        elif nr.land == "local":
            err = _land_one_locally(repo, nr, feature_branch)
        else:
            err = _land_one(repo, nr, feature_branch)
        if err:
            return False, (f"nested repo {nr.path!r}: {err}. The main repository was not merged; "
                           "fix it there, then re-run (nested repos already landed are skipped)")
    if manual:
        return False, ("nested repos with land: manual hold the leaf's branch unmerged; the main repository was "
                       "not merged. Merge each by hand:\n" + "\n".join(manual) +
                       "\nre-run finish-this-task after merging")
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
    from specy_road.nested_repos import is_repo_top, nested_repos   # noqa: PLC0415

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
