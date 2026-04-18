"""Tests for roadmap merge loading."""

from __future__ import annotations

import json

import pytest

import roadmap_load as rl


def _write_manifest_json(r: object, includes: list[str]) -> None:
    r.mkdir(parents=True, exist_ok=True)
    (r / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": includes}),
        encoding="utf-8",
    )


def test_load_roadmap_merges_json_includes(tmp_path) -> None:
    r = tmp_path / "roadmap"
    _write_manifest_json(r, ["a.json"])
    (r / "a.json").write_text(
        json.dumps(
            [
                {
                    "id": "M0",
                    "parent_id": None,
                    "type": "phase",
                    "title": "P",
                },
            ],
        ),
        encoding="utf-8",
    )
    doc = rl.load_roadmap(tmp_path)
    assert doc["version"] == 1
    assert len(doc["nodes"]) == 1
    assert doc["nodes"][0]["id"] == "M0"


def test_load_roadmap_requires_manifest_json(tmp_path) -> None:
    (tmp_path / "roadmap").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        rl.load_roadmap(tmp_path)


def test_validate_roadmap_line_limits_json_chunk(tmp_path) -> None:
    """Oversized multi-node JSON chunk fails; limit is configurable."""
    r = tmp_path / "roadmap"
    _write_manifest_json(r, ["a.json"])
    # Pretty-printed arrays yield many physical lines (embedded ``\\n`` in JSON strings does not).
    pad = [f"pad{i}" for i in range(400)]
    nodes = [
        {"id": "M0", "parent_id": None, "type": "phase", "title": "a", "pad": pad},
        {"id": "M1", "parent_id": None, "type": "phase", "title": "b", "pad": pad},
    ]
    (r / "a.json").write_text(
        json.dumps({"nodes": nodes}, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        rl.validate_roadmap_line_limits(tmp_path)

    constraints = tmp_path / "constraints"
    constraints.mkdir()
    (constraints / "file-limits.yaml").write_text(
        "roadmap_json_chunk_max_lines: 2000\n",
        encoding="utf-8",
    )
    rl.validate_roadmap_line_limits(tmp_path)


def test_validate_roadmap_line_limits_manifest_reads_config(tmp_path) -> None:
    """Manifest line cap is read from constraints/file-limits.yaml."""
    r = tmp_path / "roadmap"
    r.mkdir(parents=True)
    big = ["a.json"] * 700
    (r / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": big}, indent=2),
        encoding="utf-8",
    )
    (r / "a.json").write_text(
        json.dumps([{"id": "M0", "parent_id": None, "type": "phase", "title": "p"}]),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        rl.validate_roadmap_line_limits(tmp_path)

    constraints = tmp_path / "constraints"
    constraints.mkdir()
    (constraints / "file-limits.yaml").write_text(
        "roadmap_manifest_max_lines: 2000\n",
        encoding="utf-8",
    )
    rl.validate_roadmap_line_limits(tmp_path)


def test_load_roadmap_rejects_top_level_nodes(tmp_path) -> None:
    r = tmp_path / "roadmap"
    r.mkdir()
    (r / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": [], "nodes": []}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        rl.load_roadmap(tmp_path)


def test_load_annotates_rollup_status_for_leaf(tmp_path) -> None:
    """F-013: load_roadmap injects rollup_status; for leaves it equals status."""
    r = tmp_path / "roadmap"
    _write_manifest_json(r, ["a.json"])
    nodes = [
        {
            "id": "M0",
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "status": "Not Started",
        },
    ]
    (r / "a.json").write_text(
        json.dumps({"nodes": nodes}, indent=2),
        encoding="utf-8",
    )
    doc = rl.load_roadmap(tmp_path)
    assert doc["nodes"][0]["rollup_status"] == "Not Started"


def test_load_rollup_status_complete_when_all_leaves_complete(tmp_path) -> None:
    """F-013: a non-leaf rolls up to Complete iff every leaf descendant is Complete."""
    r = tmp_path / "roadmap"
    _write_manifest_json(r, ["a.json"])
    nodes = [
        {"id": "M0", "parent_id": None, "type": "phase", "title": "P", "status": "Not Started"},
        {"id": "M0.1", "parent_id": "M0", "type": "task", "title": "T1", "status": "Complete"},
        {"id": "M0.2", "parent_id": "M0", "type": "task", "title": "T2", "status": "Complete"},
    ]
    (r / "a.json").write_text(
        json.dumps({"nodes": nodes}, indent=2),
        encoding="utf-8",
    )
    doc = rl.load_roadmap(tmp_path)
    by_id = {n["id"]: n for n in doc["nodes"]}
    assert by_id["M0"]["rollup_status"] == "Complete"
    assert by_id["M0.1"]["rollup_status"] == "Complete"


def test_load_rollup_status_picks_blocked_over_in_progress(tmp_path) -> None:
    r = tmp_path / "roadmap"
    _write_manifest_json(r, ["a.json"])
    nodes = [
        {"id": "M0", "parent_id": None, "type": "phase", "title": "P", "status": "Not Started"},
        {"id": "M0.1", "parent_id": "M0", "type": "task", "title": "T1", "status": "Blocked"},
        {"id": "M0.2", "parent_id": "M0", "type": "task", "title": "T2", "status": "In Progress"},
    ]
    (r / "a.json").write_text(
        json.dumps({"nodes": nodes}, indent=2),
        encoding="utf-8",
    )
    doc = rl.load_roadmap(tmp_path)
    by_id = {n["id"]: n for n in doc["nodes"]}
    assert by_id["M0"]["rollup_status"] == "Blocked"
