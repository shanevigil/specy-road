"""mark-implementation-reviewed enforces the review gate from orchestration policy."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import git, make_review_repo, review_text
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


def test_yes_without_reviews_refuses(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "--yes") == 1
    err = capsys.readouterr().err
    assert "review gate is not met" in err
    assert "--yes only commits an approval" in err
    assert _review_state(repo) == "pending"


def test_yes_with_recorded_reviews_commits_with_trailers(tmp_path: Path) -> None:
    repo = _repo(tmp_path, orchestration=TWO_FAMILIES)
    impl = git(repo, "rev-parse", "HEAD")
    _record(repo, "opus")
    _record(repo, "sol")
    assert _run(repo, "--yes") == 0
    assert _review_state(repo) == "approved"
    msg = git(repo, "log", "-1", "--format=%B")
    assert f"Reviewed-by: opus (anthropic) approve {impl}" in msg
    assert f"Reviewed-by: sol (openai) approve {impl}" in msg
    # The gate's own registry-only commit does not make the reviews stale.
    target = resolve_target(repo, "M1.1", "HEAD")
    assert target.commit == impl
    assert evaluate_gate(repo, target.node, target.commit).passed


def test_interactive_human_approval_files_a_record(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "a")
    assert _run(repo) == 0
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
