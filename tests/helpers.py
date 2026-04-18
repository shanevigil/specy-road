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
    # Repo root so `import specy_road` works; bundled_scripts for flat imports.
    prefix = f"{REPO}{sep}{BUNDLED_SCRIPTS}"
    env["PYTHONPATH"] = prefix + (sep + prev if prev else "")
    return env
