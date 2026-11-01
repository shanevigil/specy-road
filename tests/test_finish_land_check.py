"""M9.1: merge mode runs the configured land check on the merge commit before it pushes.

Every test runs in both layouts: embedded (project root == git root) and nested
(project under ``sr/``), where the check must run at ``<worktree>/sr``.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from specy_road.finish_land_integration import land_merge_feature_into_integration
from specy_road.finish_modes import apply_on_complete_mode, merge_landing_failed


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(cwd: Path, path: Path, text: str, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-qm", message)


@pytest.fixture(params=["embedded", "nested"])
def sandbox(request: pytest.FixtureRequest, tmp_path: Path) -> dict:
    """A checkout on ``feature/rm-x`` with ``main`` pushed to a bare ``origin``."""
    prefix = "" if request.param == "embedded" else "sr/"
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-q", "-b", "main", str(bare))
    top = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(top))
    _git(top, "config", "user.email", "t@e.com")
    _git(top, "config", "user.name", "T")
    _git(top, "remote", "add", "origin", str(bare))
    project = (top / prefix).resolve()
    _commit(top, project / "base.txt", "base\n", "init")
    _git(top, "push", "-q", "-u", "origin", "main")
    _git(top, "checkout", "-qb", "feature/rm-x")
    _commit(top, project / "feature.txt", "feature\n", "feature work")
    return {"top": top, "project": project, "bare": bare, "prefix": prefix,
            "log": tmp_path / "check.log", "tmp": tmp_path}


def _recorder(sb: dict, tail: str = "") -> str:
    """A check that logs where and on what it ran, and what origin's main was then."""
    log, bare = shlex.quote(str(sb["log"])), shlex.quote(str(sb["bare"]))
    rec = (
        f'echo "$(pwd -P)|$(git rev-parse --show-toplevel)|$(git rev-parse --show-prefix)'
        f'|$(git rev-parse HEAD)|$(git symbolic-ref -q HEAD || echo detached)'
        f'|$(git --git-dir={bare} rev-parse main)" >> {log}'
    )
    return f"{rec}{tail}"


def _runs(sb: dict) -> list[list[str]]:
    if not sb["log"].is_file():
        return []
    return [line.split("|") for line in sb["log"].read_text().splitlines()]


def _worktrees(sb: dict) -> list[str]:
    """Each worktree's path and branch (not its HEAD, which a landing moves)."""
    out = _git(sb["top"], "worktree", "list", "--porcelain")
    return [line for line in out.splitlines() if not line.startswith("HEAD ")]


def _land(sb: dict, cli: str | None) -> tuple[bool, str]:
    return land_merge_feature_into_integration(
        sb["project"], remote="origin", integration_branch="main",
        feature_branch="feature/rm-x", land_check_cmd=cli,
    )


def _other_lane(sb: dict) -> Path:
    """A second clone of origin holding one unpushed commit on ``main``."""
    other = sb["tmp"] / "other"
    _git(sb["tmp"], "clone", "-q", str(sb["bare"]), str(other))
    _git(other, "config", "user.email", "o@e.com")
    _git(other, "config", "user.name", "O")
    _commit(other, other / "other.txt", "other\n", "other lane")
    return other


def _assert_ran_in_detached_worktree(sb: dict, run: list[str]) -> None:
    cwd, toplevel, prefix, _sha, ref, _remote_main = run
    assert ref == "detached"
    assert prefix == sb["prefix"]
    assert Path(cwd) == Path(toplevel) / sb["prefix"]
    assert Path(toplevel).resolve() != sb["top"].resolve()
    assert not Path(toplevel).exists()  # removed after the check


def test_passing_check_runs_once_on_the_merge_commit_then_pushes(sandbox: dict) -> None:
    """A1, A2, A5, A7."""
    before_remote = _git(sandbox["top"], "rev-parse", "origin/main")
    before_wt = _worktrees(sandbox)
    ok, err = _land(sandbox, _recorder(sandbox))
    assert ok, err
    (run,) = _runs(sandbox)
    _assert_ran_in_detached_worktree(sandbox, run)
    sha, remote_main_then = run[3], run[5]
    assert remote_main_then == before_remote  # ran before the push
    assert _git(sandbox["top"], f"--git-dir={sandbox['bare']}", "rev-parse", "main") == sha
    assert _git(sandbox["top"], "rev-list", "--parents", "-n1", sha).count(" ") == 2  # merge commit
    assert _worktrees(sandbox) == before_wt
    assert _git(sandbox["top"], "branch", "--show-current") == "feature/rm-x"


def test_failing_check_pushes_nothing_and_restores_both_refs(sandbox: dict) -> None:
    """A3, A5, A7. Origin moved before finish, so its fetch advances origin/main."""
    top = sandbox["top"]
    _git(_other_lane(sandbox), "push", "-q", "origin", "main")
    remote_tip = _git(top, f"--git-dir={sandbox['bare']}", "rev-parse", "main")
    local, tracking = _git(top, "rev-parse", "main"), _git(top, "rev-parse", "origin/main")
    assert tracking != remote_tip
    before_wt = _worktrees(sandbox)
    noisy = "; for i in $(seq 1 25); do echo line$i; done; exit 3"
    ok, err = _land(sandbox, _recorder(sandbox, noisy))
    assert not ok
    assert len(_runs(sandbox)) == 1
    _assert_ran_in_detached_worktree(sandbox, _runs(sandbox)[0])
    assert "exit code: 3" in err
    assert "line25" in err and shlex.quote(str(sandbox["log"])) in err
    shown = [line.strip() for line in err.splitlines()]
    assert "line6" in shown and "line5" not in shown
    assert _git(top, "rev-parse", "main") == local
    assert _git(top, "rev-parse", "origin/main") == tracking
    assert _git(top, f"--git-dir={sandbox['bare']}", "rev-parse", "main") == remote_tip
    assert _worktrees(sandbox) == before_wt
    assert _git(top, "status", "--porcelain", "--untracked-files=no") == ""


def test_finish_restores_the_tracking_ref_its_notice_fetched(sandbox: dict) -> None:
    """A3 through finish's merge path, whose push notice fetches before the landing does."""
    top = sandbox["top"]
    _git(_other_lane(sandbox), "push", "-q", "origin", "main")
    local, tracking = _git(top, "rev-parse", "main"), _git(top, "rev-parse", "origin/main")
    args = argparse.Namespace(land_check_cmd="exit 3", delete_branch=False, push=False)
    with pytest.raises(SystemExit) as exc:
        apply_on_complete_mode(
            sandbox["project"], args, on_mode="merge", branch="feature/rm-x",
            sess_path=sandbox["tmp"] / "session.yaml", ib="main", gw_remote="origin",
            mr_manual=False, node_id="M1", node={},
        )
    assert exc.value.code == 1
    assert _git(top, "rev-parse", "main") == local
    assert _git(top, "rev-parse", "origin/main") == tracking


def test_failing_check_leaves_an_absent_tracking_ref_absent(sandbox: dict) -> None:
    """A3 when finish's fetch is what creates origin/main."""
    top = sandbox["top"]
    _git(top, "update-ref", "-d", "refs/remotes/origin/main")
    ok, _err = _land(sandbox, "exit 3")
    assert not ok
    shown = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"],
        cwd=top, capture_output=True, check=False,
    )
    assert shown.returncode == 1


def test_a_stale_registration_elsewhere_survives_the_check(sandbox: dict) -> None:
    """A5: only the check's own worktree is cleaned up, never another one's registration."""
    stale = sandbox["tmp"] / "stale"
    _git(sandbox["top"], "worktree", "add", "-q", "--detach", str(stale), "main")
    shutil.rmtree(stale)
    before_wt = _worktrees(sandbox)
    assert any(line.startswith("prunable") for line in before_wt)
    ok, _err = _land(sandbox, "exit 3")
    assert not ok
    assert _worktrees(sandbox) == before_wt
    ok, err = _land(sandbox, "true")
    assert ok, err
    assert _worktrees(sandbox) == before_wt


def test_rejected_push_resets_and_a_rerun_checks_the_new_tip(sandbox: dict) -> None:
    """A4, A5, A7: the check lets another lane land first, so the push is rejected."""
    other = _other_lane(sandbox)
    marker = sandbox["tmp"] / "raced"
    race = (
        f"; if [ ! -e {shlex.quote(str(marker))} ]; then touch {shlex.quote(str(marker))}; "
        f"git -C {shlex.quote(str(other))} push -q origin main; fi"
    )
    top = sandbox["top"]
    local = _git(top, "rev-parse", "main")
    before_wt = _worktrees(sandbox)

    ok, err = _land(sandbox, _recorder(sandbox, race))
    assert not ok
    assert "git push origin main failed" in err and "re-running" in err
    assert _git(top, "rev-parse", "main") == local
    assert _worktrees(sandbox) == before_wt

    ok, err = _land(sandbox, _recorder(sandbox, race))
    assert ok, err
    first, second = _runs(sandbox)
    assert first[3] != second[3]
    pushed = _git(top, f"--git-dir={sandbox['bare']}", "rev-parse", "main")
    assert pushed == second[3]
    _git(top, "merge-base", "--is-ancestor", _git(other, "rev-parse", "HEAD"), pushed)
    assert _worktrees(sandbox) == before_wt


def test_check_runs_in_a_worktree_of_the_holders_merge(sandbox: dict) -> None:
    """A1, A3, A5, A7 when another worktree holds ``main`` (the worker-delegate layout)."""
    top = sandbox["top"]
    holder = sandbox["tmp"] / "holder"
    _git(top, "worktree", "add", "-q", str(holder), "main")
    before_wt = _worktrees(sandbox)
    local = _git(holder, "rev-parse", "HEAD")

    ok, _err = _land(sandbox, _recorder(sandbox, "; exit 1"))
    assert not ok
    _assert_ran_in_detached_worktree(sandbox, _runs(sandbox)[0])
    assert _git(holder, "rev-parse", "HEAD") == local
    assert _git(holder, "status", "--porcelain", "--untracked-files=no") == ""
    assert _worktrees(sandbox) == before_wt

    ok, err = _land(sandbox, _recorder(sandbox))
    assert ok, err
    assert _runs(sandbox)[1][3] == _git(holder, "rev-parse", "HEAD")
    assert _worktrees(sandbox) == before_wt


def _configure(sb: dict, cmd: str) -> None:
    cfg = sb["project"] / "roadmap" / "git-workflow.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        "version: 1\nintegration_branch: main\nremote: origin\n"
        f"land_check_cmd: {cmd!r}\n",
        encoding="utf-8",
    )


def test_configured_key_runs_without_a_flag(sandbox: dict) -> None:
    """A1 via ``land_check_cmd`` in ``roadmap/git-workflow.yaml``."""
    _configure(sandbox, _recorder(sandbox, "; exit 1"))
    ok, err = _land(sandbox, None)
    assert not ok and "exit code: 1" in err
    assert len(_runs(sandbox)) == 1


def test_flag_overrides_the_key_and_empty_skips(sandbox: dict) -> None:
    """A6."""
    _configure(sandbox, "exit 1")
    ok, err = _land(sandbox, "")
    assert ok, err
    _git(sandbox["top"], "commit", "-qm", "more", "--allow-empty")
    ok, err = _land(sandbox, _recorder(sandbox))
    assert ok, err
    assert len(_runs(sandbox)) == 1


def test_no_flag_and_no_key_runs_no_check(sandbox: dict) -> None:
    """A6: off by default."""
    before_wt = _worktrees(sandbox)
    ok, err = _land(sandbox, None)
    assert ok, err
    assert _worktrees(sandbox) == before_wt


def test_failure_names_the_rerun_with_the_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """A3/A4: the error goes to stderr with the finish-this-task command that retries it."""
    with pytest.raises(SystemExit) as exc:
        merge_landing_failed("main", "land check failed", land_check_cmd="make check")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "land check failed" in err
    assert "specy-road finish-this-task --on-complete merge --land-check-cmd 'make check'" in err


def test_parser_accepts_the_flag() -> None:
    from specy_road.bundled_scripts.finish_task_args import parse_finish_args

    assert parse_finish_args([]).land_check_cmd is None
    assert parse_finish_args(["--land-check-cmd", ""]).land_check_cmd == ""
    assert parse_finish_args(["--land-check-cmd", "make check"]).land_check_cmd == "make check"
