"""Shared paths for subprocess script invocations."""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUNDLED_SCRIPTS = REPO / "specy_road" / "bundled_scripts"
DOGFOOD = REPO / "tests" / "fixtures" / "specy_road_dogfood"
SCHEMAS = DOGFOOD / "schemas"


def script_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    sep = os.pathsep
    prev = env.get("PYTHONPATH", "")
    # Repo root so `import specy_road` works from a source checkout.
    env["PYTHONPATH"] = str(REPO) + (sep + prev if prev else "")
    return env


def sorted_diff_paths_project_relative(project: Path, base: str, tip: str) -> list[str]:
    """Paths ``git diff base...tip`` touches, in the same project-relative form as review-packet."""
    from specy_road import git_changed_paths, git_subprocess, runtime_paths

    top = git_subprocess.git_root(project) or project
    prefix = runtime_paths.project_prefix(project)
    raw = git_changed_paths.diff_paths(top, f"{base}...{tip}") or []
    return sorted(runtime_paths.rebase_to_project(path, prefix) or path for path in raw)
