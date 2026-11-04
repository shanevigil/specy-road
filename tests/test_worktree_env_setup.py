"""M11.30: ``env_setup`` in ``roadmap/git-workflow.yaml`` sets up a leaf worktree when pickup or delegate creates it.

Each project ignores the files the setup copies or makes through ``.git/info/exclude``, which every linked
worktree shares, so they never count as uncommitted changes there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.pickup_repo_helpers import make_pickup_project, run_pickup, run_specy_road
from tests.review_repo_helpers import git
from tests.test_worker_cli import run_worker_cli, wait_for_worker
from tests.worker_repo_helpers import make_worker_repo

from specy_road import worker_state as ws
from specy_road.bundled_scripts import doctor_env_setup as des
from specy_road.git_workflow_config import validate_git_workflow_dict
from specy_road.worktree_env import EnvSetupError, setup_worktree_env

IGNORED = ".python-version\n.env\n.env.example\nenv-built\n"
SETUP = ("env_setup:\n  cmd: echo built > env-built\n"
         "  copy:\n    - .python-version\n    - {from: .env.example, to: .env}\n")


def _ignored_files(root: Path) -> None:
    """The main checkout's own ignored files, which git never brings to a worktree."""
    exclude = Path(git(root, "rev-parse", "--git-common-dir"))
    exclude = (exclude if exclude.is_absolute() else root / exclude) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(IGNORED, encoding="utf-8")
    (root / ".python-version").write_text("3.12\n", encoding="utf-8")
    (root / ".env.example").write_text("TOKEN=\n", encoding="utf-8")


def _cfg(env_setup) -> str | None:
    return validate_git_workflow_dict({"version": 1, "integration_branch": "main", "remote": "origin",
                                       "env_setup": env_setup})


def test_schema_takes_a_command_and_copies() -> None:
    assert _cfg({"cmd": "uv sync --all-packages --all-groups --locked"}) is None
    assert _cfg({"copy": [".python-version", {"from": ".env.example", "to": ".env"}, "../.python-version"]}) is None
    for bad in ({}, {"cmd": ""}, {"run": "x"}, {"copy": ["/etc/passwd"]}, {"copy": [{"from": "a"}]}, "uv sync"):
        assert _cfg(bad) is not None, bad


# --- copy paths stay inside the worktree and the main checkout -----------------------------------


def _nested_project(tmp_path: Path, copy: str) -> tuple[Path, Path]:
    """``(project root, leaf project root)`` in the nested layout: the project at ``<git root>/sr``, one linked worktree."""
    top = make_pickup_project(tmp_path)
    project = top / "sr"
    (project / "roadmap").mkdir(parents=True)
    (project / "roadmap" / "git-workflow.yaml").write_text(
        f"version: 1\nintegration_branch: main\nremote: origin\nenv_setup:\n  copy: [{copy}]\n", encoding="utf-8")
    (top / ".python-version").write_text("3.12\n", encoding="utf-8")
    (project / ".env").write_text("TOKEN=\n", encoding="utf-8")
    (tmp_path / "secret").write_text("outside\n", encoding="utf-8")
    lane = tmp_path / "lane"
    git(top, "worktree", "add", "-q", "-b", "lane", str(lane))
    return project, lane / "sr"


def test_a_copy_may_climb_to_the_git_root_of_a_nested_project(tmp_path: Path) -> None:
    project, leaf = _nested_project(tmp_path, "../.python-version")
    assert setup_worktree_env(project, leaf) == ["copied ../.python-version"]
    assert (leaf.parent / ".python-version").read_text(encoding="utf-8") == "3.12\n"   # the worktree's git root


def test_a_copy_target_past_the_worktree_is_refused(tmp_path: Path) -> None:
    project, leaf = _nested_project(tmp_path, "{from: .env, to: ../../.env}")
    with pytest.raises(EnvSetupError, match=r"cannot copy to '\.\./\.\./\.env': .* outside the leaf worktree .*lane"):
        setup_worktree_env(project, leaf)
    assert not (tmp_path / ".env").exists()


def test_a_copy_source_past_the_main_checkouts_git_root_is_refused(tmp_path: Path) -> None:
    project, leaf = _nested_project(tmp_path, "{from: ../../secret, to: .env}")
    with pytest.raises(EnvSetupError, match=r"cannot copy from '\.\./\.\./secret': .* outside the main checkout .*app"):
        setup_worktree_env(project, leaf)
    assert not (leaf / ".env").exists()


def test_doctor_reports_a_copy_source_outside_the_git_root(tmp_path: Path, capsys) -> None:
    project, _leaf = _nested_project(tmp_path, "../../secret")
    assert des.report_env_setup(project) is True
    assert "error: env_setup: cannot copy from '../../secret'" in capsys.readouterr().err


# --- pickup (do-next-available-task --worktree) -------------------------------------------------


def test_worktree_pickup_copies_the_ignored_files_then_runs_the_command(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path, SETUP)
    _ignored_files(root)
    r = run_pickup(root, "--worktree")
    assert r.returncode == 0, r.stderr
    wt = root / "work" / ".worktrees" / "leaf-one"
    assert (wt / ".python-version").read_text(encoding="utf-8") == "3.12\n"
    assert (wt / ".env").read_text(encoding="utf-8") == "TOKEN=\n" and not (wt / ".env.example").exists()
    assert (wt / "env-built").read_text(encoding="utf-8").strip() == "built"   # ran in the worktree's project root
    assert not (root / "env-built").exists()
    assert "env_setup: copied .env.example to .env" in r.stdout and "env_setup: ran echo built" in r.stdout


def test_worktree_pickup_stops_on_a_failing_command_with_its_output(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path, "env_setup:\n  cmd: echo no-interpreter-here; exit 3\n")
    r = run_pickup(root, "--worktree")
    assert r.returncode != 0
    assert "env_setup failed" in r.stderr and "(exit 3)" in r.stderr and "no-interpreter-here" in r.stderr
    assert "prompt-M1" not in r.stdout   # the pickup stopped before the prompt
    assert (root / "work" / ".worktrees" / "leaf-one").is_dir()   # the worktree stays, as the error says


def test_worktree_pickup_stops_when_a_copy_source_is_missing(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path, "env_setup:\n  copy: [.python-version]\n")
    r = run_pickup(root, "--worktree")
    assert r.returncode != 0
    assert "cannot copy .python-version" in r.stderr


def test_pickup_without_env_setup_sets_up_nothing(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path)
    r = run_pickup(root, "--worktree")
    assert r.returncode == 0, r.stderr
    assert "env_setup:" not in r.stdout + r.stderr


# --- worker delegate ----------------------------------------------------------------------------


def _worker_repo(tmp_path: Path, setup: str) -> Path:
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    _ignored_files(repo)
    if setup:
        cfg = repo / "roadmap" / "git-workflow.yaml"
        cfg.write_text(cfg.read_text() + setup, encoding="utf-8")
        git(repo, "commit", "-qam", "env_setup")
    return repo


def _delegate(repo: Path) -> int:
    return run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))


def test_delegate_sets_up_the_worktree_it_creates(tmp_path: Path, capsys) -> None:
    repo = _worker_repo(tmp_path, SETUP)
    assert _delegate(repo) == 0
    wt = repo / "work" / ".worktrees" / "thing"
    assert (wt / ".python-version").is_file() and (wt / ".env").is_file()
    assert (wt / "env-built").is_file()
    assert "env_setup: ran echo built" in capsys.readouterr().err
    [rec] = ws.list_records(repo)
    wait_for_worker(repo, rec.worker_id)


def test_delegate_from_a_linked_worktree_copies_from_the_main_checkout(tmp_path: Path, capsys) -> None:
    """The ignored files exist in the main checkout only; the invoking linked checkout has none of them."""
    repo = _worker_repo(tmp_path, SETUP)
    lane = tmp_path / "lane"
    git(repo, "worktree", "add", "-q", "-b", "lane", str(lane), "dev")
    assert not (lane / ".python-version").exists()
    assert _delegate(lane) == 0, capsys.readouterr().err
    wt = repo / "work" / ".worktrees" / "thing"
    assert (wt / ".python-version").read_text(encoding="utf-8") == "3.12\n"
    assert (wt / ".env").read_text(encoding="utf-8") == "TOKEN=\n"
    assert (wt / "env-built").is_file()
    [rec] = ws.list_records(lane)
    wait_for_worker(lane, rec.worker_id)


def test_delegate_stops_the_launch_on_a_failing_command_and_does_not_rerun_it(tmp_path: Path, capsys) -> None:
    repo = _worker_repo(tmp_path, "env_setup:\n  cmd: echo resolver-said-no; exit 4\n")
    assert _delegate(repo) == 1
    err = capsys.readouterr().err
    assert "(exit 4)" in err and "resolver-said-no" in err
    assert not ws.list_records(repo) and not (repo / "work" / "prompt-M1.1-executor-opus.md").exists()
    # The worktree exists now, so the next delegate launches without setting it up again.
    assert _delegate(repo) == 0
    assert "env_setup:" not in capsys.readouterr().err
    [rec] = ws.list_records(repo)
    wait_for_worker(repo, rec.worker_id)


def test_delegate_without_env_setup_sets_up_nothing(tmp_path: Path, capsys) -> None:
    repo = _worker_repo(tmp_path, "")
    assert _delegate(repo) == 0
    assert "env_setup:" not in capsys.readouterr().err
    assert not (repo / "work" / ".worktrees" / "thing" / ".python-version").exists()
    [rec] = ws.list_records(repo)
    wait_for_worker(repo, rec.worker_id)


# --- doctor -------------------------------------------------------------------------------------


def test_doctor_reports_a_command_that_succeeds_in_the_main_checkout(tmp_path: Path, capsys) -> None:
    root = make_pickup_project(tmp_path, SETUP)
    _ignored_files(root)
    assert des.report_checkout(root) is False
    out = capsys.readouterr().out
    assert "env_setup: copy .python-version, .env.example -> .env; cmd echo built > env-built" in out
    assert f"env_setup: succeeds in the main checkout {root}" in out


def test_doctor_reports_a_failing_command_and_a_missing_copy_source(tmp_path: Path, capsys) -> None:
    root = make_pickup_project(tmp_path, "env_setup:\n  cmd: echo locked-out; exit 2\n  copy: [.python-version]\n")
    assert des.report_checkout(root) is True
    err = capsys.readouterr().err
    assert "env_setup copies .python-version, which is not a file in the main checkout" in err
    assert "env_setup fails in the main checkout" in err and "(exit 2)" in err and "locked-out" in err


def test_doctor_exits_non_zero_after_the_listing_when_env_setup_fails(tmp_path: Path) -> None:
    root = make_pickup_project(tmp_path, "env_setup:\n  cmd: exit 5\n")
    r = run_specy_road(root, "doctor")
    assert r.returncode == 1
    assert "env_setup fails in the main checkout" in r.stderr and "Nothing to tidy" in r.stdout


def test_doctor_without_env_setup_runs_nothing(tmp_path: Path, capsys) -> None:
    root = make_pickup_project(tmp_path)
    assert des.report_checkout(root) is False
    captured = capsys.readouterr()
    assert "env_setup:" not in captured.out + captured.err


def _venv(tree: Path, version: str, key: str = "version_info") -> None:
    (tree / ".venv").mkdir(parents=True)
    (tree / ".venv" / "pyvenv.cfg").write_text(f"home = /usr/bin\n{key} = {version}\n", encoding="utf-8")


@pytest.mark.parametrize(("version", "warned"), [("3.11.9", True), ("3.12.7", False)])
def test_doctor_warns_when_a_worktree_environment_runs_another_python(tmp_path: Path, capsys,
                                                                       version: str, warned: bool) -> None:
    root = make_pickup_project(tmp_path)
    _venv(root, "3.12.4", key="version")   # venv's spelling; uv writes version_info
    wt = tmp_path / "lane"
    git(root, "worktree", "add", "-q", "-b", "lane", str(wt))
    _venv(wt, version)
    des.report_checkout(root)
    err = capsys.readouterr().err
    assert (f"worktree {wt} has a Python {version} environment; the main checkout's is 3.12.4" in err) is warned


def test_env_python_reads_the_project_root_before_the_git_root(tmp_path: Path) -> None:
    _venv(tmp_path / "sr", "3.13.1")
    _venv(tmp_path, "3.12.4")
    assert des.env_python(tmp_path / "sr", tmp_path) == "3.13.1"
    assert des.env_python(tmp_path / "other", tmp_path) == "3.12.4"
    assert des.env_python(tmp_path / "x", tmp_path / "x") is None
