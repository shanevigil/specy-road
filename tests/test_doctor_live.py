"""``specy-road doctor`` never offers to remove a live leaf's worktree or branch (M14.2).

Live: an open registry claim, a live session or a worker record that is not terminal holds the
branch or worktree; that is judged before anything else, a missing directory included. An
ancestry-merged branch is offered for removal only with positive evidence, on that exact ref,
of commits of its own; a fresh branch is "no commits yet", and a branch whose evidence is gone
(expired reflog, no local branch) is reported as merged but left for a human.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from specy_road import session_presence, worker_state
from specy_road.bundled_scripts import doctor
from specy_road.doctor_worktrees import NO_EVIDENCE
from tests.review_repo_helpers import commit_file, git
from tests.test_doctor import doctor_repo  # noqa: F401 — the fixture


def run_doctor(repo: Path, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        doctor.main([*args, "--repo-root", str(repo)])
    return e.value.code or 0


def has_ref(repo: Path, ref: str) -> bool:
    return bool(git(repo, "for-each-ref", "--format=%(refname)", ref))


def kept(out: str, text: str) -> bool:
    return any(line.startswith("[kept] ") and text in line for line in out.splitlines())


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

    assert run_doctor(repo) == 0
    out = capsys.readouterr().out
    assert "wt-fresh  — branch feature/rm-fresh live: claimed by M1.5, so --fix leaves it" in out
    assert "feature/rm-fresh is merged" not in out

    assert run_doctor(repo, "--fix", "--yes") == 0
    assert kept(capsys.readouterr().out, "wt-fresh: branch feature/rm-fresh live: claimed by M1.5")
    assert str(wt) in git(repo, "worktree", "list") and wt.is_dir()
    assert has_ref(repo, "refs/heads/feature/rm-fresh")


def test_f1_a_claimed_worktree_whose_directory_moved_is_live_not_missing(doctor_repo, capsys) -> None:
    """Liveness comes before "directory missing": the registration of a moved claimed tree stays."""
    repo, _bare = doctor_repo
    moved = repo.parent / "wt-thing-moved"
    shutil.move(str(repo.parent / "wt-thing"), str(moved))

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert kept(out, "wt-thing: branch feature/rm-thing live: claimed by M1.1, so --fix leaves it")
    assert "wt-thing: directory missing" not in out and not out.rstrip().endswith("wt-thing")
    assert "wt-thing" in git(repo, "worktree", "list")
    assert git(moved, "branch", "--show-current") == "feature/rm-thing"   # its admin dir is intact


def test_an_unclaimed_branch_with_no_commits_is_never_merged(doctor_repo, capsys) -> None:
    repo, _bare = doctor_repo
    wt = repo.parent / "wt-empty"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-empty", str(wt), "dev")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[kept] local feature/rm-empty: claim gone, no commits yet, so --fix leaves it" in out
    assert kept(out, "wt-empty: branch feature/rm-empty has no commits yet, so --fix leaves it")
    assert has_ref(repo, "refs/heads/feature/rm-empty") and wt.is_dir()
    assert "[ok] deleted local branch feature/rm-done" in out   # merged with commits, unclaimed: unchanged


def test_f2_a_fresh_branch_renamed_before_its_first_commit_has_no_commits(doctor_repo, capsys) -> None:
    """A rename is a reflog entry, not a commit."""
    repo, _bare = doctor_repo
    git(repo, "branch", "feature/rm-rename-source", "dev")
    git(repo, "branch", "-m", "feature/rm-rename-source", "feature/rm-renamed")
    wt = repo.parent / "wt-renamed"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-renamed")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[kept] local feature/rm-renamed: claim gone, no commits yet, so --fix leaves it" in out
    assert kept(out, "wt-renamed: branch feature/rm-renamed has no commits yet, so --fix leaves it")
    assert has_ref(repo, "refs/heads/feature/rm-renamed") and wt.is_dir()


def test_f3_a_fresh_remote_branch_does_not_borrow_its_local_namesakes_commits(doctor_repo, capsys) -> None:
    """Pushed fresh, then one unpushed local commit: the remote ref itself has none of its own."""
    repo, bare = doctor_repo
    git(repo, "branch", "feature/rm-pushed", "dev")
    git(repo, "push", "-q", "origin", "feature/rm-pushed")
    fresh = git(repo, "rev-parse", "feature/rm-pushed")
    git(repo, "checkout", "-q", "feature/rm-pushed")
    commit_file(repo, "src/pushed.py", "x\n", "unpushed")
    git(repo, "checkout", "-q", "dev")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[kept] origin feature/rm-pushed: claim gone, no commits yet, so --fix leaves it" in out   # R2
    assert "deleted feature/rm-pushed on origin" not in out
    assert git(bare, "rev-parse", "feature/rm-pushed") == fresh


def _fast_forwarded(repo: Path) -> str:
    """feature/rm-ff carries one real commit, landed on dev by fast-forward and pushed."""
    git(repo, "checkout", "-q", "-b", "feature/rm-ff", "dev")
    commit_file(repo, "src/ff.py", "x\n", "ff feature")
    git(repo, "checkout", "-q", "dev")
    git(repo, "merge", "-q", "--ff-only", "feature/rm-ff")
    git(repo, "push", "-q", "origin", "dev", "feature/rm-ff")
    return git(repo, "rev-parse", "feature/rm-ff")


def test_f4_a_fast_forwarded_commit_with_an_expired_reflog_is_merged_but_left(doctor_repo, capsys) -> None:
    repo, bare = doctor_repo
    tip = _fast_forwarded(repo)
    assert run_doctor(repo) == 0
    assert "local     feature/rm-ff  — merged\n" in capsys.readouterr().out   # the commit entry: evidence

    git(repo, "reflog", "expire", "--expire=all", "refs/heads/feature/rm-ff")
    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert f"[kept] local feature/rm-ff: merged; {NO_EVIDENCE}, so --fix leaves it" in out
    assert f"[kept] origin feature/rm-ff: merged; {NO_EVIDENCE}, so --fix leaves it" in out
    assert "no commits yet" not in out.split("[kept] local feature/rm-ff")[1].splitlines()[0]
    assert git(repo, "rev-parse", "feature/rm-ff") == tip == git(bare, "rev-parse", "feature/rm-ff")


def test_f4_a_fast_forwarded_commit_with_no_local_branch_is_merged_but_left(doctor_repo, capsys) -> None:
    repo, bare = doctor_repo
    tip = _fast_forwarded(repo)
    git(repo, "branch", "-q", "-D", "feature/rm-ff")

    assert run_doctor(repo) == 0
    assert f"origin    feature/rm-ff  — merged; {NO_EVIDENCE}, so --fix leaves it" in capsys.readouterr().out
    assert run_doctor(repo, "--fix", "--yes") == 0
    assert kept(capsys.readouterr().out, f"origin feature/rm-ff: merged; {NO_EVIDENCE}")
    assert git(bare, "rev-parse", "feature/rm-ff") == tip


def test_a_worker_held_branch_is_live_until_the_worker_is_terminal(doctor_repo, capsys) -> None:
    """feature/rm-done is merged, has commits and no claim: a running worker still keeps it."""
    repo, bare = doctor_repo
    wt = repo.parent / "wt-done"
    with (repo / ".git" / "info" / "exclude").open("a") as f:
        f.write("work/.workers/\n")   # a consumer ignores work/; registry-prune needs a clean tree
    rec = worker_state.create_record(repo, "M1.9", "generic", "m", wt, branch="feature/rm-done")
    worker_state.set_state(repo, rec, "running")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    live = f"live: worker {rec.worker_id} (running), so --fix leaves it"
    assert f"[kept] local feature/rm-done: {live}" in out
    assert f"[kept] origin feature/rm-done: {live}" in out
    assert kept(out, f"wt-done: branch feature/rm-done {live}")
    assert wt.is_dir() and has_ref(repo, "refs/heads/feature/rm-done") and has_ref(bare, "refs/heads/feature/rm-done")

    worker_state.set_state(repo, worker_state.load_record(repo, rec.worker_id), "terminated")
    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[ok] deleted local branch feature/rm-done" in out
    assert not wt.is_dir()


def test_r1_a_reused_branch_name_with_a_creation_only_reflog_has_no_commits(doctor_repo, capsys) -> None:
    """feature/rm-gone landed by a finish merge; recreating it locally from origin gives a creation-only
    reflog, which beats that earlier branch's merge commit."""
    repo, _bare = doctor_repo
    git(repo, "branch", "feature/rm-gone", "origin/feature/rm-gone")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[kept] local feature/rm-gone: claim gone, no commits yet, so --fix leaves it" in out
    assert "deleted local branch feature/rm-gone" not in out
    assert has_ref(repo, "refs/heads/feature/rm-gone")


def test_r3_a_fresh_branch_at_another_branchs_unlanded_tip_has_no_commits(doctor_repo, capsys) -> None:
    repo, _bare = doctor_repo
    git(repo, "branch", "feature/rm-borrowed", "feature/rm-open")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[kept] local feature/rm-borrowed: claim gone, no commits yet, so --fix leaves it" in out
    assert has_ref(repo, "refs/heads/feature/rm-borrowed")
    assert "[ok] deleted local branch feature/rm-open" in out   # unmerged with commits: policy unchanged


def test_r4_a_claim_beats_a_session_and_a_session_alone_still_protects(doctor_repo, capsys) -> None:
    repo, _bare = doctor_repo
    with (repo / ".git" / "info" / "exclude").open("a") as f:
        f.write("work/.sessions/\n")   # a consumer ignores work/; registry-prune needs a clean tree
    session_presence.start_session(repo, "claim-session", paths=[], worktree=repo.parent / "wt-thing")
    empty = repo.parent / "wt-empty"
    git(repo, "worktree", "add", "-q", "-b", "feature/rm-empty", str(empty), "dev")
    session_presence.start_session(repo, "lone-session", paths=[], worktree=empty)

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert kept(out, "wt-thing: branch feature/rm-thing live: claimed by M1.1, so --fix leaves it")
    assert "live: session claim-session" not in out
    assert kept(out, "wt-empty: branch feature/rm-empty live: session lone-session, so --fix leaves it")
    assert "[kept] local feature/rm-empty: live: session lone-session, so --fix leaves it" in out
    assert empty.is_dir() and (repo.parent / "wt-thing").is_dir()


def test_r5_f1_a_copy_of_a_merged_branch_has_no_commits_of_its_own(doctor_repo, capsys) -> None:
    """``git branch -c`` copies the source's reflog: its commit entries were made on the source."""
    repo, _bare = doctor_repo
    git(repo, "branch", "-c", "feature/rm-done", "feature/rm-copied")

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[kept] local feature/rm-copied: claim gone, no commits yet, so --fix leaves it" in out
    assert "deleted local branch feature/rm-copied" not in out
    assert has_ref(repo, "refs/heads/feature/rm-copied")
    assert "[ok] deleted local branch feature/rm-done" in out   # the source keeps its evidence


def test_r5_f2_a_local_namesake_at_the_remote_tip_keeps_the_remotes_finish_merge(doctor_repo, capsys) -> None:
    """Only the local branch is new: origin's feature/rm-gone still landed by a finish merge."""
    repo, bare = doctor_repo
    git(repo, "branch", "feature/rm-gone", git(repo, "rev-parse", "origin/feature/rm-gone"))

    assert run_doctor(repo) == 0
    out = capsys.readouterr().out
    assert "origin    feature/rm-gone  — merged\n" in out
    assert "local     feature/rm-gone  — claim gone, no commits yet, so --fix leaves it" in out

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert "[ok] deleted feature/rm-gone on origin" in out
    assert not has_ref(bare, "refs/heads/feature/rm-gone")
    assert has_ref(repo, "refs/heads/feature/rm-gone")


def test_r5_f2_a_namesake_created_after_the_remote_ref_does_not_prove_it_fresh(doctor_repo, capsys) -> None:
    """A fast-forward-landed remote branch (no finish merge) and a local namesake recreated at its
    tip later: the remote is merged without evidence, never "no commits yet"."""
    repo, bare = doctor_repo
    tip = _fast_forwarded(repo)
    git(repo, "branch", "-q", "-D", "feature/rm-ff")
    log = Path(git(repo, "rev-parse", "--git-path", "logs/refs/remotes/origin/feature/rm-ff"))
    log = log if log.is_absolute() else repo / log
    old, new, rest = log.read_text().split(" ", 2)
    who, _, subject = rest.partition("\t")
    name, when, tz = who.rsplit(" ", 2)
    log.write_text(f"{old} {new} {name} {int(when) - 60} {tz}\t{subject}")   # pushed a minute earlier
    git(repo, "branch", "feature/rm-ff", tip)

    assert run_doctor(repo, "--fix", "--yes") == 0
    out = capsys.readouterr().out
    assert kept(out, f"origin feature/rm-ff: merged; {NO_EVIDENCE}")
    assert git(bare, "rev-parse", "feature/rm-ff") == tip
