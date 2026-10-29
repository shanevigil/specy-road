"""``specy-road doctor``: leftover branches, worktrees, registry rows and stashes.

One repo holds every kind, with the look-alikes doctor must leave alone next to
each: a claimed branch, an open rollup, a worktree on the claimed branch, a stash
specy-road did not push.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from specy_road import cli
from specy_road.bundled_scripts import doctor
from tests.helpers import REPO
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

TOOLKIT_STASH = "specy-road: temp stash work/ around pickup"


def _exit(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        doctor.main(argv)
    return e.value.code or 0


def _branch_with_commits(repo: Path, branch: str, *rels: str) -> None:
    git(repo, "checkout", "-q", "-b", branch, "dev")
    for rel in rels:
        commit_file(repo, rel, f"{rel}\n", rel)
    git(repo, "checkout", "-q", "dev")


def _has(repo: Path, ref: str) -> bool:
    return bool(git(repo, "for-each-ref", "--format=%(refname)", ref))


def _graph_and_registry(repo: Path) -> None:
    """A Complete leaf ``finished``, an open rollup ``roll``, a claim ``ghost`` with no branch."""
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"][0]["milestone_execution"] = {"state": "active", "rollup_branch": "feature/rm-roll"}
    doc["nodes"].append({**NODE, "id": "M1.2", "codename": "finished", "status": "Complete",
                         "node_key": "22222222-2222-5222-8222-222222222222", "sibling_order": 2})
    commit_file(repo, "roadmap/phases/M1.json", json.dumps(doc), "graph")
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())
    reg["entries"].append({"codename": "ghost", "node_id": "M1.3", "branch": "feature/rm-ghost",
                           "touch_zones": ["ghost"]})
    commit_file(repo, "roadmap/registry.yaml", yaml.safe_dump(reg), "ghost claim")


@pytest.fixture
def doctor_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.setenv("PYTHONPATH", str(REPO))   # --fix runs registry-prune as a subprocess
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    _graph_and_registry(repo)
    git(repo, "branch", "feature/rm-roll")
    for name in ("done", "rebased", "finished", "open", "gone"):
        _branch_with_commits(repo, f"feature/rm-{name}", f"src/{name}.py")
    _branch_with_commits(repo, "feature/rm-squash", "src/s1.py", "src/s2.py")
    for branch in ("feature/rm-done", "feature/rm-gone", "feature/rm-thing"):
        git(repo, "merge", "-q", "--no-ff", "--no-edit", branch)
    git(repo, "merge", "-q", "--squash", "feature/rm-squash")
    git(repo, "commit", "-qm", "squash")
    git(repo, "cherry-pick", "feature/rm-rebased")   # same patch, new sha
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "--all")
    git(repo, "branch", "-q", "-D", "feature/rm-gone")

    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-done"), "feature/rm-done")
    (tmp_path / "wt-done" / "work" / "reviews").mkdir(parents=True)
    (tmp_path / "wt-done" / "work" / "reviews" / "READY.md").write_text("x", encoding="utf-8")
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "wt-detached"), "dev")
    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-missing"), "feature/rm-squash")
    shutil.rmtree(tmp_path / "wt-missing")
    git(repo, "worktree", "add", "-q", str(tmp_path / "wt-thing"), "feature/rm-thing")

    for msg in (TOOLKIT_STASH, "mine"):
        (repo / "work").mkdir(exist_ok=True)
        (repo / "work" / "note.md").write_text(msg, encoding="utf-8")
        git(repo, "stash", "push", "-q", "-u", "-m", msg)
    return repo, bare


LISTED_LOCAL = {
    "feature/rm-done": "merged",
    "feature/rm-squash": doctor.SAME_PATCH,
    "feature/rm-rebased": doctor.SAME_PATCH,
    "feature/rm-finished": "leaf M1.2 Complete, not merged: 1 commit(s) origin/dev lacks",
    "feature/rm-open": "claim gone, not merged: 1 commit(s) origin/dev lacks",
}
KEPT = ("feature/rm-thing", "feature/rm-roll")


def test_dry_run_lists_every_kind_and_changes_nothing(doctor_repo, capsys) -> None:
    repo, bare = doctor_repo

    assert _exit(["--repo-root", str(repo)]) == 0

    out = capsys.readouterr().out
    for branch, reason in LISTED_LOCAL.items():
        assert f"local     {branch}  — {reason}" in out
        assert f"origin    {branch}  — {reason}" in out
    assert "origin    feature/rm-gone  — merged" in out
    for branch in KEPT:
        assert branch not in out.split("Worktrees")[0]
    assert "wt-done  — branch feature/rm-done is merged; removing it deletes ignored work/reviews/" in out
    assert "wt-detached  — branch gone: detached at" in out
    assert "wt-missing  — directory missing" in out
    assert "wt-thing" not in out
    assert "ghost  — node M1.3: feature/rm-ghost is in neither this clone nor origin" in out
    assert TOOLKIT_STASH in out
    assert ": mine" not in out
    assert "Nothing removed. Re-run with --fix" in out
    assert _has(repo, "refs/heads/feature/rm-open")
    assert _has(bare, "refs/heads/feature/rm-gone")
    assert len(git(repo, "stash", "list").splitlines()) == 2
    assert "ghost" in git(bare, "show", "dev:roadmap/registry.yaml")


def test_doctor_is_wired_into_the_cli(doctor_repo, capfd) -> None:
    repo, _bare = doctor_repo
    cli.main(["doctor", "--repo-root", str(repo)])   # raises only on a non-zero exit
    assert "local     feature/rm-done  — merged" in capfd.readouterr().out


def test_fix_removes_what_it_listed_and_reports_each(doctor_repo, capsys) -> None:
    repo, bare = doctor_repo

    assert _exit(["--fix", "--yes", "--repo-root", str(repo)]) == 0

    out = capsys.readouterr().out
    for branch in [*LISTED_LOCAL, "feature/rm-gone"]:
        if branch != "feature/rm-gone":
            assert f"[ok] deleted local branch {branch}" in out
            assert not _has(repo, f"refs/heads/{branch}")
        assert f"[ok] deleted {branch} on origin" in out
        assert not _has(bare, f"refs/heads/{branch}")
    for name in ("wt-done", "wt-detached", "wt-missing"):
        assert any(line.startswith("[ok] removed worktree ") and line.endswith(name)
                   for line in out.splitlines())
        assert name not in git(repo, "worktree", "list")
    assert "wt-thing" in git(repo, "worktree", "list")
    assert "[ok] removed registry row ghost on origin/dev" in out
    assert "ghost" not in git(bare, "show", "dev:roadmap/registry.yaml")
    assert "[ok] dropped stash" in out
    stashes = git(repo, "stash", "list").splitlines()
    assert len(stashes) == 1 and stashes[0].endswith(": mine")
    for branch in KEPT:
        assert _has(repo, f"refs/heads/{branch}")
        assert _has(bare, f"refs/heads/{branch}")

    assert _exit(["--repo-root", str(repo)]) == 0
    assert "Nothing to tidy" in capsys.readouterr().out


def test_fix_asks_per_kind_and_a_no_removes_nothing(doctor_repo, capsys, monkeypatch) -> None:
    repo, bare = doctor_repo
    asked: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: asked.append(prompt) or "n")

    assert _exit(["--fix", "--repo-root", str(repo)]) == 0

    assert [p.split()[4] for p in asked] == ["worktree", "branch", "stash", "registry"]
    out = capsys.readouterr().out
    assert "[ok]" not in out
    assert "Skipped the branch item(s)." in out
    assert _has(repo, "refs/heads/feature/rm-done")
    assert _has(bare, "refs/heads/feature/rm-gone")
    assert len(git(repo, "stash", "list").splitlines()) == 2


def test_fix_without_an_answer_stops_before_removing(doctor_repo, capsys, monkeypatch) -> None:
    repo, _bare = doctor_repo

    def no_stdin(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_stdin)

    assert _exit(["--fix", "--repo-root", str(repo)]) == 1

    assert "pass --yes" in capsys.readouterr().err
    assert "wt-done" in git(repo, "worktree", "list")
    assert _has(repo, "refs/heads/feature/rm-done")


def test_a_branch_moved_after_listing_is_not_deleted(doctor_repo) -> None:
    repo, _bare = doctor_repo
    listed = git(repo, "rev-parse", "feature/rm-open")
    git(repo, "branch", "-f", "feature/rm-open", "feature/rm-done")

    failure = doctor._delete_local(repo, "feature/rm-open", listed)

    assert failure == "moved since it was listed; left alone"
    assert _has(repo, "refs/heads/feature/rm-open")


def test_merged_how_needs_the_patch_upstream_not_just_the_files(tmp_path: Path) -> None:
    """A branch whose diff differs from what landed is not merged, even with shared files."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    _branch_with_commits(repo, "feature/rm-x", "src/x.py")
    commit_file(repo, "src/x.py", "something else\n", "different content, same path")

    assert doctor.merged_how(repo, "feature/rm-x", "dev") is None
    assert doctor.merged_how(repo, "feature/rm-thing", "feature/rm-thing") == "merged"


def test_doctor_refuses_without_a_fresh_fetch(doctor_repo, capsys) -> None:
    repo, bare = doctor_repo
    git(repo, "remote", "set-url", "origin", str(bare.parent / "missing.git"))

    assert _exit(["--fix", "--yes", "--repo-root", str(repo)]) == 1

    assert "git fetch --prune origin failed" in capsys.readouterr().err
    assert _has(repo, "refs/heads/feature/rm-done")
