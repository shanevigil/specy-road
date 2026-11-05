"""``env_setup`` in ``roadmap/git-workflow.yaml``: the environment a new leaf worktree gets.

A linked worktree holds tracked files only, so it starts with no virtual environment and none of the ignored
files (``.python-version``, ``.env``) the main checkout has. ``copy`` names files copied from the main
checkout's project root to the same project-relative path in the worktree (``{from, to}`` to rename one);
``link`` names paths symlinked from the main checkout into the same place (``node_modules``, ``.venv``), each
added to ``info/exclude`` (:func:`exclude_links`); ``cmd`` then runs at the worktree's project root. ``do-next-available-task --worktree`` and ``worker delegate``
run both once, when they create the worktree; ``doctor`` runs ``cmd`` in the main checkout.

A copy path may climb with ``../`` from a nested project root to its git root and no further: a source
outside the main checkout's git root, or a target outside the leaf's worktree, is refused
(:func:`bounded_path`), since the schema can only forbid a leading ``/``.

Split from :mod:`specy_road.git_workflow_config` for the file limit.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.review_files import reviews_root
from specy_road.runtime_paths import git_path


class EnvSetupError(Exception):
    """A copy or the command failed; the message carries the command's output."""


def env_setup_config(repo_root: Path) -> dict[str, Any] | None:
    """``env_setup`` from ``roadmap/git-workflow.yaml``, or ``None`` when unset or the file is unreadable."""
    data, err = load_git_workflow_config(repo_root)
    return None if err else (data or {}).get("env_setup") or None


def copy_pairs(conf: dict[str, Any]) -> list[tuple[str, str]]:
    """``(from, to)`` per ``copy`` item: a bare path is copied to the same path."""
    return [(c, c) if isinstance(c, str) else (c["from"], c["to"]) for c in conf.get("copy") or []]


def link_paths(conf: dict[str, Any] | None) -> list[str]:
    """``env_setup.link``: project-relative paths symlinked from the main checkout."""
    return list((conf or {}).get("link") or [])


def linked_status_paths(repo_root: Path, leaf_root: Path) -> set[str]:
    """Each ``link`` path that is, in ``leaf_root``, a symlink to its main-checkout source, as ``git status``
    names it (git-root-relative, no slash), for ``worker delegate``'s clean-tree check: a symlink made by
    hand before the exclude existed is not work. A file or directory of the same name still counts."""
    main = main_project_root(repo_root)
    top = git_top(leaf_root)
    out = set()
    for rel in link_paths(env_setup_config(main)):
        try:
            source = bounded_path(main, rel, git_top(main), rel, "the main checkout", "link")
            target = link_target(leaf_root, rel, top)
        except EnvSetupError:
            continue
        if target.is_symlink() and target.resolve() == source:
            out.add(target.relative_to(top).as_posix())
    return out


def link_target(leaf_root: Path, rel: str, leaf_top: Path) -> Path:
    """Where the link ``rel`` goes in the leaf: its parent resolved (a symlinked directory on the way is
    followed, so it cannot carry the link out) and bounded by ``leaf_top``; the final component is not
    followed, so an existing or dangling link there is still seen and refused. A newline is refused too:
    no ``info/exclude`` line can name it."""
    path = leaf_root / rel
    target = path.parent.resolve() / path.name
    if path.name == ".." or "\n" in rel or "\r" in rel or not target.is_relative_to(leaf_top) or target == leaf_top:
        raise EnvSetupError(f"env_setup: cannot link to {rel!r}: {target} is not a path inside the leaf worktree {leaf_top}")
    return target


def exclude_pattern(rel: str) -> str:
    """``rel`` as an anchored ``info/exclude`` line matching that one name: ``\\ * ? [ ] ! #`` and trailing
    spaces are escaped, since git reads them as pattern syntax (``env[1]`` would match ``env1``, not itself).
    The leading ``/`` means no line starts with ``!`` or ``#``; escaping them anyway keeps each one literal."""
    body = re.sub(r"([\\*?\[\]!#])", r"\\\1", rel)
    stripped = body.rstrip(" ")
    return "/" + stripped + "\\ " * (len(body) - len(stripped))


def info_exclude_lines(text: str) -> list[str]:
    """Each ``info/exclude`` record, split on LF only (git's line delimiter).

    ``str.splitlines()`` also splits on vertical tab and other Unicode line breaks, which are legal in
    path names and must stay part of one pattern."""
    if not text:
        return []
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return parts


def exclude_links(leaf_top: Path, targets: list[Path]) -> None:
    """Add an anchored ``/<path>`` line per symlink to the exclude file git reads in ``leaf_top``.

    Git reads ``info/exclude`` from the **common** git dir, so the line holds in every worktree of the
    repository, the main checkout included (where it matches the real directory, already ignored). A
    directory-only pattern such as ``node_modules/`` never matches a symlink, which git sees as a file.
    Existing lines are never rewritten; new patterns are appended only."""
    exclude = git_path(["rev-parse", "--path-format=absolute", "--git-path", "info/exclude"], leaf_top)
    if exclude is None:
        raise EnvSetupError(f"env_setup: cannot find the git exclude file for {leaf_top}")
    have = info_exclude_lines(exclude.read_text(encoding="utf-8")) if exclude.is_file() else []
    lines = [exclude_pattern(t.relative_to(leaf_top).as_posix()) for t in targets]
    new = [ln for ln in dict.fromkeys(lines) if ln not in have]
    if new:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as fh:
            for ln in new:
                fh.write(f"{ln}\n")


def run_setup_cmd(cmd: str, cwd: Path) -> tuple[int, str]:
    """``(exit code, stdout and stderr together)`` of ``cmd`` run by the shell in ``cwd``."""
    r = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE,  # noqa: S602 — adopter's own config
                       stderr=subprocess.STDOUT, text=True, check=False)
    return r.returncode, r.stdout or ""


def git_top(root: Path) -> Path:
    """The top of the worktree holding ``root`` (the nearest directory with a ``.git``), else ``root`` itself."""
    here = Path(root).resolve()
    return next((p for p in (here, *here.parents) if (p / ".git").exists()), here)


def bounded_path(root: Path, rel: str, top: Path, entry: str, where: str, verb: str = "copy") -> Path:
    """``root / rel`` resolved, which must stay under ``top``; else :class:`EnvSetupError` naming the ``entry``."""
    path = (root / rel).resolve()
    if not path.is_relative_to(top):
        raise EnvSetupError(f"env_setup: cannot {verb} {entry}: {rel!r} is {path}, outside {where} {top} "
                            "('../' may reach the git root only)")
    return path


def copy_source(main_root: Path, src: str) -> Path:
    """``src`` under the main checkout's project root ``main_root``, which it must not leave by its git root."""
    return bounded_path(main_root, src, git_top(main_root), f"from {src!r}", "the main checkout")


def main_project_root(repo_root: Path) -> Path:
    """The main checkout's project root, whichever checkout ``repo_root`` is (``reviews_root`` is the one resolver)."""
    return reviews_root(repo_root).parents[1]   # <main project root>/work/reviews


def link_into(conf: dict[str, Any], repo_root: Path, leaf_root: Path, keep: str) -> list[str]:
    """Symlink each ``env_setup.link`` path from the main checkout's project root ``repo_root`` into
    ``leaf_root`` and exclude the links (:func:`exclude_links`); one line per link. ``keep`` ends each error."""
    leaf_top, done, links = git_top(leaf_root), [], []
    for rel in link_paths(conf):
        try:
            source = bounded_path(repo_root, rel, git_top(repo_root), f"from {rel!r}", "the main checkout", "link")
            target = link_target(leaf_root, rel, leaf_top)
        except EnvSetupError as e:
            raise EnvSetupError(str(e) + keep) from None
        if not source.exists():
            raise EnvSetupError(f"env_setup: cannot link {rel}: {source} does not exist." + keep)
        if target.is_symlink() or target.exists():
            raise EnvSetupError(f"env_setup: cannot link {rel}: {target} already exists in the worktree." + keep)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=source.is_dir())
        links.append(target)
        done.append(f"linked {rel}")
    if links:
        exclude_links(leaf_top, links)
    return done


def setup_worktree_env(repo_root: Path, leaf_root: Path) -> list[str]:
    """Copy ``env_setup.copy`` and symlink ``env_setup.link`` from the main checkout into ``leaf_root``, then
    run ``env_setup.cmd`` there.

    ``repo_root`` is the project root of the checkout running the command, which may be a linked worktree
    (``worker delegate``); the setting and every copy source come from the main checkout's project root,
    where the ignored files live. ``leaf_root`` is the project root in the new worktree. Returns one line
    per step done (none when ``env_setup`` is unset); raises :class:`EnvSetupError` at the first failure.
    The worktree stays either way, and is never set up again by the commands that created it.
    """
    repo_root = main_project_root(repo_root)
    conf = env_setup_config(repo_root)
    if not conf:
        return []
    keep = (f"\n  {leaf_root} stays as it is: fix the cause, finish the setup there by hand, "
            "then continue the leaf (an existing worktree is not set up again).")
    done = []
    leaf_top = git_top(leaf_root)
    for src, dest in copy_pairs(conf):
        try:
            source = copy_source(repo_root, src)
            target = bounded_path(leaf_root, dest, leaf_top, f"to {dest!r}", "the leaf worktree")
        except EnvSetupError as e:
            raise EnvSetupError(str(e) + keep) from None
        if not source.is_file():
            raise EnvSetupError(f"env_setup: cannot copy {src}: {source} is not a file." + keep)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
        done.append(f"copied {src}" + (f" to {dest}" if dest != src else ""))
    done += link_into(conf, repo_root, leaf_root, keep)
    cmd = conf.get("cmd")
    if cmd:
        code, out = run_setup_cmd(cmd, leaf_root)
        if code:
            raise EnvSetupError(f"env_setup failed in {leaf_root} (exit {code}): {cmd}\n{out.rstrip()}" + keep)
        done.append(f"ran {cmd}")
    return done
