"""What ``specy-road worktree prune`` deletes, and the scan of it for other repositories.

:func:`deletions` is the single list of what :func:`specy_road.worktree_prune.remove` deletes, step by
step, with every directory each step takes: a full clone with its ``.git``, a linked worktree with its
administrative directory. :func:`walk_foreign` walks exactly those directories for another repository's
worktree, checkout or bare clone, and :func:`foreign_refusal` says why one refuses. Every git call here and
in ``worktree_prune`` reads bytes (:func:`git_run`), and every command shown is built with :func:`cmd`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from specy_road.git_subprocess import DEFAULT_TIMEOUT


# Every git call in worktree prune goes through git_run, which reads bytes: git prints paths (its own output,
# and in messages), and text mode's universal newlines and stripping would turn a '\\r' in one into '\\n'
# or drop an edge space. Paths are decoded with os.fsdecode only, which round-trips any name.
def git_run(args: list[str], d: Path) -> tuple[int, bytes, str]:
    """``(exit code, stdout bytes, message)``: the message is stderr (or stdout), decoded for display."""
    try:
        r = subprocess.run(["git", *args], cwd=d, capture_output=True, timeout=DEFAULT_TIMEOUT, check=False)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return -1, b"", str(e)
    return r.returncode, r.stdout, os.fsdecode(r.stderr or r.stdout).strip()


def git_out(args: list[str], d: Path) -> str | None:
    """``git <args>``'s stdout in ``d`` less its final newline, or ``None`` on failure."""
    code, out, _msg = git_run(args, d)
    return None if code else os.fsdecode(out.removesuffix(b"\n"))


def git_path(args: list[str], d: Path) -> Path | None:
    """The one path ``git <args>`` prints in ``d``, or ``None`` on failure or none printed."""
    out = git_out(args, d)
    return Path(out).resolve() if out else None


def cmd(*argv: object) -> str:
    """A command to show: built from its argument list, each one shell-quoted, never formatted."""
    return f"`{shlex.join(str(a) for a in argv)}`"


def common_dir(d: Path) -> Path | None:
    return git_path(["rev-parse", "--path-format=absolute", "--git-common-dir"], d)


def is_repo_top(d: Path) -> bool:
    """``d`` is the top of a git worktree (its own repository, not a directory of an enclosing one)."""
    return d.is_dir() and git_path(["rev-parse", "--show-toplevel"], d) == d.resolve()


# The entries git keeps in a worktree's administrative directory (<common dir>/worktrees/<name>): only
# these may make that directory itself look like a repository. Anything below it is scanned like the rest.
_ADMIN_OWN = frozenset({"HEAD", "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD",
                        "AUTO_MERGE", "BISECT_LOG", "gitdir", "commondir", "index", "locked", "config.worktree",
                        "logs", "refs", "modules", "rebase-merge", "rebase-apply", "sequencer"})
_TOP_OWN = frozenset({".git"})                       # a worktree's or clone's own .git entry
_GIT_DIR_OWN = frozenset({"HEAD", "objects", "refs"})   # a full clone's own .git directory, laid out as a repository


@dataclass(frozen=True)
class Deletion:
    """One step of ``worktree_prune.remove``: ``git -C <owner> worktree remove --force <path>`` when ``owner`` is set,
    else ``shutil.rmtree(<path>)``; and every directory that step deletes with all it holds, each with the
    entries that are its own git files (exempt in that directory itself, never below it). Branches and
    other refs in the owner's common directory are not files of the step and are not deleted."""
    path: Path
    owner: Path | None
    dirs: tuple[tuple[Path, frozenset[str]], ...]


def deletions(nested: list[tuple[Path, Path, bool]], main: Path, worktree: Path) -> tuple[list[Deletion], list[str]]:
    """Everything ``worktree_prune.remove`` deletes for a plan's ``nested`` repos (``(main copy, dir,
    linked)``) and its leaf ``worktree`` of ``main``, step by step, and why any of it cannot be known: the single
    source both the foreign-repository scan and :func:`remove` read.

    A full clone is its directory, its ``.git`` directory included. A linked worktree (each configured
    one, then the leaf) is its directory and its administrative directory, which ``git worktree remove``
    deletes too: read from its ``.git`` file (``--absolute-git-dir``), and only accepted where git keeps
    one, ``<common dir>/worktrees/<name>``.
    """
    steps, problems = [], []
    for src, d, linked in [*nested, (main, worktree, True)]:
        if not linked:
            steps.append(Deletion(d, None, ((d, _TOP_OWN), (d / ".git", _GIT_DIR_OWN))))
            continue
        admin, common = git_path(["rev-parse", "--absolute-git-dir"], d), common_dir(d)
        if admin is None or common is None or admin.parent != common / "worktrees":
            problems.append(f"cannot find {d}'s administrative directory under its repository's worktrees/ "
                            f"(git dir {admin}, common dir {common}); removal would delete it unchecked")
            steps.append(Deletion(d, src, ((d, _TOP_OWN),)))
        else:
            steps.append(Deletion(d, src, ((d, _TOP_OWN), (admin, _ADMIN_OWN))))
    return steps, problems


def walk_foreign(steps: list[Deletion]) -> tuple[list[Path], list[str]]:
    """``(foreign, unreadable)``: every directory in or below those ``steps`` delete that holds a ``.git``
    entry (file, directory or link) or is laid out as a bare repository, unless it is one of their
    directories and what makes it look so is among its own git files; and each directory that could
    not be read, which refuses too, since what is in it is unknown.

    Each directory is walked whole (one inside another once), the filesystem itself, not git's view of
    it: a clean tracked directory, or a submodule at its recorded commit, is in no status output. Links
    are never followed (removal deletes the link, not its target). A found repository is not descended
    into: it refuses already.
    """
    found, unreadable = [], []
    own = {d: names for step in steps for d, names in step.dirs}

    def unread(e: OSError) -> None:
        unreadable.append(f"cannot read {e.filename}: {e.strerror}; removal would delete what it holds unchecked")

    real = [r.resolve() for r in own]
    for root, rr in zip(own, real):
        if any(o != rr and rr.is_relative_to(o) for o in real):
            continue   # walked with the directory that holds it
        for top, dirs, files in os.walk(root, onerror=unread):
            d = Path(top)
            looks = {".git"} & {*dirs, *files}
            if "HEAD" in files and {"objects", "refs"} <= set(dirs):
                looks |= {"HEAD", "objects", "refs"}
            if looks and not looks <= own.get(d, frozenset()):
                found.append(d)
                dirs.clear()
    return sorted(set(found)), unreadable


def head_state(d: Path) -> tuple[str, str | None]:
    """``(what HEAD is on, its commit or None)`` in ``d``: the branch it names, born or not (``symbolic-ref``
    names an unborn branch too, where ``rev-parse --abbrev-ref`` fails), marked when it has no commit yet;
    else ``HEAD (detached at <sha>)``; else ``an unreadable HEAD``."""
    sha = git_out(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], d) or None
    code, out, _msg = git_run(["symbolic-ref", "-q", "--short", "HEAD"], d)
    if not code and out.strip():
        name = os.fsdecode(out.removesuffix(b"\n"))
        return (name if sha else f"{name} (no commits yet)"), sha
    return (f"HEAD (detached at {sha[:12]})" if sha else "an unreadable HEAD"), sha


def foreign_refusal(wt: Path, d: Path) -> str:
    """Why ``d``, another repository's linked worktree, checkout (a ``.git`` directory, or a ``.git`` file
    naming its own git directory, as a submodule's does) or bare repository, refuses."""
    common = common_dir(d)
    git_dir = git_path(["rev-parse", "--absolute-git-dir"], d)
    linked = bool(common and git_dir) and git_dir != common
    bare = not (d / ".git").exists() and not os.path.islink(d / ".git")
    if linked:
        repo = common.parent if common.name == ".git" else common
    else:
        repo = d if bare or (d / ".git").is_dir() else (common or d)
    branch, sha = head_state(d)
    upstream = git_out(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], d) if sha else None
    span = ["@{u}..HEAD"] if upstream else ["HEAD", "--not", "--remotes"]
    log = git_out(["log", "--oneline", *span], d) if sha else ""   # every one: removal would lose them all
    lacks = f"its upstream {upstream}" if upstream else "every remote-tracking ref"
    if log is None:
        commits = f"commits {lacks} lacks cannot be listed"
    else:
        lines = log.split("\n") if log else []
        commits = f"commits {lacks} lacks: {'; '.join(lines)}" if lines else f"no commits {lacks} lacks"
    kind, step = (("linked worktree", cmd("git", "-C", repo, "worktree", "remove", d)) if linked
                  else ("bare clone" if bare else "checkout", "move it out of the worktree"))
    shown = d.relative_to(wt).as_posix() if d.is_relative_to(wt) else str(d)
    return (f"{shown}/ is a {kind} of another repository, {repo}, on {branch}; "
            f"{commits}; removal would delete it: land or push those commits, then {step}")
