"""Subprocess pytest runs prove the fixture-pollution guard (M9.2 A1–A3)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers import REPO, script_subprocess_env

_GUARD = REPO / "tests" / "fixture_guard.py"
_MINI_CONFTEST = '''\
"""Wires fixture_guard for subprocess integration tests."""
from __future__ import annotations

import pytest

from tests.fixture_guard import (
    exit_if_ignored_fixtures_present,
    fail_if_fixtures_status_changed,
    record_session_start,
)
from tests.helpers import REPO


def pytest_sessionstart(session: pytest.Session) -> None:
    record_session_start(session, REPO)
    exit_if_ignored_fixtures_present(REPO)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    fail_if_fixtures_status_changed(session, REPO)
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _mini_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "tests" / "fixtures" / "sample").mkdir(parents=True)
    # A tracked fixture file, as in the dogfood tree: git then names the ignored
    # directory inside it instead of collapsing to ``tests/fixtures/``.
    (root / "tests" / "fixtures" / "sample" / "tracked.txt").write_text("x\n", encoding="utf-8")
    # A tracked name git must quote; the A2 test renames it during the run.
    (root / "tests" / "fixtures" / "sample" / "old -> src.txt").write_text("y\n", encoding="utf-8")
    (root / ".gitignore").write_text("**/.specyrd/cache/\n")
    shutil.copy(_GUARD, root / "tests" / "fixture_guard.py")
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "conftest.py").write_text(_MINI_CONFTEST)
    (root / "tests" / "helpers.py").write_text(
        "from pathlib import Path\n\n"
        f"REPO = Path({repr(str(root))})\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    return root


def _run_pytest(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = script_subprocess_env()
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + prev if prev else "")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *extra],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
    )


def test_refuses_start_when_ignored_cache_sits_in_fixtures(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    cache = root / "tests" / "fixtures" / "sample" / ".specyrd" / "cache"
    cache.mkdir(parents=True)
    (cache / "index.json").write_text("{}", encoding="utf-8")

    proc = _run_pytest(root)
    combined = proc.stdout + proc.stderr

    assert proc.returncode != 0
    assert "  tests/fixtures/sample/.specyrd/\n" in combined
    assert "git clean -fdX tests/fixtures" in combined
    assert "1 passed" not in combined
    assert "1 failed" not in combined


def test_fails_session_when_a_run_pollutes_the_fixture_tree(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)
    (root / "tests" / "test_pollutes.py").write_text(
        "import subprocess\n"
        "from pathlib import Path\n\n"
        "def test_leaves_cache():\n"
        "    p = Path(__file__).resolve().parent / 'fixtures' / 'sample' / '.specyrd' / 'cache'\n"
        "    p.mkdir(parents=True, exist_ok=True)\n"
        "    (p / 'x').write_text('pollution')\n"
        "    # An ordinary filename containing ' -> ' is not a rename record.\n"
        "    (p.parents[2] / 'a -> b.txt').write_text('pollution')\n"
        "    # A rename whose quoted source contains ' -> ' must report the destination.\n"
        "    subprocess.run(['git', 'mv', 'tests/fixtures/sample/old -> src.txt',\n"
        "                    'tests/fixtures/sample/new.txt'], cwd=p.parents[4], check=True)\n",
        encoding="utf-8",
    )

    proc = _run_pytest(root)
    combined = proc.stdout + proc.stderr

    assert proc.returncode != 0
    assert "tests/fixtures git status changed during the run" in combined
    assert '  "tests/fixtures/a -> b.txt"\n' in combined
    assert "  tests/fixtures/sample/.specyrd/\n" in combined
    assert "  tests/fixtures/sample/new.txt\n" in combined
    assert 'src.txt"' not in combined


def test_clean_fixture_tree_leaves_exit_status_and_output_unchanged(tmp_path: Path) -> None:
    root = _mini_repo(tmp_path)

    proc = _run_pytest(root)
    combined = proc.stdout + proc.stderr

    assert proc.returncode == 0
    assert "git clean -fdX tests/fixtures" not in combined
    assert "refused to start" not in combined
    assert "changed during the run" not in combined
    assert "1 passed" in combined
