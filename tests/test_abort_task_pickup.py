"""Tests for abort-task-pickup (undo do-next-available-task)."""

from __future__ import annotations

import yaml
import pytest

import abort_task_pickup as atp


def _claimed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A feature branch with a resolvable registry claim."""
    monkeypatch.setattr(atp, "current_branch", lambda _root: "feature/rm-ab")
    monkeypatch.setattr(
        atp,
        "resolve_feature_rm_registry_context",
        lambda *_a, **_k: ("ab", {"version": 1, "entries": []}, {"node_id": "M9.1"}, []),
    )
    monkeypatch.setattr(
        atp,
        "resolve_integration_defaults",
        lambda *_a, **_k: ("main", "origin", []),
    )


def test_abort_refuses_dirty_tree(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _claimed(monkeypatch)
    monkeypatch.setattr(atp, "_dirty_entries", lambda *_a, **_k: [" M src/app.py"])
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_pickup_artifacts_do_not_block_abort() -> None:
    """An immediate pickup->abort must work: pickup writes these itself.

    The scaffold deliberately does not gitignore the brief, so a fresh pickup
    always leaves untracked files that abort is about to delete anyway.
    """
    ignore = atp._pickup_artifact_rel_paths("M9.1")
    assert ignore == {
        "work/brief-M9.1.md",
        "work/prompt-M9.1.md",
        "work/implementation-summary-M9.1.md",
        "work/.on-complete-M9.1.yaml",
    }


def test_dirty_entries_filters_only_the_listed_untracked_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    porcelain = (
        "?? work/brief-M9.1.md\n"
        "?? work/notes.txt\n"
        " M src/app.py\n"
    )

    class _R:
        stdout = porcelain

    monkeypatch.setattr(atp.subprocess, "run", lambda *_a, **_k: _R())
    blocking = atp._dirty_entries({"work/brief-M9.1.md"})
    assert blocking == ["?? work/notes.txt", " M src/app.py"]


def test_abort_refuses_non_feature_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(atp, "_dirty_entries", lambda *_a, **_k: [])
    monkeypatch.setattr(atp, "current_branch", lambda _root: "main")
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
    monkeypatch.setattr(atp, "_dirty_entries", lambda *_a, **_k: [])
    monkeypatch.setattr(atp, "current_branch", lambda _root: "feature/rm-x")
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
    monkeypatch.setattr(atp, "git_run", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_count_commits_ahead_of_remote_base", lambda *_a, **_k: 2)
    with pytest.raises(SystemExit):
        atp.main(["--repo-root", str(tmp_path)])


def test_abort_pickup_git_order(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_git(_root, *args: str) -> None:
        calls.append(list(args))

    branches = iter(["feature/rm-ab", "dev"])

    def fake_branch(_root) -> str:
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

    monkeypatch.setattr(atp, "_dirty_entries", lambda *_a, **_k: [])
    monkeypatch.setattr(atp, "current_branch", fake_branch)
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
    monkeypatch.setattr(atp, "git_run", fake_git)
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

    def fake_git(_root, *args: str) -> None:
        calls.append(args[0])

    branches = iter(["feature/rm-ab", "dev"])

    def fake_branch(_root) -> str:
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

    monkeypatch.setattr(atp, "_dirty_entries", lambda *_a, **_k: [])
    monkeypatch.setattr(atp, "current_branch", fake_branch)
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
    monkeypatch.setattr(atp, "git_run", fake_git)
    monkeypatch.setattr(atp, "_delete_feature_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(atp, "_remove_pickup_work_files", lambda *_a, **_k: None)

    atp.main(["--repo-root", str(tmp_path), "--force"])

    assert "push" in calls
