"""Tests for do-next-available-task pickup (registry commit, push, CI-skip message)."""

from __future__ import annotations

import pytest

import do_next_task as dnt
from registration_pickup_commit import (
    REGISTRATION_COMMIT_CI_SKIP_SUFFIX,
    registration_commit_message,
    warn_degraded_pickup,
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
    """brief → register commit on integration → checkout -b feature (no push in this test)."""
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
            "--no-sync",
            "--no-push-registry",
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

    dnt.main(["--no-sync", "--repo-root", str(tmp_path)])

    assert calls[0][0] == "add"
    assert calls[1][0] == "commit"
    assert "[skip ci]" in calls[1][2]
    assert calls[2] == ["push", "origin", "main"]
    assert calls[3] == ["checkout", "-b", "feature/rm-pickup-git"]


def test_warn_degraded_pickup_quiet_when_full_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    warn_degraded_pickup(
        no_sync=False,
        no_push_registry=False,
        remote="origin",
        base="main",
    )
    assert capsys.readouterr().err == ""


def test_warn_degraded_pickup_stderr_when_degraded(capsys: pytest.CaptureFixture[str]) -> None:
    warn_degraded_pickup(
        no_sync=True,
        no_push_registry=True,
        remote="origin",
        base="dev",
    )
    err = capsys.readouterr().err
    assert "warning: do-next-available-task:" in err
    assert "Others will not see your registry claim on origin/dev" in err
    assert "--no-sync" in err
    assert "--no-push-registry" in err


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
    monkeypatch.setattr(dnt, "_git", fake_git)
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
            "--no-sync",
            "--no-push-registry",
            "--no-ci-skip-in-message",
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert calls[1][0] == "commit"
    assert calls[1][2] == "chore(rm-pickup-git): register as in-progress"
