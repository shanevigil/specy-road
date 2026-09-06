"""`specy-road sync` refreshes every generated file, and commits none of them."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts import pm_sync


def test_sync_runs_validate_export_and_digest_in_order(tmp_path: Path, monkeypatch) -> None:
    """digest belongs with the other two: sync exists to leave the tree current."""
    calls: list[list[str]] = []
    monkeypatch.setattr(pm_sync, "ROOT", tmp_path)
    monkeypatch.setattr(
        pm_sync.subprocess, "check_call", lambda argv, **_k: calls.append(list(argv))
    )

    pm_sync._validate_export_digest()

    assert [c[3] for c in calls] == ["validate", "export", "digest"]
    assert all(c[1:3] == ["-m", "specy_road.cli"] for c in calls)
    assert all(c[4:] == ["--repo-root", str(tmp_path)] for c in calls)


def test_sync_stages_and_commits_nothing(tmp_path: Path, monkeypatch) -> None:
    """The docs promise review-then-commit; nothing here may commit for you."""
    git_calls: list[tuple] = []
    monkeypatch.setattr(pm_sync, "ROOT", tmp_path)
    monkeypatch.setattr(
        pm_sync.subprocess, "check_call", lambda *_a, **_k: git_calls.append(_a)
    )

    pm_sync._validate_export_digest()

    flat = [arg for call in git_calls for arg in call[0]]
    assert "add" not in flat
    assert "commit" not in flat
