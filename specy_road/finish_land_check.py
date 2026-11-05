"""Run the configured land check on the merge commit before finish pushes it.

Each leaf passes its own review, yet the combined tree that lands on the
integration branch is one nobody ran: two leaves can each be green and red
together, and a clean merge at finish lands a tree no reviewer saw. In merge
mode finish builds that merge commit locally and only then pushes, so the
project's gate (``land_check_cmd`` in ``roadmap/git-workflow.yaml``, or
``--land-check-cmd``) runs here, on exactly the commit that would become the
new tip, in a detached temporary worktree so neither checkout is touched.

Off when neither is set; pr mode never gets here, because there CI owns the
merge result.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

from specy_road.git_subprocess import git_code, git_ok
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.runtime_paths import project_prefix

#: How much of a failing check's output the error repeats.
TAIL_LINES = 20


def resolve_land_check_cmd(repo_root: Path, *, cli: str | None) -> str | None:
    """Land check command, or ``None`` when no check runs.

    CLI ``--land-check-cmd`` wins, and an empty one turns a configured check
    off for that run; then ``land_check_cmd`` in ``roadmap/git-workflow.yaml``.
    """
    cmd = cli
    if cmd is None:
        data, err = load_git_workflow_config(repo_root)
        cmd = (data or {}).get("land_check_cmd") if not err else None
    return (cmd or "").strip() or None


def _run_streaming(cmd: str, cwd: Path) -> tuple[int, list[str]]:
    """Run ``cmd`` through the shell, echoing its output; return (exit, last lines)."""
    tail: deque[str] = deque(maxlen=TAIL_LINES)
    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace",
    )
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()   # M15.40: under `2>&1 | tee`, ahead of whatever finish reports next
        tail.append(line.rstrip("\n"))
    return proc.wait(), list(tail)


def run_land_check(tree: Path, cmd: str) -> str | None:
    """Run ``cmd`` at the project root of a detached worktree of ``tree``'s HEAD.

    ``tree`` is the project root of the checkout holding the new merge commit;
    in the nested layout the command runs in ``<worktree>/<project prefix>``,
    just as it would from the project root of a normal checkout. The worktree
    is always removed. Returns ``None`` when the command exits 0, else the
    error to report. Only this worktree is removed: a repository-wide
    ``git worktree prune`` would also drop other checkouts' stale registrations.
    """
    _ok, sha = git_ok(["rev-parse", "HEAD"], tree)
    holder = Path(tempfile.mkdtemp(prefix="specy-road-land-check-"))
    worktree = holder / "tree"
    code, out = git_code(["worktree", "add", "--detach", str(worktree), sha], tree)
    if code != 0:
        shutil.rmtree(holder, ignore_errors=True)
        return f"could not create a worktree of {sha} for the land check: {out}"
    try:
        print(f"\nland check on {sha[:12]}: {cmd}")
        rc, tail = _run_streaming(cmd, worktree / project_prefix(tree))
    finally:
        git_code(["worktree", "remove", "--force", str(worktree)], tree)
        shutil.rmtree(holder, ignore_errors=True)
    if rc == 0:
        return None
    shown = "\n".join(f"    {line}" for line in tail) or "    (no output)"
    return (
        f"land check failed on merge commit {sha[:12]}; nothing was pushed.\n"
        f"  command: {cmd}\n"
        f"  exit code: {rc}\n"
        f"  last {TAIL_LINES} lines of its output:\n{shown}"
    )
