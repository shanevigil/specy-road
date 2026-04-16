"""Tests for do_next_task and finish_task logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import do_next_available as dna
import do_next_task as dnt
import finish_task as ft

# ---------------------------------------------------------------------------
# do_next_task: _available
# ---------------------------------------------------------------------------

# dependencies[] reference node_key UUIDs (not display ids)
_NK_PREREQ = "11111111-1111-4111-8111-111111111111"
_NK_EXAMPLE = "22222222-2222-4222-8222-222222222222"

_BASE_NODE = {
    "id": "M1.1",
    "node_key": _NK_EXAMPLE,
    "type": "milestone",
    "title": "Example",
    "codename": "example",
    "execution_milestone": "Agentic-led",
    "status": "Not Started",
    "dependencies": [],
    "touch_zones": [],
}


def _reg(*node_ids: str) -> dict:
    return {
        "version": 1,
        "entries": [{"node_id": nid, "codename": nid} for nid in node_ids],
    }


def test_available_returns_unclaimed_agentic() -> None:
    nodes = [_BASE_NODE]
    result = dnt._available(nodes, _reg(), {})
    assert len(result) == 1
    assert result[0]["id"] == "M1.1"


def test_available_excludes_claimed() -> None:
    nodes = [_BASE_NODE]
    assert dnt._available(nodes, _reg("M1.1"), {}) == []


def test_available_excludes_complete() -> None:
    node = {**_BASE_NODE, "status": "Complete"}
    assert dnt._available([node], _reg(), {}) == []


def test_available_excludes_unmet_deps() -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    node = {**_BASE_NODE, "dependencies": [_NK_PREREQ]}
    assert dnt._available([dep, node], _reg(), {}) == []


def test_available_includes_when_deps_complete() -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Complete",
        "dependencies": [],
    }
    node = {**_BASE_NODE, "dependencies": [_NK_PREREQ]}
    result = dnt._available([dep, node], _reg(), {})
    assert len(result) == 1


def test_available_excludes_human_led_no_agentic_subtask() -> None:
    node = {**_BASE_NODE, "execution_milestone": "Human-led"}
    assert dnt._available([node], _reg(), {}) == []


def test_available_includes_agentic_subtask() -> None:
    node = {
        **_BASE_NODE,
        "execution_milestone": None,
        "execution_subtask": "agentic",
    }
    result = dnt._available([node], _reg(), {})
    assert len(result) == 1


def test_available_excludes_no_codename() -> None:
    node = {**_BASE_NODE, "codename": None}
    assert dnt._available([node], _reg(), {}) == []


def test_available_prioritizes_blocked_before_not_started() -> None:
    a = {**_BASE_NODE, "id": "M1.2", "codename": "a", "status": "Not Started"}
    b = {**_BASE_NODE, "id": "M1.3", "node_key": "33333333-3333-4333-8333-333333333333", "codename": "b", "status": "Blocked"}
    result = dnt._available([a, b], _reg(), {})
    assert [n["id"] for n in result] == ["M1.3", "M1.2"]


def test_load_branch_enrichment_returns_empty_on_registry_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    def boom(_root):
        raise RuntimeError("no registry")

    monkeypatch.setattr(dna, "load_registry", boom)
    assert dna._load_branch_enrichment(tmp_path) == {}


def test_available_orders_blocked_then_mr_rejected_then_not_started() -> None:
    a = {**_BASE_NODE, "id": "M1.2", "codename": "a", "status": "Not Started"}
    b = {
        **_BASE_NODE,
        "id": "M1.3",
        "node_key": "33333333-3333-4333-8333-333333333333",
        "codename": "b",
        "status": "Blocked",
    }
    c = {
        **_BASE_NODE,
        "id": "M1.4",
        "node_key": "44444444-4444-4444-8444-444444444444",
        "codename": "c",
        "status": "In Progress",
    }
    enrich = {
        "M1.4": {"kind": "github_pr", "pr_state": "rejected", "merged": False},
    }
    result = dnt._available([a, b, c], _reg(), enrich)
    assert [n["id"] for n in result] == ["M1.3", "M1.4", "M1.2"]


def test_available_prioritizes_mr_rejected_before_not_started() -> None:
    a = {**_BASE_NODE, "id": "M1.2", "codename": "a", "status": "Not Started"}
    b = {
        **_BASE_NODE,
        "id": "M1.3",
        "node_key": "33333333-3333-4333-8333-333333333333",
        "codename": "b",
        "status": "In Progress",
    }
    enrich = {
        "M1.3": {"kind": "github_pr", "pr_state": "rejected", "merged": False},
    }
    result = dnt._available([a, b], _reg(), enrich)
    assert [n["id"] for n in result] == ["M1.3", "M1.2"]


def test_sync_integration_branch_git_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    dnt._sync_integration_branch("main", "origin")
    assert calls == [
        ["fetch", "origin"],
        ["checkout", "main"],
        ["merge", "--ff-only", "origin/main"],
    ]


def test_assert_current_branch_equals_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dnt, "_current_branch", lambda: "dev")
    dnt._assert_current_branch_equals("dev")


def test_assert_current_branch_equals_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dnt, "_current_branch", lambda: "other")
    with pytest.raises(SystemExit):
        dnt._assert_current_branch_equals("dev")


def test_assert_current_branch_equals_detached_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dnt, "_current_branch", lambda: "HEAD")
    with pytest.raises(SystemExit):
        dnt._assert_current_branch_equals("main")


def test_validate_touch_zones_empty_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    node = {"id": "M1.1", "codename": "x", "touch_zones": []}
    with pytest.raises(SystemExit):
        dnt._validate_touch_zones(node)


def test_pickup_git_order_after_sync(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """brief → register commit on integration → checkout -b feature → (prompt would follow)."""
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )

    node = {
        "id": "M9.1",
        "node_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "type": "milestone",
        "title": "T",
        "codename": "pickup-git",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": ["src/"],
    }
    monkeypatch.setattr(
        dnt,
        "load_roadmap",
        lambda _p: {"nodes": [node]},
    )
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "_sync_integration_branch", lambda _b, _r: None)
    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    monkeypatch.setattr(dnt, "merge_request_requires_manual_approval", lambda _r: False)
    monkeypatch.setattr(
        dnt,
        "resolve_integration_defaults",
        lambda _root, explicit_base=None, explicit_remote=None: ("main", "origin", []),
    )
    monkeypatch.setattr(dnt, "_write_brief", lambda n, nodes: tmp_path / "work" / "brief-M9.1.md")

    def _fake_prompt(n, nodes, bp, **kw):
        return tmp_path / "work" / "prompt-M9.1.md"

    monkeypatch.setattr(dnt, "write_agent_prompt", _fake_prompt)

    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "brief-M9.1.md").write_text("x", encoding="utf-8")

    argv = [
        "--no-sync",
        "--repo-root",
        str(tmp_path),
    ]
    dnt.main(argv)

    assert calls[0][0] == "add"
    assert calls[0][1].replace("\\", "/").endswith("roadmap/registry.yaml")
    assert calls[1][0] == "commit"
    assert calls[2] == ["checkout", "-b", "feature/rm-pickup-git"]


def test_working_tree_clean_true() -> None:
    with patch.object(dnt.subprocess, "run", return_value=__import__("types").SimpleNamespace(stdout="", returncode=0)):
        assert dnt._working_tree_clean() is True


def test_working_tree_clean_false() -> None:
    with patch.object(
        dnt.subprocess,
        "run",
        return_value=__import__("types").SimpleNamespace(stdout=" M foo\n", returncode=0),
    ):
        assert dnt._working_tree_clean() is False


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
