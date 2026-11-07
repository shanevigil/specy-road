"""Shared pieces of the parity harness: a clean CLI environment, normalisation and golden files.

Goldens are data under ``tests/parity/golden/``. A test compares what the CLI prints today with
its golden; ``SPECY_ROAD_PARITY_REGEN=1`` rewrites the goldens instead (see README.md).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from tests.helpers import REPO

PARITY = Path(__file__).resolve().parent
GOLDEN = PARITY / "golden"
COMMAND_MAP = PARITY / "command_map.yaml"
#: ``1`` rewrites every golden (a new baseline); ``missing`` writes only goldens that do not exist
#: yet (a command a command_map.yaml row adds) and leaves every other golden as it is.
REGEN_MODE = os.environ.get("SPECY_ROAD_PARITY_REGEN", "")
REGEN = REGEN_MODE == "1"

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
        # Whole tokens only: at 0.3.1, "0.3.1rc1" in prose is another version, not this one.
        (re.compile(rf"(?<![\w.-]){re.escape(docs_ref())}(?![\w.-])"), "<DOCS_REF>"),
        (
            re.compile(rf"(?<![\w.]){re.escape(__version__)}(\+[0-9A-Za-z.]+)?(?![\w-])"),
            "<VERSION>",
        ),
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


def help_paragraphs(text: str) -> list[str]:
    """``text`` split into argparse paragraphs.

    A paragraph ends at a blank line, and a new one starts at each line indented exactly two
    spaces (an option, positional or subcommand entry); deeper-indented lines continue the entry
    above them, and consecutive unindented lines (a description) stay together.
    """
    paragraphs: list[list[str]] = []
    for line in text.split("\n"):
        starts = not paragraphs or not line.strip() or not paragraphs[-1][-1].strip()
        starts = starts or (len(line) - len(line.lstrip(" ")) == 2)
        if starts:
            paragraphs.append([line])
        else:
            paragraphs[-1].append(line)
    return ["\n".join(p) for p in paragraphs]


def help_text(text: str) -> str:
    """The form help transcripts are compared in: byte for byte, with one bounded exception.

    A paragraph (:func:`help_paragraphs`) holding a toolkit docs URL (``<DOCS_REF>``) has its
    whitespace runs collapsed to one space. The docs tag follows the version (``v0.3.1-rc2`` to
    ``v0.3.1``), so a version bump changes the URL's length and argparse reflows that paragraph.
    Limit: whitespace-only drift inside such a paragraph passes; a changed word still fails, and
    every other paragraph must match exactly.
    """
    return "\n".join(" ".join(p.split()) if "<DOCS_REF>" in p else p for p in help_paragraphs(text))


def check_golden(path: Path, actual: str, compare: Callable[[str], str] = str) -> None:
    """Fail when ``actual`` differs from the golden at ``path`` (both passed through ``compare``).

    Under regeneration, write ``actual`` instead: always for ``1``, only if absent for ``missing``.
    """
    if REGEN or (REGEN_MODE == "missing" and not path.is_file()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    assert path.is_file(), (
        f"no golden {path.relative_to(REPO)}; run with SPECY_ROAD_PARITY_REGEN=missing"
    )
    expected = path.read_text(encoding="utf-8")
    assert compare(actual) == compare(expected), (
        f"{path.relative_to(REPO)} differs from today's output"
    )
