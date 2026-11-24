"""Smoke tests for reconcile-milestone-status script."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import REPO, script_subprocess_env
from tests.support.cli import run_script


@pytest.mark.parametrize("extra", [[], ["--fallback-head-delivery"]])
def test_reconcile_dry_run_on_dogfood(extra: list[str]) -> None:
    dog = REPO / "tests" / "fixtures" / "specy_road_dogfood"
    argv = ["--repo-root", str(dog), *extra]
    r = run_script("reconcile_milestone_status.py", argv, cwd=REPO, env=script_subprocess_env())
    assert r.returncode == 0, r.stderr
    assert "Nothing to reconcile" in r.stdout or r.stdout.strip() != ""
