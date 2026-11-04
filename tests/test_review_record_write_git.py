"""M8.3 A2 at the Git metadata boundary: a reviewer run that changes the Git index is a review failure (Sol, c12efa63).

The post-run walk skips ``.git``; the index is compared by ``git ls-files --stage -v`` instead, so an index-only
write (``update-index --assume-unchanged``, ``rm --cached``) fails the review while the stat refresh a read-only
``git status`` writes does not. Both public CLIs are exercised: ``review delegate`` and ``prompt --channel cli``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step, wrote_only
from tests.review_repo_helpers import git
from tests.test_models_and_prompt import run_main

from specy_road import review_files as rf
from specy_road.bundled_scripts import review_cli, role_prompt

#: A generic reviewer whose channels.cli is the fake harness (``{fake}``), printing only its final message.
GENERIC_GEM = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
               "  - {id: gem, family: google, roles: [reviewer], harness: generic, channels: {cli: '{fake} {prompt}'}}\n")


INDEX_ONLY_WRITES = [["update-index", "--assume-unchanged", "src/a.py"], ["rm", "--cached", "-q", "docs/x.md"]]


@pytest.mark.parametrize("cmd", INDEX_ONLY_WRITES)
def test_review_delegate_cli_fails_an_index_only_write_and_files_no_verdict(tmp_path: Path, capsys,
                                                                             cmd: list[str]) -> None:
    repo, spec = delegate_repo(tmp_path)
    clean = git(repo, "status", "--porcelain", "--untracked-files=no")
    set_steps(repo, spec, {**verdict_step(repo), "git": cmd})
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--json",
                         "--repo-root", str(repo)])
    assert e.value.code == 1
    run = json.loads(capsys.readouterr().out)
    assert run["outcome"] == "review_failure" and wrote_only(run["reason"], 'git index')
    assert not rf.review_path(repo, "M1.1", "opus").exists()
    if cmd[0] == "update-index":   # the index changed and the worktree did not: git status sees nothing either
        assert git(repo, "ls-files", "-v", "src/a.py").startswith("h ") and git(
            repo, "status", "--porcelain", "--untracked-files=no") == clean


def test_prompt_channel_cli_fails_an_index_only_write_and_files_no_verdict(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC_GEM)
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True, "git": INDEX_ONLY_WRITES[0]})
    assert run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 1
    assert "review_failure: review failure: the reviewer run wrote git index;" in capsys.readouterr().err
    assert not rf.review_path(repo, "M1.1", "gem").exists()


def test_a_read_only_git_status_that_refreshes_the_index_is_not_a_write(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    target = repo / "src" / "a.py"
    os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 5_000_000_000))   # stale stat cache
    index = Path(git(repo, "rev-parse", "--git-path", "index"))
    index = index if index.is_absolute() else repo / index
    raw = index.read_bytes()
    set_steps(repo, spec, {**verdict_step(repo), "git": ["status", "--porcelain"]})
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--json",
                         "--repo-root", str(repo)])
    assert e.value.code == 0 and json.loads(capsys.readouterr().out)["outcome"] == "recorded"
    assert index.read_bytes() != raw                                     # git status did rewrite the index file


# --- Git metadata beyond the index: hooks, the common and worktree Git directories, the .git pointer (Sol, 07169a5a) ---

def _delegate_cli(repo: Path, capsys, *extra: str) -> tuple[int, dict]:
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--json", *extra,
                         "--repo-root", str(repo)])
    return e.value.code, json.loads(capsys.readouterr().out)


def _common_git_dir(checkout: Path) -> Path:
    return Path(git(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def test_review_delegate_cli_fails_a_reviewer_created_hook_and_files_no_verdict(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    hooks = _common_git_dir(repo) / "hooks"
    hooks.mkdir(exist_ok=True)
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(hooks / "pre-commit"), "text": "#!/bin/sh\n"}})
    code, run = _delegate_cli(repo, capsys)
    assert code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], '.git/hooks/pre-commit')
    assert not rf.review_path(repo, "M1.1", "opus").exists()


@pytest.mark.parametrize("target", ["hook", "pointer"])
def test_a_reviewer_in_a_linked_worktree_that_writes_git_metadata_files_no_verdict(tmp_path: Path, capsys,
                                                                                    target: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    wt = tmp_path / "review-wt"
    git(repo, "worktree", "add", "-q", "--detach", str(wt))
    common = _common_git_dir(wt)
    (common / "hooks").mkdir(exist_ok=True)
    path = common / "hooks" / "post-checkout" if target == "hook" else wt / ".git"
    text = "#!/bin/sh\n" if target == "hook" else (wt / ".git").read_text() + "\n"
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(path), "text": text}})
    code, run = _delegate_cli(repo, capsys, "--worktree", str(wt))
    shown = ".git" if target == "pointer" else str(path)   # inside the worktree: relative; the common dir: absolute
    assert code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], shown)
    assert not rf.review_path(repo, "M1.1", "opus").exists()


# --- permission mode: a reviewer-only chmod is a write (Sol, e6195893) --------------------------------------------------

@pytest.mark.parametrize("area", ["checkout", "hand-off", "git-dir", "pointer"])
def test_review_delegate_cli_fails_a_reviewer_only_chmod_and_files_no_verdict(tmp_path: Path, capsys, area: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    extra: tuple[str, ...] = ()
    if area == "pointer":
        wt = tmp_path / "review-wt"
        git(repo, "worktree", "add", "-q", "--detach", str(wt))
        path, shown, extra = wt / ".git", ".git", ("--worktree", str(wt))
    else:
        rel = {"checkout": "src/a.py", "hand-off": "work/reviews/M1.1/PACKET.md", "git-dir": ".git/config"}[area]
        path, shown = repo / rel, rel
    before, content = path.stat(), path.read_bytes()
    set_steps(repo, spec, {**verdict_step(repo), "chmod": str(path)})
    code, run = _delegate_cli(repo, capsys, *extra)
    after = path.stat()
    assert after.st_mode != before.st_mode                                                 # only the mode changed
    assert (after.st_size, after.st_mtime_ns, path.read_bytes()) == (before.st_size, before.st_mtime_ns, content)
    assert code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], shown)
    assert not rf.review_path(repo, "M1.1", "opus").exists()


# --- a reviewer-created nested .git: recorded, not skipped as another checkout (Sol, 3387a90d) -----------------------

@pytest.mark.parametrize("how", ["git-file", "git-init"])
def test_review_delegate_cli_fails_a_reviewer_created_nested_git_and_files_no_verdict(tmp_path: Path, capsys,
                                                                                       how: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    if how == "git-file":   # a .git pointer file in a new directory, which would then read as a nested checkout
        step, shown = {"write": {"path": str(repo / "work" / "hidden" / ".git"), "text": "gitdir: elsewhere\n"}}, \
            "work/hidden/.git"
    else:                   # a whole new repository inside the checkout
        step, shown = {"git": ["init", "-q", "work/nested"]}, "work/nested/.git"
    set_steps(repo, spec, {**verdict_step(repo), **step})
    code, run = _delegate_cli(repo, capsys)
    assert (repo / shown).exists()
    assert code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], shown)
    assert not rf.review_path(repo, "M1.1", "opus").exists()


# --- file identity: an identical hard-link replacement is a write (Sol, d5f3e39d) ------------------------------------

@pytest.mark.parametrize("area", ["checkout", "hand-off", "git-dir", "pointer"])
def test_review_delegate_cli_fails_an_identical_hard_link_replacement_and_files_no_verdict(tmp_path: Path, capsys,
                                                                                           area: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    extra: tuple[str, ...] = ()
    if area == "pointer":
        wt = tmp_path / "review-wt"
        git(repo, "worktree", "add", "-q", "--detach", str(wt))
        path, shown, extra = wt / ".git", ".git", ("--worktree", str(wt))
    else:
        rel = {"checkout": "src/a.py", "hand-off": "work/reviews/M1.1/PACKET.md", "git-dir": ".git/config"}[area]
        path, shown = repo / rel, rel
    alias = tmp_path / f"alias-{area}"                                        # outside every snapshotted tree
    before, content = path.stat(), path.read_bytes()
    set_steps(repo, spec, {**verdict_step(repo), "relink": {"path": str(path), "alias": str(alias)}})
    code, run = _delegate_cli(repo, capsys, *extra)
    after = path.stat()
    assert (after.st_mode, after.st_size, after.st_mtime_ns, path.read_bytes()) == (
        before.st_mode, before.st_size, before.st_mtime_ns, content)          # all the old tuple compared
    assert after.st_ino == alias.stat().st_ino != before.st_ino and after.st_nlink == 2
    assert code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], shown)
    assert not rf.review_path(repo, "M1.1", "opus").exists()


# --- change time: an identical-bytes rewrite with its mtime put back is a write (Sol, 06d90dba) ---------------------

def test_review_delegate_cli_fails_an_identical_rewrite_with_its_mtime_restored_and_files_no_verdict(
        tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    target = repo / "src" / "a.py"
    assert git(repo, "ls-files", "src/a.py") == "src/a.py"                    # a tracked file
    before, content = target.stat(), target.read_bytes()
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(target), "text": content.decode(),
                                                            "keep_mtime": True}})
    code, run = _delegate_cli(repo, capsys)
    after = target.stat()
    assert (after.st_dev, after.st_ino, after.st_nlink, after.st_mode, after.st_size, after.st_mtime_ns,
            target.read_bytes()) == (before.st_dev, before.st_ino, before.st_nlink, before.st_mode,
                                     before.st_size, before.st_mtime_ns, content)   # all but the change time
    assert after.st_ctime_ns != before.st_ctime_ns
    assert code == 1 and run["outcome"] == "review_failure"
    assert wrote_only(run["reason"], 'src/a.py')
    assert not rf.review_path(repo, "M1.1", "opus").exists()


# --- directory metadata: a file created, written and deleted again is a write (Sol, 26f5cfb6) ----------------------

@pytest.mark.parametrize("where", ["src", ".git/hooks", "work/reviews/M1.1/history"])
def test_review_delegate_cli_fails_a_created_written_and_deleted_file_and_files_no_verdict(tmp_path: Path, capsys,
                                                                                           where: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    (repo / where).mkdir(parents=True, exist_ok=True)                        # an existing directory, set up first
    scratch = repo / where / "scratch.tmp"
    set_steps(repo, spec, {**verdict_step(repo), "transient": str(scratch)})
    code, run = _delegate_cli(repo, capsys)
    assert not scratch.exists()                                              # nothing is left behind
    assert code == 1 and run["outcome"] == "review_failure" and wrote_only(run["reason"], where)
    assert not rf.review_path(repo, "M1.1", "opus").exists()
