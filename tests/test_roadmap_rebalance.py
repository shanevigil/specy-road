"""Tests for ``specy-road rebalance-chunks`` (power-user maintenance)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, script_subprocess_env

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))

from roadmap_chunk_utils import load_json_chunk, load_manifest_mapping  # noqa: E402
from roadmap_rebalance import build_pack_plan  # noqa: E402


def _copy_dogfood(dest: Path) -> Path:
    shutil.copytree(DOGFOOD, dest)
    return dest


def _run_rebal(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "roadmap_rebalance.py"),
            "--repo-root",
            str(repo),
            *args,
        ],
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def test_rebalance_dry_run_does_not_write(tmp_path: Path) -> None:
    repo = _copy_dogfood(tmp_path / "df")
    before_manifest = (repo / "roadmap" / "manifest.json").read_bytes()
    before_files = sorted(p.name for p in (repo / "roadmap" / "phases").iterdir())
    r = _run_rebal(repo, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "rebalance-chunks plan:" in r.stdout
    assert "(dry-run; no files written)" in r.stdout
    assert (repo / "roadmap" / "manifest.json").read_bytes() == before_manifest
    after_files = sorted(p.name for p in (repo / "roadmap" / "phases").iterdir())
    assert before_files == after_files


def test_rebalance_consolidates_phase_nodes(tmp_path: Path) -> None:
    """The dogfood graph has M0.2 living in M1.json; rebalance should bring it back to M0.json."""
    repo = _copy_dogfood(tmp_path / "df")
    plan = build_pack_plan(repo)
    # Map abs_path -> [ids].
    by_path = {p: [n["id"] for n in nodes] for p, nodes in plan.chunk_writes.items()}
    m0 = repo / "roadmap" / "phases" / "M0.json"
    m1 = repo / "roadmap" / "phases" / "M1.json"
    assert "M0.2" in by_path[m0]  # consolidated under its phase
    assert "M0.2" not in by_path[m1]


def test_rebalance_apply_writes_and_validates(tmp_path: Path) -> None:
    repo = _copy_dogfood(tmp_path / "df")
    r = _run_rebal(repo)
    assert r.returncode == 0, r.stderr
    assert "specy-road validate passed" in r.stdout
    # M0.json now holds all four M0-phase nodes.
    nodes_m0 = load_json_chunk(repo / "roadmap" / "phases" / "M0.json")
    ids = {n["id"] for n in nodes_m0}
    assert {"M0", "M0.1", "M0.2", "M0.3"}.issubset(ids)
    doc = load_manifest_mapping(repo)
    assert all(rel.startswith("phases/") for rel in doc["includes"])


def test_rebalance_idempotent(tmp_path: Path) -> None:
    repo = _copy_dogfood(tmp_path / "df")
    r1 = _run_rebal(repo)
    assert r1.returncode == 0, r1.stderr
    state_after_first = {
        p.name: p.read_bytes()
        for p in (repo / "roadmap" / "phases").iterdir()
        if p.suffix == ".json"
    }
    manifest_after_first = (repo / "roadmap" / "manifest.json").read_bytes()
    r2 = _run_rebal(repo)
    assert r2.returncode == 0, r2.stderr
    state_after_second = {
        p.name: p.read_bytes()
        for p in (repo / "roadmap" / "phases").iterdir()
        if p.suffix == ".json"
    }
    manifest_after_second = (repo / "roadmap" / "manifest.json").read_bytes()
    assert state_after_first == state_after_second
    assert manifest_after_first == manifest_after_second
