"""Tests for finish-this-task work/ artifact cleanup."""

from __future__ import annotations

import shutil
import subprocess

from specy_road.finish_work_artifacts import (
    cleanup_work_artifacts,
    warn_if_pr_body_tracked,
    work_artifact_rel_paths,
    worker_logs_to_stage,
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


def test_cleanup_work_artifacts_removes_untracked_files(tmp_path, capsys) -> None:
    root, outside = tmp_path / "app", tmp_path / "outside"
    (root / "work").mkdir(parents=True)
    for name in (
        "brief-M1.1.md",
        "prompt-M1.1.md",
        "implementation-summary-M1.1.md",
    ):
        (root / "work" / name).write_text("x", encoding="utf-8")
    tracked = cleanup_work_artifacts(root, "M1.1")
    assert tracked == []
    for name in (
        "brief-M1.1.md",
        "prompt-M1.1.md",
        "implementation-summary-M1.1.md",
    ):
        assert not (root / "work" / name).is_file()
    # never committed, so the reviewed summary survives beside the reviews
    kept = root / "work" / "reviews" / "M1.1" / "implementation-summary-M1.1.md"
    assert kept.read_text(encoding="utf-8") == "x"
    kept.unlink()
    # a summary reached through a symlink -- the file, or work/ itself -- is never copied
    outside.mkdir()
    (outside / "implementation-summary-M1.1.md").write_text("secret", encoding="utf-8")
    (root / "work" / "implementation-summary-M1.1.md").symlink_to(outside / "implementation-summary-M1.1.md")
    cleanup_work_artifacts(root, "M1.1")
    assert "not copying" in capsys.readouterr().err and not kept.exists()
    shutil.rmtree(root / "work")
    (root / "work").symlink_to(outside)
    cleanup_work_artifacts(root, "M1.1")
    assert "not copying" in capsys.readouterr().err and not (outside / "reviews").exists()


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


def _logs_repo(root, mode: str | None) -> None:
    _init_repo(root)
    (root / "roadmap").mkdir()
    (root / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n"
        + (f"track_worker_logs: {mode}\n" if mode else ""),
        encoding="utf-8",
    )
    logs = root / "work" / "worker-logs" / "M1.1"
    logs.mkdir(parents=True)
    (logs / "w-0001.events.jsonl").write_text('{"seq": 1}\n', encoding="utf-8")


def test_worker_logs_are_staged_when_tracked_and_survive_cleanup(tmp_path) -> None:
    _logs_repo(tmp_path, '"events"')
    staged = worker_logs_to_stage(tmp_path, "M1.1")
    assert staged == ["work/worker-logs/M1.1"]
    cleanup_work_artifacts(tmp_path, "M1.1")   # the session documents go; the logs are not among them
    assert (tmp_path / "work" / "worker-logs" / "M1.1" / "w-0001.events.jsonl").is_file()
    subprocess.run(["git", "-C", str(tmp_path), "add", *staged], check=True, capture_output=True)
    names = subprocess.run(["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"],
                           check=True, capture_output=True, text=True).stdout.split()
    assert names == ["work/worker-logs/M1.1/w-0001.events.jsonl"]


def test_worker_logs_are_not_staged_when_off_or_absent(tmp_path) -> None:
    for i, mode in enumerate((None, "off", '"off"')):   # absent, bare (YAML false), quoted
        root = tmp_path / f"r{i}"
        root.mkdir()
        _logs_repo(root, mode)
        assert worker_logs_to_stage(root, "M1.1") == []
        assert worker_logs_to_stage(root, "M9.9") == []


def test_worker_logs_a_consumer_ignores_are_skipped_with_a_warning(tmp_path, capsys) -> None:
    _logs_repo(tmp_path, '"full"')
    (tmp_path / ".gitignore").write_text("/work/*\n", encoding="utf-8")
    assert worker_logs_to_stage(tmp_path, "M1.1") == []
    assert "!work/worker-logs/" in capsys.readouterr().err


READY_WRITER = """import sys
open(sys.argv[1], "w").write(sys.argv[2])
print("done", flush=True)
"""


def _status(check: str, where) -> str:
    return subprocess.run(check, shell=True, cwd=where, capture_output=True, text=True, check=True).stdout


def test_an_opted_in_completed_worker_goes_through_review_to_finish(tmp_path, monkeypatch, capsys) -> None:
    """R1: the logs the wrapper mirrors after READY pass both clean-tree checks, and finish commits them."""
    import re
    import sys

    import pytest

    from tests.helpers import REPO
    from tests.review_repo_helpers import make_review_repo, review_text
    from tests.test_prerelease_s2 import ROSTER

    from specy_road import worker_adapters as wa
    from specy_road import worker_runner as wr
    from specy_road import worker_state as ws
    from specy_road.agent_ignores import apply_agent_ignores
    from specy_road.bundled_scripts import finish_task
    from specy_road.bundled_scripts import mark_implementation_reviewed as mir
    from specy_road.bundled_scripts.role_prompt import build_prompt
    from specy_road.bundled_scripts.role_prompt_rca import precondition
    from specy_road.review_files import PACKET_NAME, reviews_dir
    from specy_road.review_target import resolve_target

    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    apply_agent_ignores(repo)
    (repo / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n"
        "require_implementation_review_before_finish: true\ntrack_worker_logs: \"events\"\n", encoding="utf-8")
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Added\n\nnone\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "executor: summary"], check=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    ready = reviews_dir(repo, "M1.1") / "READY-exec.md"
    ready.parent.mkdir(parents=True)
    script = tmp_path / "ready.py"
    script.write_text(READY_WRITER)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "dev"], check=True,
                          capture_output=True, text=True).stdout.strip()
    text = (f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\ncommit: \"{head}\"\n"
            f"base: \"{base}\"\nchanged_paths: [src/a.py]\n---\n")
    rec = ws.create_record(repo, "M1.1", "generic", "exec", repo, branch="feature/rm-thing")
    wr.run(repo, rec.worker_id, wa.Launch([sys.executable, str(script), str(ready), text]))
    assert ws.load_record(repo, rec.worker_id).state == "completed"
    logs = f"work/worker-logs/M1.1/{rec.worker_id}.events.jsonl"
    assert (repo / logs).is_file()   # written after READY, as R1 found

    (reviews_dir(repo, "M1.1") / PACKET_NAME).write_text("# packet\n")
    prompt, _prof, err = build_prompt(repo, "M1.1", role="reviewer", model="rev")
    assert err is None
    reviewer = re.search(r"or `(git status [^`]+)` lists changes you did not make", prompt).group(1)
    executor = re.search(r"or `(git status [^`]+)` lists changes you did not make",
                         "\n".join(precondition("executor", "M1.1", resolve_target(repo, "M1.1"), tmp_path))).group(1)
    assert _status(reviewer, repo) == "" and _status(executor, repo) == ""
    stray = repo / "work" / "worker-logs" / "M1.2" / "w-0009.events.jsonl"   # another leaf's logs still count
    stray.parent.mkdir(parents=True)
    stray.write_text("{}\n")
    assert "work/worker-logs/M1.2/" in _status(reviewer, repo) and "work/worker-logs/M1.2/" in _status(executor, repo)
    stray.unlink()
    stray.parent.rmdir()

    (reviews_dir(repo, "M1.1") / "REVIEW-human.md").write_text(review_text(head))
    with pytest.raises(SystemExit) as e:
        mir.main(["--yes", "--repo-root", str(repo)])
        raise SystemExit(0)
    assert (e.value.code or 0) == 0
    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])
        raise SystemExit(0)
    assert (e.value.code or 0) == 0, capsys.readouterr().err
    committed = subprocess.run(["git", "-C", str(repo), "show", "--name-only", "--format=%s", "HEAD"],
                               check=True, capture_output=True, text=True).stdout
    assert committed.startswith("chore(rm-thing): complete, deregister") and logs in committed
