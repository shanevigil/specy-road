"""Tests for ``set-gate-status`` CLI (type gate only)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from specy_road.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from tests.helpers import BUNDLED_SCRIPTS, REPO, SCHEMAS, script_subprocess_env
from tests.support.extracted.set_gate_status import sheet, repo_with_gate






def _run_crud(tmp: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "roadmap_crud.py"), *args],
        cwd=tmp,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def test_set_gate_status_cli_updates_gate(tmp_path: Path) -> None:
    repo_with_gate(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-gate-status",
        "M99.4",
        "--status",
        "Complete",
    )
    assert r.returncode == 0, r.stderr
    nodes = load_json_chunk(tmp_path / "roadmap" / "phases" / "T.json")
    gate = next(n for n in nodes if n["id"] == "M99.4")
    assert gate["status"] == "Complete"


def test_set_gate_status_cli_rejects_task(tmp_path: Path) -> None:
    repo_with_gate(tmp_path)
    r = _run_crud(
        tmp_path,
        "--repo-root",
        str(tmp_path),
        "set-gate-status",
        "M99.1",
        "--status",
        "Complete",
    )
    assert r.returncode == 1
    assert "only applies to type gate" in r.stderr
