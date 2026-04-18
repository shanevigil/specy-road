"""Unit tests for scripts/post_release_readme_cleanup.py."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "post_release_readme_cleanup.py"


def _run(version: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), version],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed(tmp_path: Path, body: str) -> Path:
    out = tmp_path / "README.md"
    out.write_text(body, encoding="utf-8")
    return out


def test_strips_pre_release_block_and_todo(tmp_path: Path) -> None:
    body = """<!--
TODO(post-release): wire automated PyPI build-and-publish on every tagged
release (v*.*.*), then replace the install-from-source block below with a
single `pip install specy-road` line.
-->

# specy-road

> ## ⚠️ Pre-release notice
> The first tagged release is pending. **There is no `specy-road` package on
> PyPI yet.** Install from source as shown in the [Install](#install) section
> until v0.1 ships.

**Roadmap-first coordination** for teams and coding agents.

## Install

Requires **Python 3.11+** and **git** (with a configured remote — `origin` by
default).

```bash
git clone https://github.com/shanevigil/specy-road.git
cd specy-road
git switch dev
pip install -e ".[dev,gui-next]"
```

How the PM Gantt UI is packaged: see other docs.
"""
    _seed(tmp_path, body)
    r = _run("0.1.0", tmp_path)
    assert r.returncode == 0, r.stderr
    new = (tmp_path / "README.md").read_text(encoding="utf-8")
    # TODO comment gone.
    assert "TODO(post-release)" not in new
    # Pre-release blockquote gone.
    assert "Pre-release notice" not in new
    # New install block.
    assert "pip install specy-road" in new
    assert "git clone" not in new


def test_idempotent_on_already_clean_readme(tmp_path: Path) -> None:
    """Running twice (or on a clean README) is a no-op."""
    body = """# specy-road

A clean README without the pre-release scaffolding.

## Install

```bash
pip install specy-road
```
"""
    _seed(tmp_path, body)
    r1 = _run("0.1.0", tmp_path)
    text_after_first = (tmp_path / "README.md").read_text(encoding="utf-8")
    r2 = _run("0.1.0", tmp_path)
    text_after_second = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert r1.returncode == 0
    assert r2.returncode == 0
    # No-op the second time.
    assert text_after_first == text_after_second


def test_real_readme_smoke(tmp_path: Path) -> None:
    """Smoke test against the actual repo README — verify it cleans without crash."""
    src = REPO / "README.md"
    dst = tmp_path / "README.md"
    shutil.copy2(src, dst)
    r = _run("0.1.0", tmp_path)
    assert r.returncode == 0, r.stderr
    new = dst.read_text(encoding="utf-8")
    assert "TODO(post-release)" not in new
    assert "Pre-release notice" not in new
    assert "pip install specy-road" in new
