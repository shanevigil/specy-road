"""mark-implementation-reviewed enforces the review gate from orchestration policy."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import diverge, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.review_files import review_path, reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_target import resolve_target


def _repo(tmp_path: Path, **kw) -> Path:
    repo = make_review_repo(tmp_path, **kw)
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    return repo


def _run(repo: Path, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        mir.main([*args, "--repo-root", str(repo)])
        raise SystemExit(0)
    return e.value.code or 0


def _review_state(repo: Path) -> str:
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())
    return reg["entries"][0]["implementation_review"]


def _record(repo: Path, model: str) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model))


def _failing_ready(repo: Path) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-exec.md").write_text(
        f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\n"
        f"commit: {git(repo, 'rev-parse', 'HEAD')}\nbase: {git(repo, 'rev-parse', 'dev')}\n"
        "changed_paths: [src/a.py]\nverify:\n  - {cmd: 'false', exit: 1, tail: boom}\n---\n"
    )


def test_yes_without_reviews_refuses(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "--yes") == 1
    err = capsys.readouterr().err
    assert "review gate is not met" in err
    assert "--yes only commits an approval" in err
    assert _review_state(repo) == "pending"


def test_yes_with_recorded_reviews_commits_with_trailers(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path, orchestration=TWO_FAMILIES)
    impl = git(repo, "rev-parse", "HEAD")
    _record(repo, "opus")
    _record(repo, "sol")
    assert _run(repo, "--yes") == 0
    out = capsys.readouterr().out
    assert "Summary file: work/implementation-summary-M1.1.md" in out and "Did it." not in out   # nobody reads it
    assert _review_state(repo) == "approved"
    msg = git(repo, "log", "-1", "--format=%B")
    assert f"Reviewed-by: opus (anthropic) approve {impl}" in msg
    assert f"Reviewed-by: sol (openai) approve {impl}" in msg
    # The gate's own registry-only commit does not make the reviews stale.
    target = resolve_target(repo, "M1.1", "HEAD")
    assert target.commit == impl
    assert evaluate_gate(repo, target.node, target.commit).passed


def test_interactive_human_approval_files_a_record(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "a")
    assert _run(repo) == 0
    assert "Did it." in capsys.readouterr().out   # the human approving reads the summary
    assert review_path(repo, "M1.1", "human").is_file()
    assert _review_state(repo) == "approved"
    assert "Reviewed-by: human (human) approve" in git(repo, "log", "-1", "--format=%B")


def test_interactive_quit_leaves_everything_unchanged(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")
    assert _run(repo) == 0
    assert not review_path(repo, "M1.1", "human").exists()
    assert _review_state(repo) == "pending"


def test_human_cannot_stand_in_for_a_missing_second_family(tmp_path: Path, monkeypatch, capsys) -> None:
    """With two distinct families required and none recorded, one human cannot close it."""
    repo = _repo(tmp_path, orchestration=TWO_FAMILIES)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def _no_prompt(_prompt: str = "") -> str:
        raise AssertionError("must not prompt")

    monkeypatch.setattr("builtins.input", _no_prompt)
    assert _run(repo) == 1
    assert "need 2 distinct-family approvals" in capsys.readouterr().out
    assert _review_state(repo) == "pending"


def test_human_completes_the_second_family(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, orchestration=TWO_FAMILIES)
    _record(repo, "opus")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "a")
    assert _run(repo) == 0
    assert _review_state(repo) == "approved"


def test_finish_refuses_work_committed_after_approval(tmp_path: Path, monkeypatch, capsys) -> None:
    """A fix restarts review: an approved registry row does not cover later commits."""
    from specy_road.bundled_scripts import finish_task as ft
    from tests.review_repo_helpers import NODE, commit_file

    repo = _repo(tmp_path)
    _record(repo, "human")
    assert _run(repo, "--yes") == 0
    monkeypatch.setattr(ft, "ROOT", repo)
    entry = {"implementation_review": "approved"}
    ft._impl_review_or_exit(entry, NODE)  # the gate commit alone does not count as new work

    commit_file(repo, "src/late.py", "x\n", "late change")
    with pytest.raises(SystemExit) as e:
        ft._impl_review_or_exit(entry, NODE)
    assert e.value.code == 1
    assert "no longer holds at this commit" in capsys.readouterr().err


def test_yes_refuses_a_failing_ready_verifier(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    _record(repo, "human")
    _failing_ready(repo)
    assert _run(repo, "--yes") == 1
    captured = capsys.readouterr()
    assert "review gate is not met" in captured.err
    assert "verifier `false` exited 1" in captured.out
    assert _review_state(repo) == "pending"


def _blocked_on_ready(repo: Path) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-exec.md").write_text(
        f"---\nnode_id: M1.1\nagent: exec\nbranch: feature/rm-thing\n"
        f"commit: {git(repo, 'rev-parse', 'HEAD')}\nbase: {git(repo, 'rev-parse', 'dev')}\n"
        "changed_paths: [src/a.py]\nverify:\n  - {cmd: pytest, exit: 0}\n"
        "blocked_on:\n  - {acceptance: A1, reason: cannot meet without weakening tests}\n---\n"
    )


def test_yes_refuses_while_ready_declares_blocked_on(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    _record(repo, "human")
    _blocked_on_ready(repo)
    assert _run(repo, "--yes") == 1
    captured = capsys.readouterr()
    assert "review gate is not met" in captured.err
    assert "blocked on A1" in captured.out
    assert _review_state(repo) == "pending"


def test_finish_refuses_a_failing_ready_verifier(tmp_path: Path, monkeypatch, capsys) -> None:
    from specy_road.bundled_scripts import finish_task as ft
    from tests.review_repo_helpers import NODE

    repo = _repo(tmp_path)
    _record(repo, "human")
    _failing_ready(repo)
    monkeypatch.setattr(ft, "ROOT", repo)
    with pytest.raises(SystemExit) as e:
        ft._impl_review_or_exit({"implementation_review": "approved"}, NODE)
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "no longer holds at this commit" in err
    assert "verifier `false` exited 1" in err


def test_finish_refuses_while_ready_declares_blocked_on(tmp_path: Path, monkeypatch, capsys) -> None:
    from specy_road.bundled_scripts import finish_task as ft
    from tests.review_repo_helpers import NODE

    repo = _repo(tmp_path)
    _record(repo, "human")
    _blocked_on_ready(repo)
    monkeypatch.setattr(ft, "ROOT", repo)
    with pytest.raises(SystemExit) as e:
        ft._impl_review_or_exit({"implementation_review": "approved"}, NODE)
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "no longer holds at this commit" in err
    assert "blocked on A1" in err


@pytest.mark.parametrize("case", ["clean", "bookkeeping", "code"])
def test_yes_refuses_while_a_trial_merge_conflicts_on_code(tmp_path: Path, capsys, case: str) -> None:
    repo = _repo(tmp_path, orchestration=TWO_FAMILIES)
    diverge(repo, case)
    _record(repo, "opus")
    _record(repo, "sol")
    head = git(repo, "rev-parse", "HEAD")
    refused = case == "code"
    assert _run(repo, "--yes") == (1 if refused else 0)
    assert ("trial merge conflicts on src/a.py" in capsys.readouterr().err) == refused
    assert _review_state(repo) == ("pending" if refused else "approved")
    assert (git(repo, "rev-parse", "HEAD") == head) == refused   # no bookkeeping commit when refused
