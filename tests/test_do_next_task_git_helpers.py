"""Tests for the shared repo git helpers, and do_next_task's use of them."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts import repo_ops


def test_sync_integration_branch_git_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_git(_root: Path, *args: str) -> None:
        calls.append(list(args))

    monkeypatch.setattr(repo_ops, "assert_working_tree_clean", lambda *_a, **_k: None)
    monkeypatch.setattr(repo_ops, "git_run", fake_git)
    repo_ops.sync_integration_branch(
        Path("."), "main", "origin", retry_hint="retry do-next-available-task"
    )
    assert calls == [
        ["fetch", "origin"],
        ["checkout", "main"],
        ["merge", "--ff-only", "origin/main"],
    ]


def test_assert_current_branch_equals_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dnt, "current_branch", lambda _root: "dev")
    dnt._assert_current_branch_equals("dev")


def test_assert_current_branch_equals_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dnt, "current_branch", lambda _root: "other")
    with pytest.raises(SystemExit):
        dnt._assert_current_branch_equals("dev")


def test_assert_current_branch_equals_detached_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dnt, "current_branch", lambda _root: "HEAD")
    with pytest.raises(SystemExit):
        dnt._assert_current_branch_equals("main")


# F-009: _validate_touch_zones was removed (touch_zones are optional; the
# agent prompt instructs the implementer to discover them). Test deleted.


def test_working_tree_clean_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repo_ops, "git_checked", lambda *_a, **_k: "")
    assert repo_ops.working_tree_clean(Path(".")) is True


def test_working_tree_clean_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repo_ops, "git_checked", lambda *_a, **_k: "M foo")
    assert repo_ops.working_tree_clean(Path(".")) is False
