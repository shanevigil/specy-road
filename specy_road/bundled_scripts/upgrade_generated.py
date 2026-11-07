"""``specy-road upgrade``: the generated files it rewrites, and the environment of its scratch copy.

Split out of ``upgrade.py`` to keep that module under its line cap.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from specy_road import git_subprocess
from specy_road.bundled_scripts.export_roadmap_md import export_markdown
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.ignore_report import isolate_git, scratch_git_env
from specy_road import safe_write
from specy_road.managed_block import refused_link

COPY = "the temporary copy"


class GitFailed(Exception):
    """A git call upgrade depends on failed; ``run_upgrade`` prints it and returns 2."""


def checked(r: git_subprocess.GitResult, command: str, where: str = COPY, ok: tuple[int, ...] = (0,)) -> None:
    """Raise :class:`GitFailed` unless ``r`` exited with a code in ``ok``: every git call upgrade depends on ends here."""
    if r.code not in ok:
        lines = r.message.splitlines()
        reason = "timed out" if r.failure == "timeout" else lines[-1] if lines else f"exit {r.code}"
        raise GitFailed(f"git {command} failed in {where} ({reason})")


@contextlib.contextmanager
def scratch_environ(tmp: Path):
    """The dry run's environment: no ``GIT_`` variable and no global or system git config, for every git call on a copy.

    Yields the caller's environment with ``GIT_`` variables dropped and nothing
    else changed, for the one git call that reads the caller's own checkout.
    """
    saved, caller, env = os.environ.copy(), scratch_git_env(), scratch_git_env(tmp)
    os.environ.clear()
    os.environ.update(env)
    isolate_git(tmp)
    try:
        yield caller
    finally:
        isolate_git(None)
        os.environ.clear()
        os.environ.update(saved)


def regenerate(project: Path, tracked_in: Path, verb: str, caller_env: dict[str, str]) -> bool:
    """Write each drifted generated file into ``project``: the digest, and ``roadmap.md`` if ``tracked_in`` tracks it.

    ``tracked_in`` is the checkout's project: a dry run renders and writes into its
    copy, whose single commit tracks everything. A path the safe-write rule
    refuses (a symlink of any kind) is refused before it is read; the rest are compared as bytes, so a
    file that is not UTF-8 is drifted, not an error. Returns whether a path was refused.

    The question goes to the caller's checkout, under their own config (``caller_env``,
    their environment without ``GIT_`` variables), with only the command-running
    ``core.fsmonitor`` off. Exit 1 is untracked; any other failure raises
    :class:`GitFailed` before a file is written.
    """
    r = git_subprocess.run(["-c", "core.fsmonitor=false", "ls-files", "--error-unmatch", "roadmap.md"], tracked_in,
                           env=caller_env)
    checked(r, "ls-files", "the checkout" if project == tracked_in else COPY, ok=(0, 1))
    tracked = r.ok
    files = [(DEFAULT_OUTPUT, render_digest(project), "specy-road digest")]
    if tracked:
        files.append(("roadmap.md", export_markdown(load_roadmap(project)["nodes"]), "specy-road export"))
    refused = wrote = False
    for rel, body, command in files:
        path = project / rel
        if why := refused_link(project, path):   # checked before any read: a link is never opened
            print(f"refused {rel} ({why})")
            refused = wrote = True
            continue
        if path.is_file() and path.read_bytes() == body.encode("utf-8"):
            continue
        wrote = True
        safe_write.write(project, path, body)
        print(f"{verb} {rel} ({command})")
    if not wrote:
        print("generated files already current")
    return refused
