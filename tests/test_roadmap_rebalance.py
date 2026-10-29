"""Tests for ``specy-road rebalance-chunks`` (power-user maintenance)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, script_subprocess_env


from specy_road.bundled_scripts.roadmap_chunk_utils import (
    load_json_chunk,
    load_manifest_mapping,
    render_json_chunk,
)
from specy_road.bundled_scripts.roadmap_rebalance import (
    build_normalize_plan,
    build_pack_plan,
)


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


def test_rebalance_refuses_when_milestone_active(tmp_path: Path) -> None:
    """v0.1.1 gap fix: rebalance must refuse while any milestone is in-flight.

    A live ``active`` or ``pending_mr`` milestone subtree means the PM lock
    is enforced on cmd_edit / cmd_set_gate_status / the PM Gantt API.
    Rebalance silently moving nodes between chunks under that subtree
    would bypass the lock semantically (the chunk reorganization IS a
    mutation under the locked parent). Force the operator to reconcile
    + close the milestone first.
    """
    import json as _json

    repo = _copy_dogfood(tmp_path / "df")
    # Tag M0 with an active milestone_execution. The dogfood schema
    # accepts this field (added in v0.1.0).
    chunk = repo / "roadmap" / "phases" / "M0.json"
    doc = _json.loads(chunk.read_text(encoding="utf-8"))
    nodes = doc["nodes"] if isinstance(doc, dict) else doc
    for n in nodes:
        if isinstance(n, dict) and n.get("id") == "M0":
            n["milestone_execution"] = {
                "state": "active",
                "rollup_branch": "feature/rm-tmp",
                "integration_branch": "dev",
                "remote": "origin",
            }
    chunk.write_text(_json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    r = _run_rebal(repo)
    assert r.returncode == 1, (
        f"expected exit 1, got {r.returncode}\n--stdout--\n{r.stdout}\n--stderr--\n{r.stderr}"
    )
    assert "milestone subtree" in r.stderr or "milestone" in r.stderr
    assert "M0" in r.stderr
    assert "reconcile-milestone-status" in r.stderr
    assert "Traceback" not in r.stderr


def _hand_order(chunk: Path) -> list[dict]:
    """Rewrite ``chunk`` the way a person might: keys reversed, bare array, indent 4."""
    import json as _json

    nodes = load_json_chunk(chunk)
    hand = [dict(reversed(list(n.items()))) for n in nodes]
    chunk.write_text(_json.dumps(hand, indent=4) + "\n", encoding="utf-8")
    return nodes


def _ids_by_chunk(repo: Path) -> dict[str, list[str]]:
    return {
        rel: [n["id"] for n in load_json_chunk(repo / "roadmap" / rel)]
        for rel in load_manifest_mapping(repo)["includes"]
    }


def test_normalize_rewrites_hand_ordered_chunk_without_moving_nodes(
    tmp_path: Path,
) -> None:
    repo = _copy_dogfood(tmp_path / "df")
    chunk = repo / "roadmap" / "phases" / "M0.json"
    other = repo / "roadmap" / "phases" / "M1.json"
    nodes = _hand_order(chunk)
    ids_before = _ids_by_chunk(repo)
    manifest_before = (repo / "roadmap" / "manifest.json").read_bytes()
    other_before = other.read_bytes()

    dry = _run_rebal(repo, "--normalize", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert "~ roadmap/phases/M0.json" in dry.stdout
    assert "(dry-run; no files written)" in dry.stdout
    assert not chunk.read_text(encoding="utf-8").startswith("{")

    r = _run_rebal(repo, "--normalize")
    assert r.returncode == 0, r.stderr
    assert "specy-road validate passed" in r.stdout
    assert chunk.read_text(encoding="utf-8") == render_json_chunk(nodes)
    # Same nodes in the same chunks and order: M0.2 stays in M1.json, where a
    # plain rebalance would have moved it back under its phase.
    assert _ids_by_chunk(repo) == ids_before
    assert "M0.2" in ids_before["phases/M1.json"]
    assert (repo / "roadmap" / "manifest.json").read_bytes() == manifest_before
    assert other.read_bytes() == other_before


def test_normalize_is_idempotent(tmp_path: Path) -> None:
    repo = _copy_dogfood(tmp_path / "df")
    _hand_order(repo / "roadmap" / "phases" / "M0.json")
    r1 = _run_rebal(repo, "--normalize")
    assert r1.returncode == 0, r1.stderr
    after_first = {
        p.name: p.read_bytes() for p in (repo / "roadmap").rglob("*.json")
    }
    assert build_normalize_plan(repo) == {}
    r2 = _run_rebal(repo, "--normalize")
    assert r2.returncode == 0, r2.stderr
    assert "already canonical; nothing to do" in r2.stdout
    after_second = {
        p.name: p.read_bytes() for p in (repo / "roadmap").rglob("*.json")
    }
    assert after_first == after_second
