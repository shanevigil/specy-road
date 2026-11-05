"""M15.40: a failed merge landing reports last and undoes its bookkeeping commit.

finish-this-task runs in a sandbox with a bare ``origin`` and a passing land
check, stdout and stderr merged into one pipe (as ``finish-this-task 2>&1 | tee``).
"""

from __future__ import annotations

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
