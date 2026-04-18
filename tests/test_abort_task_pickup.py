"""Tests for abort-task-pickup (undo do-next-available-task)."""

from __future__ import annotations

import yaml
import pytest

import abort_task_pickup as atp


def test_abort_refuses_dirty_tree(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(atp, "_working_tree_clean", lambda: False)
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_abort_refuses_non_feature_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(atp, "_working_tree_clean", lambda: True)
    monkeypatch.setattr(atp, "_current_branch", lambda: "main")
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_abort_refuses_ahead_of_remote_without_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(atp, "_working_tree_clean", lambda: True)
    monkeypatch.setattr(atp, "_current_branch", lambda: "feature/rm-x")
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: (
            "x",
            {"version": 1, "entries": []},
            {"node_id": "M1.1"},
            [],
        ),
    )
    monkeypatch.setattr(atp, "_git", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 2)
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_abort_pickup_git_order(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_git(*args: str) -> None:
        calls.append(list(args))

    branches = iter(["feature/rm-ab", "dev"])

    def fake_branch() -> str:
        return next(branches)

    reg_doc = {
        "version": 1,
        "entries": [
            {
                "codename": "ab",
                "node_id": "M9.1",
                "branch": "feature/rm-ab",
                "touch_zones": ["src/"],
            }
        ],
    }
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        yaml.dump(reg_doc),
        encoding="utf-8",
    )

    monkeypatch.setattr(atp, "_working_tree_clean", lambda: True)
    monkeypatch.setattr(atp, "_current_branch", fake_branch)
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: ("ab", reg_doc, {"node_id": "M9.1"}, []),
    )
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 0)
    monkeypatch.setattr(atp, "_sync_integration_branch_ff", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_git", fake_git)
    monkeypatch.setattr(atp, "_delete_feature_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_remove_pickup_work_files", lambda *_a, **_k: None)

    atp.main(["--repo-root", str(tmp_path)])

    assert calls[0] == ["fetch", "origin"]
    assert calls[1] == ["add", "roadmap/registry.yaml"]
    assert calls[2][0] == "commit"
    assert "abort task pickup" in calls[2][2]
    assert calls[3] == ["push", "origin", "main"]


def test_abort_allows_ahead_with_force(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[str] = []

    def fake_git(*args: str) -> None:
        calls.append(args[0])

    branches = iter(["feature/rm-ab", "dev"])

    def fake_branch() -> str:
        return next(branches)

    reg_doc = {
        "version": 1,
        "entries": [
            {
                "codename": "ab",
                "node_id": "M9.1",
                "branch": "feature/rm-ab",
                "touch_zones": ["src/"],
            }
        ],
    }
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        yaml.dump(reg_doc),
        encoding="utf-8",
    )

    monkeypatch.setattr(atp, "_working_tree_clean", lambda: True)
    monkeypatch.setattr(atp, "_current_branch", fake_branch)
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: (
            "ab",
            {"version": 1, "entries": []},
            {"node_id": "M9.1"},
            [],
        ),
    )
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 3)
    monkeypatch.setattr(atp, "_sync_integration_branch_ff", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_git", fake_git)
    monkeypatch.setattr(atp, "_delete_feature_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_remove_pickup_work_files", lambda *_a, **_k: None)

    atp.main(["--repo-root", str(tmp_path), "--force"])

    assert "push" in calls
