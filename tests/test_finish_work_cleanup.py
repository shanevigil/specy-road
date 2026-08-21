"""Tests for finish-this-task work/ artifact cleanup."""

from __future__ import annotations

import subprocess

from specy_road.finish_work_artifacts import (
    cleanup_work_artifacts,
    warn_if_pr_body_tracked,
    work_artifact_rel_paths,
)
from specy_road.git_workflow_config import (
    cleanup_work_artifacts_on_finish,
    should_cleanup_work_artifacts_on_finish,
)


def test_work_artifact_rel_paths() -> None:
    assert work_artifact_rel_paths("M1.1") == (
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
    tracked = cleanup_work_artifacts(tmp_path, "M1.1")
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
    tracked = cleanup_work_artifacts(tmp_path, "M1.1")
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


def _init_repo(root) -> None:
    for args in (
        ["init"],
        ["config", "user.email", "a@b.c"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_pr_body_warning_fires_for_snapshots_from_earlier_tasks(tmp_path, capsys) -> None:
    """The repos that need this warning never track the node being finished.

    Its snapshot was written moments ago, so it is not in the index; what a
    pre-ignore-rule repo carries is committed snapshots from previous tasks.
    """
    _init_repo(tmp_path)
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "pr-body-M1.1.md").write_text("old", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "-f", "work/pr-body-M1.1.md"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "legacy snapshot"],
        check=True, capture_output=True,
    )
    # A different node is being finished now; its snapshot is untracked.
    (tmp_path / "work" / "pr-body-M2.7.md").write_text("new", encoding="utf-8")

    warn_if_pr_body_tracked(tmp_path)
    err = capsys.readouterr().err
    assert "work/pr-body-*.md" in err
    assert "git rm --cached" in err


def test_pr_body_warning_silent_when_nothing_is_tracked(tmp_path, capsys) -> None:
    _init_repo(tmp_path)
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "pr-body-M1.1.md").write_text("x", encoding="utf-8")
    warn_if_pr_body_tracked(tmp_path)
    assert capsys.readouterr().err == ""
