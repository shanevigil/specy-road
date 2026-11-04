"""``env_setup`` in ``roadmap/git-workflow.yaml``: the environment a new leaf worktree gets.

A linked worktree holds tracked files only, so it starts with no virtual environment and none of the ignored
files (``.python-version``, ``.env``) the main checkout has. ``copy`` names files copied from the main
checkout's project root to the same project-relative path in the worktree (``{from, to}`` to rename one);
``cmd`` then runs at the worktree's project root. ``do-next-available-task --worktree`` and ``worker delegate``
run both once, when they create the worktree; ``doctor`` runs ``cmd`` in the main checkout.

Split from :mod:`specy_road.git_workflow_config` for the file limit.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.review_files import reviews_root


class EnvSetupError(Exception):
    """A copy or the command failed; the message carries the command's output."""


def env_setup_config(repo_root: Path) -> dict[str, Any] | None:
    """``env_setup`` from ``roadmap/git-workflow.yaml``, or ``None`` when unset or the file is unreadable."""
    data, err = load_git_workflow_config(repo_root)
    return None if err else (data or {}).get("env_setup") or None


def copy_pairs(conf: dict[str, Any]) -> list[tuple[str, str]]:
    """``(from, to)`` per ``copy`` item: a bare path is copied to the same path."""
    return [(c, c) if isinstance(c, str) else (c["from"], c["to"]) for c in conf.get("copy") or []]


def run_setup_cmd(cmd: str, cwd: Path) -> tuple[int, str]:
    """``(exit code, stdout and stderr together)`` of ``cmd`` run by the shell in ``cwd``."""
    r = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE,  # noqa: S602 — adopter's own config
                       stderr=subprocess.STDOUT, text=True, check=False)
    return r.returncode, r.stdout or ""


def main_project_root(repo_root: Path) -> Path:
    """The main checkout's project root, whichever checkout ``repo_root`` is (``reviews_root`` is the one resolver)."""
    return reviews_root(repo_root).parents[1]   # <main project root>/work/reviews


def setup_worktree_env(repo_root: Path, leaf_root: Path) -> list[str]:
    """Copy ``env_setup.copy`` from the main checkout into ``leaf_root``, then run ``env_setup.cmd`` there.

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
    for src, dest in copy_pairs(conf):
        if not (repo_root / src).is_file():
            raise EnvSetupError(f"env_setup: cannot copy {src}: {repo_root / src} is not a file." + keep)
        (leaf_root / dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(repo_root / src, leaf_root / dest)
        done.append(f"copied {src}" + (f" to {dest}" if dest != src else ""))
    cmd = conf.get("cmd")
    if cmd:
        code, out = run_setup_cmd(cmd, leaf_root)
        if code:
            raise EnvSetupError(f"env_setup failed in {leaf_root} (exit {code}): {cmd}\n{out.rstrip()}" + keep)
        done.append(f"ran {cmd}")
    return done
