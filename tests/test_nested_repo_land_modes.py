"""M14.4.1: per nested repository ``land: push|local|manual`` and ``base: remote|local``.

Fixture: :func:`tests.test_nested_repo_finish._repo` (the review repo with a bare
``origin`` and one nested repository holding the leaf's branch), its
``nested_repos`` entry rewritten to the object form under test.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git, make_review_repo
from tests.test_nested_repo_finish import BRANCH, _land, _origin_tip, _repo
from tests.test_nested_repo_worktrees import COVERED, _cfg, add_nested_repo

from specy_road.finish_modes import merge_landing_failed
from specy_road.nested_repos import NestedRepo, NestedRepoError, add_nested_worktrees, nested_repos


def _configure(repo: Path, entry: str) -> None:
    """Replace the ``- src/engine`` entry with ``entry`` (YAML flow mapping) on the checked-out branch."""
    cfg = repo / "roadmap" / "git-workflow.yaml"
    text = cfg.read_text(encoding="utf-8")
    assert f"  - {COVERED}\n" in text
    commit_file(repo, "roadmap/git-workflow.yaml", text.replace(f"  - {COVERED}\n", f"  - {entry}\n"),
                "nested entry under test")


def test_schema_accepts_land_and_base_and_refuses_other_values() -> None:
    ok = {"path": "svc", "land": "local", "base": "local", "refuse_behind_remote": True}
    assert _cfg({"nested_repos": [ok, {"path": "web", "land": "manual", "base": "remote"}]}) is None
    for bad in ({"land": "pull"}, {"base": "upstream"}, {"refuse_behind_remote": "yes"}):
        assert _cfg({"nested_repos": [{"path": "svc", **bad}]}) is not None, bad


def test_entries_default_to_push_and_remote(tmp_path: Path) -> None:
    repo, _nested = _repo(tmp_path)
    assert nested_repos(repo) == [NestedRepo(COVERED, "dev", "origin", "push", "remote", False)]
    _configure(repo, f"{{path: {COVERED}, land: local, base: local, refuse_behind_remote: true}}")
    assert nested_repos(repo) == [NestedRepo(COVERED, "dev", "origin", "local", "local", True)]


def test_land_local_merges_into_the_local_branch_and_pushes_nothing(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    _configure(repo, f"{{path: {COVERED}, land: local}}")
    nested_remote = _origin_tip(nested)
    ok, err = _land(repo)
    assert ok, err
    assert _origin_tip(nested) == nested_remote   # no push in the nested repository
    assert git(nested, "merge-base", "--is-ancestor", BRANCH, "dev") == ""
    # dev is checked out (clean) there: the checkout moved with its ref.
    assert git(nested, "branch", "--show-current") == "dev" and git(nested, "status", "--porcelain") == ""
    assert (nested / "core.py").read_text(encoding="utf-8") == "x = 2\n"
    assert git(repo, "merge-base", "--is-ancestor", BRANCH, _origin_tip(repo)) == ""   # main still pushes
    assert len(git(nested, "worktree", "list").splitlines()) == 1


def test_land_local_moves_the_ref_when_the_branch_is_not_checked_out(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    _configure(repo, f"{{path: {COVERED}, land: local}}")
    git(nested, "checkout", "-q", "--detach")
    nested_remote, before = _origin_tip(nested), git(nested, "rev-parse", "dev")
    ok, err = _land(repo)
    assert ok, err
    assert _origin_tip(nested) == nested_remote
    merge = git(nested, "rev-parse", "dev")
    assert git(nested, "rev-parse", f"{merge}^1") == before and git(nested, "rev-parse", f"{merge}^2") == \
        git(nested, "rev-parse", BRANCH)


def test_land_local_refuses_a_dirty_checkout_of_the_integration_branch(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    _configure(repo, f"{{path: {COVERED}, land: local}}")
    (nested / "core.py").write_text("unsaved\n", encoding="utf-8")
    nested_remote, main_remote, dev = _origin_tip(nested), _origin_tip(repo), git(nested, "rev-parse", "dev")
    ok, err = _land(repo)
    assert not ok and "dev is checked out in" in err and "uncommitted changes" in err
    assert "main repository was not merged" in err
    assert _origin_tip(nested) == nested_remote and _origin_tip(repo) == main_remote
    assert git(nested, "rev-parse", "dev") == dev


def test_land_manual_stops_with_the_merge_command_then_proceeds_after_the_merge(tmp_path: Path) -> None:
    repo, nested = _repo(tmp_path)
    _configure(repo, f"{{path: {COVERED}, land: manual}}")
    nested_remote, main_remote, dev = _origin_tip(nested), _origin_tip(repo), git(nested, "rev-parse", "dev")
    ok, err = _land(repo)
    assert not ok
    assert f"git -C {nested} merge --no-ff {BRANCH}" in err and "re-run finish-this-task after merging" in err
    assert _origin_tip(nested) == nested_remote and _origin_tip(repo) == main_remote   # nothing pushed
    assert git(nested, "rev-parse", "dev") == dev and git(repo, "branch", "--show-current") == BRANCH
    git(nested, "merge", "-q", "--no-ff", "--no-edit", BRANCH)   # the merge it asked for
    ok, err = _land(repo)
    assert ok, err
    assert _origin_tip(nested) == nested_remote   # still never pushed
    assert git(repo, "merge-base", "--is-ancestor", BRANCH, _origin_tip(repo)) == ""


def test_finish_exits_1_with_the_manual_message(tmp_path: Path, capsys) -> None:
    repo, _nested = _repo(tmp_path)
    _configure(repo, f"{{path: {COVERED}, land: manual}}")
    ok, err = _land(repo)
    assert not ok
    with pytest.raises(SystemExit) as exc:
        merge_landing_failed("dev", err)
    assert exc.value.code == 1
    assert "re-run finish-this-task after merging" in capsys.readouterr().err


def _base_repo(tmp_path: Path, entry: str) -> tuple[Path, Path, str]:
    """``(repo, nested, local-only commit)``: the nested ``dev`` has a commit its ``origin`` lacks."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    nested = add_nested_repo(repo, COVERED, "dev")
    _configure(repo, entry)
    local_only = commit_file(nested, "local.py", "y = 1\n", "a local-only commit")
    return repo, nested, local_only


def test_base_local_worktree_contains_a_local_only_commit(tmp_path: Path) -> None:
    repo, _nested, local_only = _base_repo(tmp_path, f"{{path: {COVERED}, base: local}}")
    leaf = tmp_path / "leaf"
    assert add_nested_worktrees(repo, leaf, BRANCH, ["src"]) == [f"{COVERED}: on {BRANCH}"]
    assert git(leaf / COVERED, "merge-base", "--is-ancestor", local_only, "HEAD") == ""
    assert (leaf / COVERED / "local.py").is_file()


def test_base_remote_worktree_starts_at_the_remote_tip(tmp_path: Path) -> None:
    repo, nested, local_only = _base_repo(tmp_path, f"{{path: {COVERED}}}")
    leaf = tmp_path / "leaf"
    add_nested_worktrees(repo, leaf, BRANCH, ["src"])
    assert git(leaf / COVERED, "rev-parse", "HEAD") == git(nested, "rev-parse", "origin/dev") != local_only


@pytest.mark.parametrize("refuse", [False, True])
def test_base_local_behind_its_remote_is_refused_only_when_the_entry_says_so(tmp_path: Path, refuse: bool) -> None:
    flag = ", refuse_behind_remote: true" if refuse else ""
    repo, nested, _local_only = _base_repo(tmp_path, f"{{path: {COVERED}, base: local{flag}}}")
    git(nested, "push", "-q", "origin", "dev")
    git(nested, "reset", "-q", "--hard", "HEAD~1")   # origin/dev is now one commit ahead of dev
    leaf = tmp_path / "leaf"
    if refuse:
        with pytest.raises(NestedRepoError, match="1 commit\\(s\\) behind origin/dev"):
            add_nested_worktrees(repo, leaf, BRANCH, ["src"])
    else:
        add_nested_worktrees(repo, leaf, BRANCH, ["src"])
        assert git(leaf / COVERED, "rev-parse", "HEAD") == git(nested, "rev-parse", "dev")


@pytest.mark.parametrize("switch", [["checkout", "-q", "-b", "another-branch"], ["checkout", "-q", "--detach"]])
def test_land_local_refuses_when_the_checkout_leaves_the_integration_branch_during_the_merge(
        tmp_path: Path, switch: list[str]) -> None:
    """Fix round 1 R1: the checkout switches to another branch (or detaches) at the same commit while the
    temporary merge runs; landing must not report success, and the main repository must not be pushed."""
    repo, nested = _repo(tmp_path)
    _configure(repo, f"{{path: {COVERED}, land: local}}")
    hook = Path(git(nested, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "hooks" / "pre-merge-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nunset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_COMMON_DIR\n"
                    f"git -C {shlex.quote(str(nested))} {' '.join(switch)}\n", encoding="utf-8")
    hook.chmod(0o755)
    nested_remote, main_remote, dev = _origin_tip(nested), _origin_tip(repo), git(nested, "rev-parse", "dev")
    ok, err = _land(repo)
    assert not ok and "no longer has dev checked out" in err and "main repository was not merged" in err
    assert git(nested, "rev-parse", "dev") == dev   # the integration branch did not move
    assert git(nested, "branch", "--show-current") == ("another-branch" if "-b" in switch else "")
    assert git(nested, "rev-parse", "HEAD") == dev   # nor did the branch it switched to
    assert _origin_tip(nested) == nested_remote and _origin_tip(repo) == main_remote   # nothing pushed


def test_the_printed_manual_command_runs_for_a_path_with_spaces(tmp_path: Path) -> None:
    """Fix round 1 R2: the repository path is shell-quoted, so the printed command merges as printed."""
    parent = tmp_path / "parent with spaces"
    parent.mkdir()
    repo, nested = _repo(parent)
    _configure(repo, f"{{path: {COVERED}, land: manual}}")
    ok, err = _land(repo)
    assert not ok
    line = next(ln for ln in err.splitlines() if ln.lstrip().startswith("git -C "))
    assert shlex.quote(str(nested)) in line
    r = subprocess.run(line, shell=True, capture_output=True, text=True,
                       env={**os.environ, "GIT_MERGE_AUTOEDIT": "no"})
    assert r.returncode == 0, r.stderr
    assert git(nested, "merge-base", "--is-ancestor", BRANCH, "dev") == ""
    ok, err = _land(repo)
    assert ok, err
