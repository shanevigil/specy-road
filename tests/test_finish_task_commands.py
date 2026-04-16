"""Tests for finish_task and mark_implementation_reviewed helpers."""

from __future__ import annotations

import pytest

import finish_task as ft
import mark_implementation_reviewed as mir


def test_resolve_context_rejects_registry_branch_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = {
        "version": 1,
        "entries": [
            {
                "codename": "example",
                "node_id": "M1.1",
                "branch": "feature/rm-other",
                "touch_zones": ["src/"],
            }
        ],
    }
    monkeypatch.setattr(ft, "_load_registry", lambda: reg)
    monkeypatch.setattr(
        ft,
        "load_roadmap",
        lambda _p: {"nodes": [{"id": "M1.1", "title": "Example"}]},
    )
    with pytest.raises(SystemExit):
        ft._resolve_context("feature/rm-example")


def test_resolve_context_rejects_missing_branch_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = {
        "version": 1,
        "entries": [
            {
                "codename": "example",
                "node_id": "M1.1",
                "touch_zones": ["src/"],
            }
        ],
    }
    monkeypatch.setattr(ft, "_load_registry", lambda: reg)
    monkeypatch.setattr(
        ft,
        "load_roadmap",
        lambda _p: {"nodes": [{"id": "M1.1", "title": "Example"}]},
    )
    with pytest.raises(SystemExit):
        ft._resolve_context("feature/rm-example")


def test_resolve_context_rejects_non_leaf_registry_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = {
        "version": 1,
        "entries": [
            {
                "codename": "example",
                "node_id": "M1",
                "branch": "feature/rm-example",
                "touch_zones": ["src/"],
            }
        ],
    }
    nodes = [
        {"id": "M1", "title": "Parent"},
        {"id": "M1.1", "title": "Child", "parent_id": "M1"},
    ]
    monkeypatch.setattr(ft, "_load_registry", lambda: reg)
    monkeypatch.setattr(ft, "load_roadmap", lambda _p: {"nodes": nodes})
    with pytest.raises(SystemExit):
        ft._resolve_context("feature/rm-example")


def test_extract_walkthrough_parses_markdown_section() -> None:
    text = """# X

## Walkthrough

1. First
2. Second

## Other
noop
"""
    body = mir._extract_walkthrough(text)
    assert body is not None
    assert "1. First" in body
    assert "noop" not in body


def test_extract_walkthrough_none_when_missing() -> None:
    assert mir._extract_walkthrough("# Only\n\nno walk") is None


def test_finish_blocks_when_implementation_review_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = {
        "version": 1,
        "entries": [
            {
                "codename": "example",
                "node_id": "M1.1",
                "branch": "feature/rm-example",
                "touch_zones": ["src/"],
                "implementation_review": "pending",
            }
        ],
    }
    monkeypatch.setattr(ft, "_load_registry", lambda: reg)
    monkeypatch.setattr(
        ft,
        "load_roadmap",
        lambda _p: {"nodes": [{"id": "M1.1", "title": "Example"}]},
    )
    monkeypatch.setattr(ft, "require_implementation_review_before_finish", lambda _r: True)
    monkeypatch.setattr(ft, "_current_branch", lambda: "feature/rm-example")
    monkeypatch.setattr(ft, "_update_chunk_status", lambda _nid: [])
    monkeypatch.setattr(ft, "_validate_and_export", lambda: None)
    monkeypatch.setattr(ft, "_git", lambda *_a, **_k: None)
    with pytest.raises(SystemExit) as ei:
        ft.main([])
    assert ei.value.code == 1


def test_update_chunk_status_json_writes_complete(tmp_path, monkeypatch) -> None:
    import json

    from roadmap_chunk_utils import load_json_chunk

    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/x.json"]}) + "\n",
        encoding="utf-8",
    )
    nodes = [
        {
            "id": "M1.1",
            "parent_id": None,
            "type": "milestone",
            "title": "Example",
            "codename": "example",
            "status": "Not Started",
        },
    ]
    (tmp_path / "roadmap" / "phases" / "x.json").write_text(
        json.dumps({"nodes": nodes}, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ft, "ROOT", tmp_path)
    changed = ft._update_chunk_status("M1.1")
    assert changed == ["roadmap/phases/x.json"]
    out = load_json_chunk(tmp_path / "roadmap" / "phases" / "x.json")
    assert out[0]["status"] == "Complete"
