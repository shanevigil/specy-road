"""Tests for finish-this-task work/ artifact cleanup."""

from __future__ import annotations

import subprocess

import finish_task as ft
from specy_road.git_workflow_config import (
    cleanup_work_artifacts_on_finish,
    should_cleanup_work_artifacts_on_finish,
)


def test_work_artifact_rel_paths() -> None:
    assert ft._work_artifact_rel_paths("M1.1") == (
        "work/brief-M1.1.md",
        "work/prompt-M1.1.md",
        "work/implementation-summary-M1.1.md",
    )


def test_cleanup_work_artifacts_removes_untracked_files(tmp_path) -> None:
    (tmp_path / "work").mkdir(parents=True)
    for name in (
        "brief-M1.1.md",
        "prompt-M1.1.md",
        "implementation-summary-M1.1.md",
    ):
        (tmp_path / "work" / name).write_text("x", encoding="utf-8")
    tracked = ft._cleanup_work_artifacts(tmp_path, "M1.1")
    assert tracked == []
    for name in (
        "brief-M1.1.md",
        "prompt-M1.1.md",
        "implementation-summary-M1.1.md",
    ):
        assert not (tmp_path / "work" / name).is_file()


def test_cleanup_work_artifacts_tracked_paths_returned(tmp_path) -> None:
    (tmp_path / "work").mkdir(parents=True)
    (tmp_path / "work" / "brief-M1.1.md").write_text("a", encoding="utf-8")
    (tmp_path / "work" / "prompt-M1.1.md").write_text("b", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "a@b.c"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "t"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "work/brief-M1.1.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    tracked = ft._cleanup_work_artifacts(tmp_path, "M1.1")
    assert set(tracked) == {"work/brief-M1.1.md"}
    assert not (tmp_path / "work" / "brief-M1.1.md").is_file()
    assert not (tmp_path / "work" / "prompt-M1.1.md").is_file()


def test_cleanup_work_artifacts_on_finish_defaults_true(tmp_path) -> None:
    assert cleanup_work_artifacts_on_finish(tmp_path) is True


def test_cleanup_work_artifacts_on_finish_false_in_yaml(tmp_path) -> None:
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\n"
        "integration_branch: main\n"
        "remote: origin\n"
        "cleanup_work_artifacts_on_finish: false\n",
        encoding="utf-8",
    )
    assert cleanup_work_artifacts_on_finish(tmp_path) is False


def test_should_cleanup_work_artifacts_cli_overrides_yaml(tmp_path) -> None:
    (tmp_path / "roadmap").mkdir(parents=True)
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\n"
        "integration_branch: main\n"
        "remote: origin\n"
        "cleanup_work_artifacts_on_finish: false\n",
        encoding="utf-8",
    )
    assert should_cleanup_work_artifacts_on_finish(
        tmp_path,
        no_cleanup_work_cli=False,
    ) is False
    assert should_cleanup_work_artifacts_on_finish(
        tmp_path,
        no_cleanup_work_cli=True,
    ) is False
    (tmp_path / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\n"
        "integration_branch: main\n"
        "remote: origin\n"
        "cleanup_work_artifacts_on_finish: true\n",
        encoding="utf-8",
    )
    assert should_cleanup_work_artifacts_on_finish(
        tmp_path,
        no_cleanup_work_cli=True,
    ) is False
    assert should_cleanup_work_artifacts_on_finish(
        tmp_path,
        no_cleanup_work_cli=False,
    ) is True
