"""``specy-road upgrade``: the generated files it rewrites, and the environment of its scratch copy.

Split out of ``upgrade.py`` to keep that module under its line cap.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from specy_road.bundled_scripts.export_roadmap_md import export_markdown
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.ignore_report import scratch_git_env
from specy_road import safe_write
from specy_road.managed_block import refused_link


@contextlib.contextmanager
def scratch_environ():
    """The copy is a scratch repository: validate's own git calls on it must not follow the caller's ``GIT_DIR``."""
    saved, env = os.environ.copy(), scratch_git_env()
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def regenerate(project: Path, tracked_in: Path, verb: str) -> bool:
    """Write each drifted generated file into ``project``: the digest, and ``roadmap.md`` if ``tracked_in`` tracks it.

    ``tracked_in`` is the checkout's project: a dry run renders and writes into its
    copy, whose single commit tracks everything. A path the safe-write rule
    refuses (a symlink of any kind) is refused before it is read; the rest are compared as bytes, so a
    file that is not UTF-8 is drifted, not an error. Returns whether a path was refused.
    """
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "roadmap.md"], cwd=tracked_in,
                             capture_output=True, check=False).returncode == 0
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
