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
from specy_road.managed_block import resolves_outside


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
    copy, whose single commit tracks everything. Returns whether a write was
    refused for a path that leads out of the project.
    """
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "roadmap.md"], cwd=tracked_in,
                             capture_output=True, check=False).returncode == 0
    files = [(DEFAULT_OUTPUT, render_digest(project), "specy-road digest")]
    if tracked:
        files.append(("roadmap.md", export_markdown(load_roadmap(project)["nodes"]), "specy-road export"))
    refused = wrote = False
    for rel, body, command in files:
        path = project / rel
        if path.is_file() and path.read_text(encoding="utf-8") == body:
            continue
        wrote = True
        if resolves_outside(project, path):
            print(f"refused {rel} (a symlink leads outside the project)")
            refused = True
            continue
        path.write_text(body, encoding="utf-8")
        print(f"{verb} {rel} ({command})")
    if not wrote:
        print("generated files already current")
    return refused
