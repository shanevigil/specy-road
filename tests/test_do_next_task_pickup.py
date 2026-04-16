"""Tests for do-next-available-task pickup (registry commit, push, CI-skip message)."""

from __future__ import annotations

import yaml
import pytest

import do_next_task as dnt
from registration_pickup_commit import (
    REGISTRATION_COMMIT_CI_SKIP_SUFFIX,
    registration_commit_message,
)


def _pickup_test_node() -> dict:
    return {
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


def test_pickup_git_order_after_sync(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """brief → register commit on integration → checkout -b feature (push mocked out)."""
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )

    node = _pickup_test_node()
    monkeypatch.setattr(dnt, "load_roadmap", lambda _p: {"nodes": [node]})
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "_sync_integration_branch", lambda _b, _r: None)
    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_push_integration_branch", lambda _r, _b: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "pr")
    monkeypatch.setattr(dnt, "merge_request_requires_manual_approval", lambda _r: False)
    monkeypatch.setattr(
        dnt,
        "resolve_integration_defaults",
        lambda _root, explicit_base=None, explicit_remote=None: ("main", "origin", []),
    )
    monkeypatch.setattr(dnt, "_write_brief", lambda n, nodes: tmp_path / "work" / "brief-M9.1.md")
    monkeypatch.setattr(
        dnt,
        "write_agent_prompt",
        lambda n, nodes, bp, **kw: tmp_path / "work" / "prompt-M9.1.md",
    )

    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "brief-M9.1.md").write_text("x", encoding="utf-8")

    dnt.main(
        [
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert calls[0][0] == "add"
    assert calls[0][1].replace("\\", "/").endswith("roadmap/registry.yaml")
    assert calls[1][0] == "commit"
    assert "chore(rm-pickup-git): register as in-progress" in calls[1][2]
    assert REGISTRATION_COMMIT_CI_SKIP_SUFFIX in calls[1][2]
    assert calls[2] == ["checkout", "-b", "feature/rm-pickup-git"]


def test_pickup_git_order_pushes_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Default: add → commit (with CI skip suffix) → push integration → checkout -b feature."""
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )

    node = _pickup_test_node()
    monkeypatch.setattr(dnt, "load_roadmap", lambda _p: {"nodes": [node]})
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "_sync_integration_branch", lambda _b, _r: None)
    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "pr")
    monkeypatch.setattr(dnt, "merge_request_requires_manual_approval", lambda _r: False)
    monkeypatch.setattr(
        dnt,
        "resolve_integration_defaults",
        lambda _root, explicit_base=None, explicit_remote=None: ("main", "origin", []),
    )
    monkeypatch.setattr(dnt, "_write_brief", lambda n, nodes: tmp_path / "work" / "brief-M9.1.md")
    monkeypatch.setattr(
        dnt,
        "write_agent_prompt",
        lambda n, nodes, bp, **kw: tmp_path / "work" / "prompt-M9.1.md",
    )

    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "brief-M9.1.md").write_text("x", encoding="utf-8")

    dnt.main(["--repo-root", str(tmp_path)])

    assert calls[0][0] == "add"
    assert calls[1][0] == "commit"
    assert "[skip ci]" in calls[1][2]
    assert calls[2] == ["push", "origin", "main"]
    assert calls[3] == ["checkout", "-b", "feature/rm-pickup-git"]


def test_pickup_registers_leaf_claim_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    (tmp_path / "roadmap").mkdir(parents=True)
    reg_path = tmp_path / "roadmap" / "registry.yaml"
    reg_path.write_text("version: 1\nentries: []\n", encoding="utf-8")

    parent = {
        "id": "M9",
        "node_key": "11111111-aaaa-4aaa-8aaa-111111111111",
        "type": "phase",
        "title": "Parent",
        "codename": "pickup-parent",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": ["src/"],
    }
    leaf = _pickup_test_node()
    leaf["parent_id"] = "M9"
    monkeypatch.setattr(dnt, "load_roadmap", lambda _p: {"nodes": [parent, leaf]})
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "_sync_integration_branch", lambda _b, _r: None)
    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_push_integration_branch", lambda _r, _b: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "pr")
    monkeypatch.setattr(dnt, "merge_request_requires_manual_approval", lambda _r: False)
    monkeypatch.setattr(
        dnt,
        "resolve_integration_defaults",
        lambda _root, explicit_base=None, explicit_remote=None: ("main", "origin", []),
    )
    monkeypatch.setattr(dnt, "_write_brief", lambda n, nodes: tmp_path / "work" / "brief-M9.1.md")
    monkeypatch.setattr(
        dnt,
        "write_agent_prompt",
        lambda n, nodes, bp, **kw: tmp_path / "work" / "prompt-M9.1.md",
    )
    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "brief-M9.1.md").write_text("x", encoding="utf-8")

    dnt.main(["--repo-root", str(tmp_path)])

    reg_doc = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    assert reg_doc["entries"][0]["node_id"] == "M9.1"
    assert reg_doc["entries"][0]["codename"] == "pickup-git"
    assert calls[2] == ["checkout", "-b", "feature/rm-pickup-git"]


def test_pickup_rejects_non_leaf_when_available_returns_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-leaf from _available triggers assert_leaf_target before git."""

    def fake_git(*_args: str) -> None:  # pragma: no cover
        pytest.fail(
            "git should not run when pickup rejects non-leaf target",
        )

    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )

    parent = {
        "id": "M9",
        "node_key": "11111111-aaaa-4aaa-8aaa-111111111111",
        "type": "phase",
        "title": "Parent",
        "codename": "pickup-parent",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": ["src/"],
    }
    leaf = _pickup_test_node()
    leaf["parent_id"] = "M9"

    def misconfigured_available(_nodes, _reg, _enrich=None, **_kwargs):
        return [parent]

    monkeypatch.setattr(
        dnt,
        "load_roadmap",
        lambda _p: {"nodes": [parent, leaf]},
    )
    monkeypatch.setattr(dnt, "_available", misconfigured_available)
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "_sync_integration_branch", lambda _b, _r: None)
    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "pr")
    monkeypatch.setattr(
        dnt,
        "merge_request_requires_manual_approval",
        lambda _r: False,
    )
    monkeypatch.setattr(
        dnt,
        "resolve_integration_defaults",
        lambda _root, explicit_base=None, explicit_remote=None: (
            "main",
            "origin",
            [],
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        dnt.main(
            [
                "--repo-root",
                str(tmp_path),
            ],
        )

    assert excinfo.value.code == 1
    err = capsys.readouterr().err.lower()
    assert "not a leaf" in err
    assert "only claim leaves" in err


def test_registration_commit_message_ci_skip_toggle() -> None:
    assert "[skip ci]" in registration_commit_message("foo", include_ci_skip=True)
    assert "[skip ci]" not in registration_commit_message("foo", include_ci_skip=False)
    assert registration_commit_message("foo", include_ci_skip=False) == (
        "chore(rm-foo): register as in-progress"
    )


def test_pickup_commit_without_ci_skip_tokens(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )

    node = _pickup_test_node()
    monkeypatch.setattr(dnt, "load_roadmap", lambda _p: {"nodes": [node]})
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "_sync_integration_branch", lambda _b, _r: None)
    monkeypatch.setattr(dnt, "_assert_working_tree_clean", lambda: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_push_integration_branch", lambda _r, _b: None)
    monkeypatch.setattr(dnt, "_git", fake_git)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "pr")
    monkeypatch.setattr(dnt, "merge_request_requires_manual_approval", lambda _r: False)
    monkeypatch.setattr(
        dnt,
        "resolve_integration_defaults",
        lambda _root, explicit_base=None, explicit_remote=None: ("main", "origin", []),
    )
    monkeypatch.setattr(dnt, "_write_brief", lambda n, nodes: tmp_path / "work" / "brief-M9.1.md")
    monkeypatch.setattr(
        dnt,
        "write_agent_prompt",
        lambda n, nodes, bp, **kw: tmp_path / "work" / "prompt-M9.1.md",
    )

    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "brief-M9.1.md").write_text("x", encoding="utf-8")

    dnt.main(
        [
            "--no-ci-skip-in-message",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert calls[1][0] == "commit"
    assert calls[1][2] == "chore(rm-pickup-git): register as in-progress"
