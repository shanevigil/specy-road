"""Tests for git helpers inside ``do_next_task``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import do_next_task as dnt


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


def test_assert_current_branch_equals_detached_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dnt, "_current_branch", lambda: "HEAD")
    with pytest.raises(SystemExit):
        dnt._assert_current_branch_equals("main")


def test_validate_touch_zones_empty_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    node = {"id": "M1.1", "codename": "x", "touch_zones": []}
    with pytest.raises(SystemExit):
        dnt._validate_touch_zones(node)


def test_working_tree_clean_true() -> None:
    with patch.object(
        dnt.subprocess,
        "run",
        return_value=__import__("types").SimpleNamespace(stdout="", returncode=0),
    ):
        assert dnt._working_tree_clean() is True


def test_working_tree_clean_false() -> None:
    with patch.object(
        dnt.subprocess,
        "run",
        return_value=__import__("types").SimpleNamespace(stdout=" M foo\n", returncode=0),
    ):
        assert dnt._working_tree_clean() is False
