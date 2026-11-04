"""M11.22: merge-mode finish lands the leaf's nested branches first; the gate and review-packet see them.

Fixture: the review repo (``dev``, ``feature/rm-thing`` with zones ``src``) with
a bare ``origin``, and one nested repository (``tests/test_nested_repo_worktrees``)
that has the leaf's branch with one commit.
"""

from __future__ import annotations

from pathlib import Path

import shutil

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo
from tests.test_nested_repo_worktrees import COVERED, UNCOVERED, add_nested_repo

from specy_road.bundled_scripts import review_packet as rp
from specy_road.finish_implementation_check import implementation_paths
from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.nested_repos import land_nested_branches

BRANCH = "feature/rm-thing"


def _repos(tmp_path: Path, *rels: str, text: str = "x = 2\n") -> tuple[Path, list[Path]]:
    """``(repo on the feature branch, each nested repo on dev with the leaf branch committed)``; the leaf's
    ``core.py`` is ``text``, prefixed with the repository's path so each diff is its own."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    nested = [add_nested_repo(repo, rel, "dev") for rel in rels]
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    for rel, n in zip(rels, nested):
        git(n, "checkout", "-q", "-b", BRANCH)
        commit_file(n, "core.py", (f"# {rel}\n" if len(rels) > 1 else "") + text, "leaf work in the nested repo")
        git(n, "checkout", "-q", "dev")
    return repo, nested


def _repo(tmp_path: Path, rel: str = COVERED, text: str = "x = 2\n") -> tuple[Path, Path]:
    repo, (nested,) = _repos(tmp_path, rel, text=text)
    return repo, nested


def _origin_tip(repo: Path, branch: str = "dev") -> str:
    return git(repo, "ls-remote", "origin", f"refs/heads/{branch}").split()[0]


def _land(repo: Path) -> tuple[bool, str]:
    return land_merge_feature_into_integration(repo, remote="origin", integration_branch="dev",
                                               feature_branch=BRANCH, land_check_cmd="")


def test_merge_mode_lands_the_nested_branch_then_the_main_repository(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    ok, err = _land(repo)
    assert ok, err
    git(nested, "fetch", "-q", "origin")
    assert git(nested, "merge-base", "--is-ancestor", BRANCH, "origin/dev") == ""
    assert git(nested, "branch", "--show-current") == "dev"   # no checkout of the nested repo moved
    assert git(repo, "merge-base", "--is-ancestor", BRANCH, _origin_tip(repo)) == ""
    # A re-run lands nothing twice in the nested repository.
    tip = _origin_tip(nested)
    assert land_nested_branches(repo, BRANCH) == (True, "")
    assert _origin_tip(nested) == tip


def test_a_nested_conflict_stops_before_the_main_repository_moves(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    commit_file(nested, "core.py", "x = 99\n", "dev moves on in the nested repo")
    git(nested, "push", "-q", "origin", "dev")
    nested_before, main_before = _origin_tip(nested), _origin_tip(repo)
    ok, err = _land(repo)
    assert not ok
    assert f"nested repo {COVERED!r}" in err and "main repository was not merged" in err
    assert _origin_tip(nested) == nested_before and _origin_tip(repo) == main_before
    assert git(repo, "branch", "--show-current") == BRANCH
    assert len(git(nested, "worktree", "list").splitlines()) == 1   # the temporary worktree is gone


def test_a_configured_repo_that_is_gone_stops_the_landing_before_the_main_repository(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    main_before = _origin_tip(repo)
    shutil.rmtree(nested)   # whether it held the leaf's work can no longer be told
    ok, err = _land(repo)
    assert not ok
    assert f"nested repo {COVERED!r}" in err and "not the top of a git repository" in err
    assert "main repository was not merged" in err
    assert _origin_tip(repo) == main_before
    assert git(repo, "branch", "--show-current") == BRANCH


def test_a_repo_without_the_leaf_branch_is_left_alone(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    git(nested, "branch", "-q", "-D", BRANCH)
    tip = _origin_tip(nested)
    assert land_nested_branches(repo, BRANCH) == (True, "")
    assert _origin_tip(nested) == tip


def test_the_implementation_gate_counts_in_zone_work_in_a_nested_repo(tmp_path: Path) -> None:
    repo, _nested = _repo(tmp_path)
    # src/a.py on the main branch is outside this zone: only the nested work matches.
    assert implementation_paths(repo, zones=[COVERED], remote="origin", integration_branch="dev") == [
        f"{COVERED}/core.py"]


@pytest.mark.parametrize(("rel", "outside"), [(COVERED, False), (UNCOVERED, True)])
def test_review_packet_includes_the_nested_diff(tmp_path: Path, rel: str, outside: bool) -> None:
    repo, _nested = _repo(tmp_path, rel)
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    section = text.split("## Nested repositories", 1)[1].split("## Verifier output", 1)[0]
    line = next(ln for ln in section.splitlines() if ln.startswith(f"- `{rel}/core.py`"))
    assert ("outside touch zones" in line) is outside
    assert "+x = 2" in section and "-x = 1" in section


def test_review_packet_caps_a_long_nested_diff(tmp_path: Path) -> None:
    repo, _nested = _repo(tmp_path)
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=2)
    section = text.split("## Nested repositories", 1)[1]
    assert "Diff capped at 2 lines" in section
    patch = repo / "work" / "reviews" / "M1.1" / "DIFF-nested-src+engine.patch"
    assert "+x = 2" in patch.read_text(encoding="utf-8")


def test_review_packet_caps_a_long_single_line_nested_diff_by_bytes(tmp_path: Path) -> None:
    repo, _nested = _repo(tmp_path, text="x = '" + "a" * 5000 + "'\n")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=0, max_diff_bytes=100)
    section = text.split("## Nested repositories", 1)[1].split("## Verifier output", 1)[0]
    assert "Diff capped at 100 bytes" in section and "a" * 200 not in section
    patch = repo / "work" / "reviews" / "M1.1" / "DIFF-nested-src+engine.patch"
    assert "a" * 5000 in patch.read_text(encoding="utf-8")


def test_capped_nested_diffs_of_paths_that_flatten_alike_keep_their_own_patch(tmp_path: Path) -> None:
    repo, _nested = _repos(tmp_path, "a/b", "a-b")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], max_diff_lines=1)
    reviews = repo / "work" / "reviews" / "M1.1"
    for rel, name in (("a/b", "DIFF-nested-a+b.patch"), ("a-b", "DIFF-nested-a-b.patch")):
        assert f"`{reviews / name}`" in text
        assert f"+# {rel}\n" in (reviews / name).read_text(encoding="utf-8")


def test_review_packet_has_no_nested_section_without_the_config(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert "## Nested repositories" not in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
