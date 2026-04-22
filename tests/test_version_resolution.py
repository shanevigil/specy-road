"""Tests for ``specy_road.__version__`` resolution policy.

Resolution order (see ``specy_road/__init__.py`` and
``.cursor/rules/026-release-version-tag-sync.mdc``):

1. Sibling ``pyproject.toml`` declaring ``[project] name = "specy-road"`` —
   used so editable checkouts match ``project.version`` even if installed
   metadata is stale.
2. ``importlib.metadata.version("specy-road")`` — for wheel-only installs.
3. ``"0.0.0+unknown"`` — last-resort sentinel (must not raise on import).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


def _import_specy_road_under_root(repo_root: Path) -> str:
    """Import ``specy_road`` from a synthetic checkout and return ``__version__``.

    Runs in a child interpreter so the parent's already-imported module is not
    reused; ``sys.path`` is set up so the synthetic ``specy_road/`` package
    wins over any installed copy.
    """
    pkg_root = repo_root / "specy_road"
    code = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(repo_root)!r})
        # Drop any pre-imported specy_road from the parent test process so the
        # synthetic checkout's __init__ runs fresh.
        for mod in [m for m in list(sys.modules) if m == 'specy_road' or m.startswith('specy_road.')]:
            sys.modules.pop(mod, None)
        import specy_road  # noqa: E402
        print(specy_road.__version__)
        """
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, (
        f"importing synthetic specy_road from {pkg_root} crashed:\n"
        f"--stdout--\n{r.stdout}\n--stderr--\n{r.stderr}"
    )
    return r.stdout.strip().splitlines()[-1]


def _stage_specy_road_package(target_repo_root: Path) -> None:
    """Copy the real ``specy_road`` package into a synthetic checkout root."""
    src = Path(__file__).resolve().parent.parent / "specy_road"
    dst = target_repo_root / "specy_road"
    shutil.copytree(src, dst)


def test_version_picks_up_sibling_pyproject(tmp_path: Path) -> None:
    """Sibling ``pyproject.toml`` declaring ``specy-road`` wins over metadata."""
    _stage_specy_road_package(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "specy-road"
            version = "9.9.9-test"
            """
        ),
        encoding="utf-8",
    )
    assert _import_specy_road_under_root(tmp_path) == "9.9.9-test"


def test_version_does_not_crash_on_malformed_pyproject(tmp_path: Path) -> None:
    """A broken ``pyproject.toml`` must not crash ``import specy_road``.

    Regression: ``_version_from_adjacent_pyproject`` previously caught only
    ``OSError`` — a malformed file raised ``tomllib.TOMLDecodeError``
    (subclass of ``ValueError``) and crashed import. The fallback chain
    (``importlib.metadata`` → ``"0.0.0+unknown"``) must take over instead.
    """
    _stage_specy_road_package(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "@@@ definitely not valid toml @@@\n[\n",
        encoding="utf-8",
    )
    v = _import_specy_road_under_root(tmp_path)
    # Either importlib.metadata for the installed editable build wins, or the
    # 0.0.0+unknown sentinel does. Both prove no crash.
    assert v
    assert v != "9.9.9-test"


def test_version_does_not_crash_on_pyproject_with_wrong_name(tmp_path: Path) -> None:
    """A ``pyproject.toml`` for a different project must be ignored cleanly."""
    _stage_specy_road_package(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "some-other-package"
            version = "1.2.3"
            """
        ),
        encoding="utf-8",
    )
    v = _import_specy_road_under_root(tmp_path)
    assert v != "1.2.3"
    assert v  # must not be empty
