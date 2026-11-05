"""M15.40: a failed merge landing reports last and undoes its bookkeeping commit.

finish-this-task runs in a sandbox with a bare ``origin`` and a passing land
check, stdout and stderr merged into one pipe (as ``finish-this-task 2>&1 | tee``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

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


def _repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    repo, bare = merge_mode_finish_repo(tmp_path, monkeypatch)
    commit_file(
        repo, "roadmap/git-workflow.yaml",
        "version: 1\nintegration_branch: dev\nremote: origin\non_complete: merge\n"
        f"land_check_cmd: {CHECK!r}\n",
        "land check",
    )
    commit_file(repo, "work/implementation-summary-M1.1.md", SUMMARY, "summary")
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
    last_error = lines[ours[0]]
    assert reason in out[out.index(last_error):], out
    assert "run `specy-road finish-this-task` again" in out, out
    assert "[ok] merged" not in out
    # The branch, its claim and the work files are as they were before finish.
    assert git(repo, "branch", "--show-current") == BRANCH
    assert git(repo, "rev-parse", BRANCH) == pre
    assert git(repo, "status", "--porcelain", "--untracked-files=no") == ""
    reg = yaml.safe_load(git(repo, "show", f"{BRANCH}:roadmap/registry.yaml"))
    assert any(e.get("codename") == "thing" for e in reg["entries"])
    assert (repo / "work" / "brief-M1.1.md").read_bytes() == BRIEF
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


def test_undo_failure_names_the_reset(capsys) -> None:
    """A2: when the undo fails, the error says so and names git reset --keep <sha>."""
    import pytest

    from specy_road.finish_modes import merge_landing_failed

    with pytest.raises(SystemExit) as exc:
        merge_landing_failed("dev", "push failed", undo=("abc123", "git reset --keep abc123 failed: x"))
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "could not undo the bookkeeping commit" in err
    assert "`git reset --keep abc123`" in err
