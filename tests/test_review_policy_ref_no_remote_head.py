"""Missing ``refs/remotes/<remote>/HEAD``: the gate fails closed and names a set-head command that works."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.git_subprocess import git_text
from specy_road.review_policy_ref import integration_name, policy_source
from tests.review_repo_helpers import commit_file, git, make_review_repo

_HINT = re.compile(r"`(git remote set-head [^`]+)`")
_MAIN = "version: 1\nintegration_branch: main\nremote: origin\n"
_FEATURE = "feature/rm-thing"


def _drop_origin_head(repo: Path) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "remote", "set-head", "origin", "-d"],
        check=False, capture_output=True, text=True,
    )


def _unborn_remote(tmp_path: Path, branch: str, workflow: str) -> Path:
    """Bare remote with an unborn ``master`` HEAD, ``branch`` pushed, checkout one commit ahead, no set-head."""
    repo = tmp_path / "app"
    repo.mkdir()
    git(repo, "init", "-q", "-b", branch)
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    commit_file(repo, "roadmap/git-workflow.yaml", workflow, "workflow")
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/master")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", branch)
    _drop_origin_head(repo)
    commit_file(repo, "notes.txt", "under review\n", "ahead of the pushed branch")
    return repo


def _hint_args(err: str) -> list[str]:
    commands = [cmd for cmd in _HINT.findall(err) if "--auto" not in cmd]
    assert len(commands) == 1, err
    return commands[0].split()[1:]


def _closed(repo: Path) -> str:
    named, err = integration_name(repo, ["origin"])
    assert named is None and err and "Traceback" not in err
    assert policy_source(repo) == (None, err)
    return err


def test_unborn_remote_head_fails_closed_and_the_hint_names_main(tmp_path: Path) -> None:
    repo = _unborn_remote(tmp_path, "main", _MAIN)
    assert git_text(["rev-parse", "--verify", "--quiet", "refs/remotes/origin/HEAD^{commit}"], repo) is None
    err = _closed(repo)
    args = _hint_args(err)
    assert args == ["remote", "set-head", "origin", "main"]
    assert "unborn" in err
    git(repo, *args)
    assert policy_source(repo) == ("refs/remotes/origin/main", None)


def test_a_pushed_feature_commit_that_names_itself_is_not_the_hint(tmp_path: Path) -> None:
    repo = _unborn_remote(tmp_path, "main", _MAIN)
    git(repo, "checkout", "-q", "-b", _FEATURE)
    commit_file(
        repo, "roadmap/git-workflow.yaml",
        f"version: 1\nintegration_branch: {_FEATURE}\nremote: origin\n", "names itself",
    )
    git(repo, "push", "-q", "origin", _FEATURE)
    _drop_origin_head(repo)
    err = _closed(repo)
    assert _FEATURE not in err
    assert _hint_args(err) == ["remote", "set-head", "origin", "main"]


@pytest.mark.parametrize("workflow", [
    "integration_branch: [\n",
    "[]\n",
    "version: 1\nremote: origin\n",
])
def test_an_unreadable_or_unnamed_candidate_names_no_branch(tmp_path: Path, workflow: str) -> None:
    repo = _unborn_remote(tmp_path, "main", workflow)
    err = _closed(repo)
    assert _hint_args(err) == ["remote", "set-head", "origin", "<name>"]
    assert "real default branch" in err
    assert "`git remote set-head origin main`" not in err


def test_validate_names_the_unreadable_policy_source(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/master")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "dev")
    _drop_origin_head(repo)
    (repo / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\n"
        "require_implementation_review_before_finish: false\n",
        encoding="utf-8",
    )
    reg = repo / "roadmap" / "registry.yaml"
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    del data["entries"][0]["implementation_review"]
    reg.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(SystemExit):
        validate_at(repo)
    err = capsys.readouterr().err
    assert "the policy source could not be read" in err
    assert "`git remote set-head origin dev`" in err
    assert "require_implementation_review_before_finish is true" not in err
    assert "Traceback" not in err
