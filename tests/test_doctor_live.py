"""``specy-road doctor`` never offers to remove a live leaf's worktree or branch (M14.2).

Live: an open registry claim or a worker record that is not terminal holds the branch.
A branch with no commit of its own is "no commits yet", never merged, even though the
integration branch trivially contains its tip.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from specy_road import worker_state
from specy_road.doctor_worktrees import has_own_commits
from tests.review_repo_helpers import commit_file, git
from tests.test_doctor import _exit, _has, doctor_repo  # noqa: F401 — the fixture


def _claim_fresh(repo: Path, codename: str, node_id: str) -> Path:
    """What pickup does: a claim on the integration branch and a worktree on a new branch."""
    reg_path = repo / "roadmap" / "registry.yaml"
    reg = yaml.safe_load(reg_path.read_text())
    reg["entries"].append({"codename": codename, "node_id": node_id,
                           "branch": f"feature/rm-{codename}", "touch_zones": [codename]})
    commit_file(repo, "roadmap/registry.yaml", yaml.safe_dump(reg), "claim")
    git(repo, "push", "-q", "origin", "dev")
    wt = repo.parent / f"wt-{codename}"
    git(repo, "worktree", "add", "-q", "-b", f"feature/rm-{codename}", str(wt), "dev")
    return wt


def test_a_claimed_worktree_on_a_fresh_branch_is_live_and_fix_leaves_it(doctor_repo, capsys) -> None:
    repo, _bare = doctor_repo
    wt = _claim_fresh(repo, "fresh", "M1.5")

    assert _exit(["--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "wt-fresh  — branch feature/rm-fresh live: claimed by M1.5, so --fix leaves it" in out
    assert "feature/rm-fresh is merged" not in out

    assert _exit(["--fix", "--yes", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert any(line.startswith("[kept] ") and "wt-fresh: branch feature/rm-fresh live: claimed by M1.5" in line
               for line in out.splitlines())
    assert str(wt) in git(repo, "worktree", "list") and wt.is_dir()
    assert _has(repo, "refs/heads/feature/rm-fresh")


def test_an_unclaimed_branch_with_no_commits_is_never_merged(doctor_repo, capsys) -> None:
    repo, _bare = doctor_repo
    wt = repo.parent / "wt-empty"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-empty", str(wt), "dev")
    assert not has_own_commits(repo, "refs/heads/feature/rm-empty", "origin/dev")
    assert has_own_commits(repo, "refs/heads/feature/rm-done", "origin/dev")

    assert _exit(["--fix", "--yes", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "[kept] local feature/rm-empty: claim gone, no commits yet, so --fix leaves it" in out
    assert "[kept] " in out and "wt-empty: branch feature/rm-empty has no commits yet, so --fix leaves it" in out
    assert _has(repo, "refs/heads/feature/rm-empty") and wt.is_dir()
    assert "[ok] deleted local branch feature/rm-done" in out   # merged with commits, unclaimed: unchanged


def test_a_worker_held_branch_is_live_until_the_worker_is_terminal(doctor_repo, capsys) -> None:
    """feature/rm-done is merged, has commits and no claim: a running worker still keeps it."""
    repo, bare = doctor_repo
    wt = repo.parent / "wt-done"
    with (repo / ".git" / "info" / "exclude").open("a") as f:
        f.write("work/.workers/\n")   # a consumer ignores work/; registry-prune needs a clean tree
    rec = worker_state.create_record(repo, "M1.9", "generic", "m", wt, branch="feature/rm-done")
    worker_state.set_state(repo, rec, "running")

    assert _exit(["--fix", "--yes", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    live = f"live: worker {rec.worker_id} (running), so --fix leaves it"
    assert f"[kept] local feature/rm-done: {live}" in out
    assert f"[kept] origin feature/rm-done: {live}" in out
    assert any(line.startswith("[kept] ") and line.endswith(f"wt-done: branch feature/rm-done {live}")
               for line in out.splitlines())
    assert wt.is_dir() and _has(repo, "refs/heads/feature/rm-done") and _has(bare, "refs/heads/feature/rm-done")

    worker_state.set_state(repo, worker_state.load_record(repo, rec.worker_id), "terminated")
    assert _exit(["--fix", "--yes", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "[ok] deleted local branch feature/rm-done" in out
    assert not wt.is_dir()
