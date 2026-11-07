"""M15.40: a failed merge landing reports last and undoes its bookkeeping commit.

finish-this-task runs in a sandbox with a bare ``origin`` and a passing land
check, stdout and stderr merged into one pipe (as ``finish-this-task 2>&1 | tee``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specy_road.finish_bookkeeping_undo import (
    BookkeepingSnapshot,
    snapshot_bookkeeping,
    undo_bookkeeping,
)
from specy_road.finish_modes import merge_landing_failed

from tests.helpers import REPO
from tests.review_repo_helpers import commit_file, git
from tests.test_finish_merge_mode import merge_mode_finish_repo

BRANCH = "feature/rm-thing"
CHECK = "echo LAND-CHECK-OUTPUT; echo '3 passed'"
BRIEF = b"# brief M1.1\n\nbytes \xe2\x80\x94 kept\n"
SUMMARY = "# summary M1.1\n\nwhat changed\n"

#: Runs finish with ``land_on_integration`` replaced by one that runs the real
#: land check (so its output streams first) and then raises.
_RAISING = """
import sys
from pathlib import Path
from unittest import mock
from specy_road.finish_land_check import resolve_land_check_cmd, run_land_check
import specy_road.finish_modes as fm

def boom(repo, *, land_check_cmd, **_kw):
    cmd = resolve_land_check_cmd(Path(repo), cli=land_check_cmd)
    assert run_land_check(Path(repo), cmd) is None
    raise OSError("simulated landing crash")

with mock.patch.object(fm, "land_on_integration", boom):
    from specy_road.bundled_scripts.finish_task import main
    main(sys.argv[1:])
"""


def _repo(tmp_path: Path, monkeypatch, *, brief_link: bool = False) -> tuple[Path, Path]:
    repo, bare = merge_mode_finish_repo(tmp_path, monkeypatch)
    commit_file(
        repo, "roadmap/git-workflow.yaml",
        "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n"
        f"land_check_cmd: {CHECK!r}\n",
        "land check",
    )
    commit_file(repo, "work/implementation-summary-M1.1.md", SUMMARY, "summary")
    if brief_link:   # an ignored brief symlink to an untracked file in the repo: cleanup deletes the target
        commit_file(repo, ".gitignore", (repo / ".gitignore").read_text() + "work/brief-M1.1.md\n", "ignore")
        (repo / "notes").mkdir()
        (repo / "notes" / "brief.md").write_bytes(BRIEF)
        (repo / "work" / "brief-M1.1.md").symlink_to("../notes/brief.md")
    else:
        (repo / "work" / "brief-M1.1.md").write_bytes(BRIEF)
    return repo, bare


def _run(repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, *argv, "--repo-root", str(repo)], cwd=repo, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
    )


def _assert_reported_last_and_undone(repo: Path, result, pre: str, reason: str) -> None:
    out = result.stdout
    assert result.returncode == 1, out
    lines = out.splitlines()
    check_at = max(i for i, line in enumerate(lines) if "3 passed" in line)
    errors = [i for i, line in enumerate(lines) if line.startswith("error:")]
    assert errors and errors[-1] > check_at, out
    ours = [i for i in errors if lines[i].startswith("error: could not land merge to dev:")]
    assert len(ours) == 1 and ours[0] > check_at, out
    assert reason in lines[ours[0]], out   # the reason is on that one line (A1)
    after = [line for line in lines[ours[0] + 1:] if line.strip()]
    assert len(after) == 1 and after[0].startswith("--on-complete merge cannot fall back"), out
    assert "run `specy-road finish-this-task` again" in out, out
    assert "[ok] merged" not in out
    # The branch, its claim and the work files are as they were before finish.
    assert git(repo, "branch", "--show-current") == BRANCH
    assert git(repo, "rev-parse", BRANCH) == pre
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    reg = yaml.safe_load(git(repo, "show", f"{BRANCH}:roadmap/registry.yaml"))
    assert any(e.get("codename") == "thing" for e in reg["entries"])
    assert (repo / "work" / "brief-M1.1.md").read_bytes() == BRIEF   # through a symlink too
    assert (repo / "work" / "implementation-summary-M1.1.md").read_text() == SUMMARY
    assert not (repo / "work" / "done" / "implementation-summary-M1.1.md").exists()


def test_push_rejected_by_remote_reports_last_and_undoes(tmp_path: Path, monkeypatch) -> None:
    """A4(a): a pre-receive hook rejects the push."""
    repo, bare = _repo(tmp_path, monkeypatch)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'fatal error in commit_refs' >&2\nexit 1\n")
    hook.chmod(0o755)
    pre = git(repo, "rev-parse", "HEAD")
    dev_before = git(bare, "rev-parse", "dev")
    result = _run(repo, ["-m", "specy_road.cli", "finish-this-task"])
    _assert_reported_last_and_undone(repo, result, pre, "remote rejected")
    assert git(bare, "rev-parse", "dev") == dev_before


def test_landing_exception_reports_last_and_undoes(tmp_path: Path, monkeypatch) -> None:
    """A4(b): land_on_integration raises OSError."""
    repo, _bare = _repo(tmp_path, monkeypatch)
    pre = git(repo, "rev-parse", "HEAD")
    result = _run(repo, ["-c", _RAISING])
    _assert_reported_last_and_undone(repo, result, pre, "OSError: simulated landing crash")


def test_symlinked_brief_target_is_restored(tmp_path: Path, monkeypatch) -> None:
    """Review round 1: cleanup deletes a brief symlink's in-repo target, so the undo restores the target."""
    repo, bare = _repo(tmp_path, monkeypatch, brief_link=True)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    pre = git(repo, "rev-parse", "HEAD")
    result = _run(repo, ["-m", "specy_road.cli", "finish-this-task"])
    _assert_reported_last_and_undone(repo, result, pre, "remote rejected")
    assert (repo / "work" / "brief-M1.1.md").is_symlink()
    assert (repo / "notes" / "brief.md").read_bytes() == BRIEF


def test_multiline_reason_is_one_error_line_and_kept_in_full(capsys) -> None:
    """A1: one outcome line; the full reason goes to stdout before it."""
    with pytest.raises(SystemExit):
        merge_landing_failed("dev", "first line\n  second line\n")
    out, err = capsys.readouterr()
    assert "  first line\n    second line" in out   # the full text, as git wrote it
    errors = [line for line in err.splitlines() if line.startswith("error:")]
    assert errors == ["error: could not land merge to dev: first line / second line"]


def _undo_repo(tmp_path: Path) -> tuple[Path, BookkeepingSnapshot]:
    """A branch with a snapshot taken, then a stand-in bookkeeping commit that changed f.txt and removed the brief."""
    repo = tmp_path / "u"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "feature/rm-x")
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    commit_file(repo, "f.txt", "1\n", "base")
    (repo / "work").mkdir()
    (repo / "work" / "brief-X.md").write_bytes(BRIEF)
    snap = snapshot_bookkeeping(repo, branch="feature/rm-x", node_id="X", sess_path=None)
    assert snap is not None and snap.entries["work/brief-X.md"] == ("file", BRIEF)
    (repo / "work" / "brief-X.md").unlink()
    commit_file(repo, "f.txt", "2\n", "chore(rm-x): complete, deregister")
    return repo, snap


def test_reset_failure_keeps_untracked_files_and_names_the_reset(tmp_path: Path, capsys) -> None:
    """A2: the reset fails, so the commit is still on the branch; the brief is back regardless."""
    repo, snap = _undo_repo(tmp_path)
    (repo / "f.txt").write_text("3\n")   # a local change git reset --keep refuses to drop
    outcome = undo_bookkeeping(repo, snap)
    assert outcome.git_error and not outcome.unrestored
    assert (repo / "work" / "brief-X.md").read_bytes() == BRIEF
    with pytest.raises(SystemExit):
        merge_landing_failed("dev", "push failed", undo=outcome)
    err = capsys.readouterr().err
    assert "error: could not undo the bookkeeping commit: git reset --keep" in err
    assert "the commit is still on feature/rm-x; its untracked work files are back" in err
    assert f"run `git reset --keep {snap.pre_sha}`, then `specy-road finish-this-task`" in err


def test_restore_failure_after_reset_saves_a_copy(tmp_path: Path, capsys) -> None:
    """A2: the reset worked, so the message says so, and names the copy of the file it could not write."""
    repo, snap = _undo_repo(tmp_path)
    (repo / "work" / "brief-X.md").mkdir()   # writing the brief back now fails
    outcome = undo_bookkeeping(repo, snap)
    assert outcome.git_error is None and list(outcome.unrestored) == ["work/brief-X.md"]
    assert git(repo, "rev-parse", "HEAD") == snap.pre_sha
    saved = Path(outcome.unrestored["work/brief-X.md"].rsplit("saved at ", 1)[1])
    assert saved.read_bytes() == BRIEF
    with pytest.raises(SystemExit):
        merge_landing_failed("dev", "push failed", undo=outcome)
    err = capsys.readouterr().err
    assert f"undid the bookkeeping commit (feature/rm-x is back at {snap.pre_sha[:12]}" in err
    assert f"saved at {saved}" in err
    assert "still on" not in err
    assert "put each file named above back at its path, then run `specy-road finish-this-task`" in err


#: Finish as a version before M15.40's undo ran it: a failed landing keeps the bookkeeping commit.
_NO_UNDO = """
import sys
from unittest import mock
import specy_road.bundled_scripts.finish_task as ft
with mock.patch.object(ft, "merge_undo_snapshot", lambda *_a: None):
    ft.main(sys.argv[1:])
"""


def _last_line(result) -> str:
    return [line for line in result.stdout.splitlines() if line.strip()][-1]


@pytest.mark.parametrize("options", [
    [],
    ["--delete-branch"],
    ["--delete-branch", "--push", "--no-cleanup-work"],
    ["--delete-branch", "--land-check-cmd", CHECK],
])
def test_a_landed_finish_prints_its_outcome_last(tmp_path: Path, monkeypatch, options) -> None:
    """A landing still prints its outcome. With --delete-branch that line stays last; otherwise the checkout guidance is last."""
    repo, _bare = _repo(tmp_path, monkeypatch)
    result = _run(repo, ["-m", "specy_road.cli", "finish-this-task", *options])
    assert result.returncode == 0, result.stdout
    outcome = f"[ok] merged {BRANCH} into dev and pushed to origin"
    if "--delete-branch" in options:
        assert _last_line(result) == outcome, result.stdout
        assert f"[ok] deleted local branch {BRANCH}" in result.stdout
    else:
        assert outcome in result.stdout
        assert _last_line(result) == (
            f"[ok] this checkout is still on {BRANCH} (landed into dev); next: git switch dev"
        ), result.stdout


def test_a_retried_landing_prints_its_outcome_last(tmp_path: Path, monkeypatch) -> None:
    """A retry prints its outcome. With no --delete-branch the checkout guidance is last; with it the outcome stays last."""
    repo, bare = _repo(tmp_path, monkeypatch)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    assert _run(repo, ["-c", _NO_UNDO]).returncode == 1   # bookkeeping kept, as an older finish left it
    hook.unlink()
    landed = _run(repo, ["-m", "specy_road.cli", "finish-this-task", "--on-complete", "merge"])
    assert landed.returncode == 0, landed.stdout
    assert f"[ok] merged {BRANCH} into dev and pushed to origin" in landed.stdout
    assert _last_line(landed) == (
        f"[ok] this checkout is still on {BRANCH} (landed into dev); next: git switch dev"
    ), landed.stdout
    again = _run(repo, ["-m", "specy_road.cli", "finish-this-task", "--on-complete", "merge", "--delete-branch"])
    assert again.returncode == 0, again.stdout
    assert f"[ok] deleted local branch {BRANCH}" in again.stdout
    assert _last_line(again) == f"[ok] {BRANCH} is already merged into dev on origin", again.stdout


def test_locally_modified_tracked_documents_come_back_as_they_were(tmp_path: Path, monkeypatch) -> None:
    """Review round 3: after a rejected push, tracked work documents carry their pre-finish bytes, not HEAD's."""
    repo, bare = _repo(tmp_path, monkeypatch)
    docs = ("work/brief-M1.1.md", "work/prompt-M1.1.md", "work/implementation-summary-M1.1.md")
    for rel in docs[:2]:
        commit_file(repo, rel, f"committed {rel}\n", f"track {rel}")
    local = {rel: f"local edit of {rel} — not committed\n".encode() for rel in docs}
    for rel, data in local.items():
        (repo / rel).write_bytes(data)
    hook = bare / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    pre = git(repo, "rev-parse", "HEAD")
    result = _run(repo, ["-m", "specy_road.cli", "finish-this-task"])
    assert result.returncode == 1, result.stdout
    assert "[ok] undid the bookkeeping commit" in result.stdout, result.stdout
    assert git(repo, "rev-parse", BRANCH) == pre
    for rel, data in local.items():
        assert (repo / rel).read_bytes() == data, rel
    assert sorted(git(repo, "diff", "--name-only").splitlines()) == sorted(docs)   # modified, as before
    assert git(repo, "diff", "--cached", "--name-only") == ""
    assert not (repo / "work" / "done" / "implementation-summary-M1.1.md").exists()


def test_reset_failure_saves_modified_tracked_documents(tmp_path: Path, capsys) -> None:
    """The same class when the reset fails: a modified tracked document is saved and named, never lost."""
    repo = tmp_path / "t"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "feature/rm-x")
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    commit_file(repo, "f.txt", "1\n", "base")
    commit_file(repo, "work/brief-X.md", "committed\n", "brief")
    (repo / "work" / "brief-X.md").write_bytes(BRIEF)   # modified, not committed
    snap = snapshot_bookkeeping(repo, branch="feature/rm-x", node_id="X", sess_path=None)
    assert snap is not None and snap.entries["work/prompt-X.md"] == ("absent", b"")
    git(repo, "rm", "-qf", "work/brief-X.md")
    commit_file(repo, "f.txt", "2\n", "chore(rm-x): complete, deregister")
    (repo / "f.txt").write_text("3\n")   # git reset --keep refuses
    outcome = undo_bookkeeping(repo, snap)
    assert outcome.git_error and list(outcome.unrestored) == ["work/brief-X.md"]
    saved = Path(outcome.unrestored["work/brief-X.md"].rsplit("saved at ", 1)[1])
    assert saved.read_bytes() == BRIEF
    with pytest.raises(SystemExit):
        merge_landing_failed("dev", "push failed", undo=outcome)
    err = capsys.readouterr().err
    assert f"saved at {saved}" in err
    assert f"run `git reset --keep {snap.pre_sha}`, put each saved file named above back at its path," in err


def _state(path: Path) -> tuple[str, str | bytes]:
    """What is at ``path``, without following a link."""
    if path.is_symlink():
        return ("link", os.readlink(path))
    return ("file", path.read_bytes()) if path.exists() else ("absent", b"")


_KINDS = {"file": (("file", b"committed A\n"), ("file", b"local B\n")),
          "link": (("link", "../tgt-a"), ("link", "../tgt-b"))}


def _put(path: Path, state: tuple[str, str | bytes]) -> None:
    if os.path.lexists(path):
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    if state[0] == "link":
        path.symlink_to(state[1])
    else:
        path.write_bytes(state[1])


def _feature_checkout_hook(repo: Path) -> None:
    """A post-checkout hook that fails only ``git checkout`` of the feature branch."""
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text(
        "#!/bin/sh\n"
        "ref=$(git symbolic-ref -q HEAD || true)\n"
        f"case $ref in refs/heads/{BRANCH}) exit 1 ;; esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


def _set_land(repo: Path, land: str) -> None:
    text = (repo / "roadmap" / "git-workflow.yaml").read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    commit_file(repo, "roadmap/git-workflow.yaml", f"{text}land: {land}\n", f"land: {land}")


def _clash(repo: Path) -> None:
    """A non-bookkeeping conflict, so the integration merge fails."""
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "src/clash.py", "dev = 1\n", "dev clash")
    git(repo, "checkout", "-q", BRANCH)
    commit_file(repo, "src/clash.py", "feature = 1\n", "feature clash")


def _separated(repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, *argv, "--repo-root", str(repo)], cwd=repo, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )


_CHECKOUT_WARNING = (
    "warning: landing succeeded, but checking out the feature branch failed; "
    f"run `git checkout {BRANCH}`"
)


def _node_status(repo: Path, ref: str) -> str:
    nodes = json.loads(git(repo, "show", f"{ref}:roadmap/phases/M1.json"))["nodes"]
    return next(n["status"] for n in nodes if n["id"] == "M1.1")


@pytest.mark.parametrize("case", ["local", "push", "merge-fails"])
def test_feature_checkout_failure_keeps_a_landed_finish(tmp_path: Path, monkeypatch, case: str) -> None:
    """A2: a post-checkout failure after a successful landing warns and keeps the bookkeeping.

    ``local`` and ``push`` exit 0: integration holds the completion, the feature
    branch keeps its bookkeeping commit, one stderr warning, no advice to run
    finish again. ``merge-fails``: the merge fails as well, so bookkeeping is undone.
    """
    repo, bare = _repo(tmp_path, monkeypatch)
    if case == "local":
        _set_land(repo, "local")
    if case == "merge-fails":
        _clash(repo)
    _feature_checkout_hook(repo)
    pre = git(repo, "rev-parse", "HEAD")
    remote_dev = git(bare, "rev-parse", "dev")
    result = _separated(repo, ["-m", "specy_road.cli", "finish-this-task"])
    out = result.stdout + result.stderr
    if case == "merge-fails":
        assert result.returncode == 1, out
        assert "src/clash.py" in out
        assert git(repo, "rev-parse", BRANCH) == pre
        assert "run `specy-road finish-this-task` again" in out
        reg = yaml.safe_load(git(repo, "show", f"{BRANCH}:roadmap/registry.yaml"))
        assert any(e.get("codename") == "thing" for e in reg["entries"])
        return
    assert result.returncode == 0, out
    checkout_lines = [ln for ln in result.stderr.splitlines() if f"git checkout {BRANCH}" in ln]
    assert checkout_lines == [_CHECKOUT_WARNING]
    assert "run `specy-road finish-this-task` again" not in out and "finish again" not in out
    assert git(repo, "rev-parse", BRANCH) != pre
    assert "complete, deregister" in git(repo, "log", "-1", "--format=%s", BRANCH)
    reg = yaml.safe_load(git(repo, "show", f"{BRANCH}:roadmap/registry.yaml"))
    assert not any(e.get("codename") == "thing" for e in reg.get("entries") or [])
    where = repo if case == "local" else bare
    assert _node_status(where, "dev") == "Complete"
    if case == "local":
        git(repo, "merge-base", "--is-ancestor", BRANCH, "dev")
        assert git(bare, "rev-parse", "dev") == remote_dev
        done = f"[ok] merged {BRANCH} into local dev (land: local); nothing pushed to origin"
    else:
        git(bare, "merge-base", "--is-ancestor", git(repo, "rev-parse", BRANCH), "dev")
        done = f"[ok] merged {BRANCH} into dev and pushed to origin"
    assert done in result.stdout
    # The hook fails after HEAD is already the feature branch, so the guidance is the final line.
    assert _last_line(result) == (
        f"[ok] this checkout is still on {BRANCH} (landed into dev); next: git switch dev"
    ), result.stdout


@pytest.mark.parametrize("tracked", [True, False], ids=["tracked", "untracked"])
@pytest.mark.parametrize("kind", ["file", "link"])
@pytest.mark.parametrize("changed", [True, False], ids=["changed", "unchanged"])
def test_undo_restores_the_exact_pre_finish_state(tmp_path: Path, tracked: bool, kind: str, changed: bool) -> None:
    """Review round 4: whatever the reset or a later write left at the path, the undo puts back the snapshot state.

    tracked: committed as A; ``changed`` edits it locally to B before finish
    (so the reset brings back A, which is wrong). untracked: B before finish;
    ``changed`` leaves A there after the bookkeeping commit. Links compare by target.
    """
    repo = tmp_path / "s"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "feature/rm-x")
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    commit_file(repo, "f.txt", "1\n", "base")
    brief = repo / "work" / "brief-X.md"
    committed, local = _KINDS[kind]
    if tracked:
        _put(brief, committed)
        git(repo, "add", "work/brief-X.md")
        git(repo, "commit", "-qm", "track brief")
        if changed:
            _put(brief, local)
    else:
        _put(brief, local)
    before = _state(brief)
    snap = snapshot_bookkeeping(repo, branch="feature/rm-x", node_id="X", sess_path=None)
    assert snap is not None and snap.entries["work/brief-X.md"] == before
    if tracked:
        git(repo, "rm", "-qf", "work/brief-X.md")
    else:
        brief.unlink()
    commit_file(repo, "f.txt", "2\n", "chore(rm-x): complete, deregister")
    if not tracked and changed:
        _put(brief, committed)   # something else at the path when the undo runs
    outcome = undo_bookkeeping(repo, snap)
    assert outcome.git_error is None and not outcome.unrestored
    assert git(repo, "rev-parse", "HEAD") == snap.pre_sha
    assert _state(brief) == before
    assert _state(repo / "work" / "prompt-X.md") == ("absent", b"")
