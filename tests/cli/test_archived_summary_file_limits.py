"""Archived implementation summaries under work/done/ stay exempt from file-limits (M15.32)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.helpers import REPO, script_subprocess_env
from tests.support.cli import run_cli


def _lines(n: int) -> str:
    return "x\n" * n


def _init_scaffold(root: Path) -> None:
    env = script_subprocess_env()
    run_cli(["init", "project", str(root)], cwd=REPO, env=env).check_returncode()


def _file_limits(root: Path) -> subprocess.CompletedProcess[str]:
    return run_cli(
        ["file-limits", "--repo-root", str(root)],
        cwd=REPO,
        env=script_subprocess_env(),
    )


def test_archived_implementation_summary_exempt_other_work_done_files_are_not(
    tmp_path: Path,
) -> None:
    """Template ``**/*.md`` cap (1000 lines): archived summaries pass; other work/done/ md fails."""
    _init_scaffold(tmp_path)
    done = tmp_path / "work" / "done"
    done.mkdir(parents=True, exist_ok=True)
    (done / "implementation-summary-M1.md").write_text(_lines(1050), encoding="utf-8")

    ok = _file_limits(tmp_path)
    assert ok.returncode == 0, ok.stdout + ok.stderr

    (done / "notes.md").write_text(_lines(1050), encoding="utf-8")
    bad = _file_limits(tmp_path)
    assert bad.returncode == 1
    assert "work/done/notes.md" in bad.stderr
