"""From a linked worktree, every review command uses the main checkout's ``work/reviews/<ID>/``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo, review_text
from tests.test_prerelease_s2 import ROSTER

from specy_road.bundled_scripts import review_cli, review_packet
from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir, reviews_root


def _linked(tmp_path: Path) -> tuple[Path, Path]:
    """``(main checkout on dev, linked worktree on the feature branch)``."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    return repo, wt


def _cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def test_packet_record_and_status_agree_from_a_linked_worktree(tmp_path: Path, capsys, monkeypatch) -> None:
    repo, wt = _linked(tmp_path)
    main_dir = repo / "work" / "reviews" / "M1.1"
    monkeypatch.chdir(wt)
    review_packet.main(["M1.1", "--repo-root", str(wt)])
    assert (main_dir / PACKET_NAME).is_file()
    head = git(wt, "rev-parse", "HEAD")
    # The executor's hand-off, where its prompt says: the main checkout's directory.
    (main_dir / "READY-x.md").write_text(
        f"---\nnode_id: M1.1\nagent: x\nbranch: feature/rm-thing\ncommit: {head}\n"
        f"base: {git(wt, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n")
    notes = main_dir / "notes-rev.md"
    notes.write_text(review_text(head, model="rev"))
    assert _cli("review", "record", "M1.1", "--model", "rev", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(wt)) == 0
    assert (main_dir / "REVIEW-rev.md").is_file()
    capsys.readouterr()
    assert _cli("handoff", "status", "M1.1", "--json", "--repo-root", str(wt)) == 0
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert [r["file"] for r in st["ready"]] == ["READY-x.md"]
    assert [r["file"] for r in st["reviews"]] == ["REVIEW-rev.md"] and st["state"] == "approved"
    assert not (wt / "work" / "reviews").exists()   # nothing read or written in the worktree's own copy


def test_the_directory_resolves_when_git_cannot_run(tmp_path: Path, monkeypatch) -> None:
    repo, wt = _linked(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "no-git"))   # a sandbox git refuses to serve
    assert reviews_root(wt) == reviews_root(repo).resolve()
    assert reviews_root(repo) == repo / "work" / "reviews"


def test_the_reviewer_prompt_names_the_writable_root(tmp_path: Path) -> None:
    repo, wt = _linked(tmp_path)
    d = reviews_dir(wt, "M1.1")
    d.mkdir(parents=True)
    (d / PACKET_NAME).write_text("# packet\n")
    text, _prof, err = build_prompt(wt, "M1.1", role="reviewer", model="rev")
    assert err is None
    assert f"**Writable root:** `{repo.resolve() / 'work' / 'reviews' / 'M1.1'}`" in text
