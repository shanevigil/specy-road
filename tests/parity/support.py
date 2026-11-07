"""Shared pieces of the parity harness: a clean CLI environment, normalisation and golden files.

Goldens are data under ``tests/parity/golden/``. A test compares what the CLI prints today with
its golden; ``SPECY_ROAD_PARITY_REGEN=1`` rewrites the goldens instead (see README.md).
"""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

from tests.helpers import REPO

PARITY = Path(__file__).resolve().parent
GOLDEN = PARITY / "golden"
COMMAND_MAP = PARITY / "command_map.yaml"
REGEN = os.environ.get("SPECY_ROAD_PARITY_REGEN") == "1"

#: Harness and session variables that change what a command decides; a parity run sees none of them.
_SCRUBBED_PREFIXES = ("SPECY_ROAD_", "CLAUDE", "CODEX_", "CURSOR_")


def cli_env(**extra: str) -> dict[str, str]:
    """The environment a user's shell gives the CLI, minus this machine's harness and session."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(_SCRUBBED_PREFIXES)}
    env.update(PYTHONPATH=str(REPO), COLUMNS="100", **extra)
    return env


def run_cli(
    module: str, argv: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``python -m <module> <argv>`` as a user would, capturing its output."""
    return subprocess.run(
        [sys.executable, "-m", module, *argv],
        cwd=cwd,
        env=env or cli_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def _version_patterns() -> list[tuple[re.Pattern[str], str]]:
    from specy_road import __version__
    from specy_road.doc_links import docs_ref

    return [
        (re.compile(re.escape(docs_ref())), "<DOCS_REF>"),
        (re.compile(re.escape(__version__) + r"(\+[0-9A-Za-z.]+)?"), "<VERSION>"),
    ]


def normalise(text: str, paths: dict[Path | str, str] | None = None) -> str:
    """Replace machine paths, the running version and its docs tag with placeholders.

    ``paths`` maps further paths (a temp repo, say) to their placeholders; longer paths go first so
    a temp repo inside the home directory is not half-replaced.
    """
    subs = {**(paths or {}), REPO: "<REPO>", sys.prefix: "<PREFIX>", Path.home(): "<HOME>"}
    for path, label in sorted(subs.items(), key=lambda kv: -len(str(kv[0]))):
        text = text.replace(str(path), label)
    for pattern, label in _version_patterns():
        text = pattern.sub(label, text)
    return text


def transcript(
    argv: list[str],
    result: subprocess.CompletedProcess[str],
    paths: dict[Path | str, str] | None = None,
) -> str:
    """One command's exit code and output, normalised, as a golden file stores it."""
    return normalise(
        f"$ {' '.join(argv)}\nexit: {result.returncode}\n--- stdout ---\n{result.stdout}"
        f"--- stderr ---\n{result.stderr}",
        paths,
    )


def words(text: str) -> str:
    """``text`` with every whitespace run collapsed to one space.

    Help text is compared this way because argparse reflows a paragraph when a URL in it changes
    length, and the docs tag in those URLs follows the version (``v0.3.1-rc2`` to ``v0.3.1``): a
    version bump must not read as a changed transcript, while any changed word still does.
    """
    return " ".join(text.split())


def check_golden(path: Path, actual: str, compare: Callable[[str], str] = str) -> None:
    """Fail when ``actual`` differs from the golden at ``path`` (both passed through ``compare``).

    Under regeneration, write ``actual`` instead.
    """
    if REGEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    assert path.is_file(), f"no golden {path.relative_to(REPO)}; run with SPECY_ROAD_PARITY_REGEN=1"
    expected = path.read_text(encoding="utf-8")
    assert compare(actual) == compare(expected), (
        f"{path.relative_to(REPO)} differs from today's output"
    )


def command_map_rows() -> list[dict]:
    """Rows of command_map.yaml: each authorises one changed invocation (old -> new, allowed)."""
    doc = yaml.safe_load(COMMAND_MAP.read_text(encoding="utf-8")) or {}
    return list(doc.get("rows") or [])


def mapped(key: str, rows: list[dict]) -> bool:
    """True when ``key`` (``specy-road branches prune``) or a command above it is in a map row.

    A row's invocation may carry options (``specy-road doctor --prune``); its command words decide.
    """
    names = set()
    for row in rows:
        for side in ("old", "new"):
            words = str(row.get(side) or "").split()
            command = " ".join(itertools.takewhile(lambda w: not w.startswith("-"), words))
            if command:
                names.add(command)
    return any(key == n or key.startswith(n + " ") for n in names)
