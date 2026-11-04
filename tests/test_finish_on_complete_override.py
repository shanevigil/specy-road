"""CR9: ``finish-this-task --on-complete`` cannot quietly change the configured landing mode.

The context-regression replay had agents asked to "finish and clean up" run
``--on-complete merge --delete-branch`` in a repo committed to ``on_complete: pr``.
A different mode now needs ``--override-on-complete``, a person's choice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.finish_on_complete_override import configured_on_complete, needs_override
from specy_road.on_complete_session import on_complete_session_path, write_on_complete_session
from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git, make_review_repo

BR = "feature/rm-thing"


def _exit(fn, argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        fn(argv)
        raise SystemExit(0)
    return e.value.code or 0


def _repo(tmp_path: Path, monkeypatch, mode: str) -> tuple[Path, Path]:
    """The claimed leaf, mergeable into ``dev``, ``on_complete: <mode>`` committed, a bare origin."""
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # finish runs validate/export/digest as subprocesses
    monkeypatch.delenv("SPECY_ROAD_ON_COMPLETE", raising=False)
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "roadmap/git-workflow.yaml",
                f"version: 1\nintegration_branch: dev\nremote: origin\non_complete: {mode}\n", "mode")
    commit_file(repo, ".gitignore", "work/\n.specyrd/cache/\n", "as init project scaffolds")
    git(repo, "checkout", "-q", BR)
    git(repo, "merge", "-q", "--no-edit", "dev")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(repo), str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    git(repo, "remote", "set-head", "origin", "dev")   # as `git clone` records it; git < 2.48 fetch does not
    return repo, bare


def test_merge_over_a_committed_pr_is_refused_before_anything_changes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, bare = _repo(tmp_path, monkeypatch, "pr")
    tip, dev = git(repo, "rev-parse", BR), git(bare, "rev-parse", "dev")

    code = _exit(finish_task.main, ["--on-complete", "merge", "--delete-branch", "--repo-root", str(repo)])

    err = capsys.readouterr().err
    assert code == 1
    assert "on_complete: pr (from roadmap/git-workflow.yaml)" in err
    assert "a person must choose" in err and "--override-on-complete" in err
    assert git(repo, "rev-parse", BR) == tip
    assert git(bare, "rev-parse", "dev") == dev
    assert git(repo, "branch", "--show-current") == BR


def test_a_repeat_finish_cannot_land_a_pr_mode_leaf_with_merge(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """CR9/cursor r1: finish (pr), then ``--on-complete merge`` to retry a 'landing'."""
    repo, bare = _repo(tmp_path, monkeypatch, "pr")
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 0
    tip, dev = git(repo, "rev-parse", BR), git(bare, "rev-parse", "dev")
    capsys.readouterr()

    assert _exit(finish_task.main, ["--on-complete", "merge", "--repo-root", str(repo)]) == 1

    assert "--override-on-complete" in capsys.readouterr().err
    assert git(repo, "rev-parse", BR) == tip
    assert git(bare, "rev-parse", "dev") == dev


def test_the_configured_value_passed_explicitly_still_lands(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, bare = _repo(tmp_path, monkeypatch, "merge")

    assert _exit(finish_task.main, ["--on-complete", "merge", "--repo-root", str(repo)]) == 0

    assert f"[ok] merged {BR} into dev and pushed to origin" in capsys.readouterr().out
    assert git(bare, "merge-base", "--is-ancestor", git(repo, "rev-parse", BR), "dev") == ""


def test_the_acknowledgement_lets_a_person_override(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, _bare = _repo(tmp_path, monkeypatch, "pr")

    argv = ["--on-complete", "merge", "--override-on-complete", "--repo-root", str(repo)]
    assert _exit(finish_task.main, argv) == 0

    out, err = capsys.readouterr()
    assert "[warn] --on-complete merge overrides on_complete: pr" in err
    assert f"[ok] merged {BR} into dev and pushed to origin" in out


def test_pr_is_never_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    """pr lands nothing and keeps the branch: the safe direction needs no acknowledgement."""
    repo, bare = _repo(tmp_path, monkeypatch, "merge")
    dev = git(bare, "rev-parse", "dev")

    assert _exit(finish_task.main, ["--on-complete", "pr", "--repo-root", str(repo)]) == 0

    assert "on_complete: pr" in capsys.readouterr().out
    assert git(bare, "rev-parse", "dev") == dev


def test_an_overridden_landing_that_fails_names_the_flag_on_its_re_run(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo, bare = _repo(tmp_path, monkeypatch, "pr")
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)

    argv = ["--on-complete", "merge", "--override-on-complete", "--repo-root", str(repo)]
    assert _exit(finish_task.main, argv) == 1

    assert "finish-this-task --on-complete merge --override-on-complete" in capsys.readouterr().err


def test_the_pickup_session_counts_as_the_configured_mode(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A mode chosen at pickup (the TTY prompt) is what finish uses; passing it again is no override."""
    repo, _bare = _repo(tmp_path, monkeypatch, "pr")
    write_on_complete_session(
        on_complete_session_path(repo / "work", "M1.1"),
        node_id="M1.1", codename="thing", on_complete="merge",
    )
    assert configured_on_complete(repo, session="merge")[0] == "merge"
    assert needs_override(repo, "merge") and not needs_override(repo, "merge", session="merge")

    assert _exit(finish_task.main, ["--on-complete", "merge", "--repo-root", str(repo)]) == 0

    assert f"[ok] merged {BR} into dev and pushed to origin" in capsys.readouterr().out
