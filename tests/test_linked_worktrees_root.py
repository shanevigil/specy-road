"""M15.21: in a linked worktree, ``SPECY_ROAD_REPO_ROOT`` resolves the enclosing worktree, and ``env_setup.link``
symlinks the main checkout's environments into a new worktree without leaving it dirty."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.pickup_repo_helpers import make_pickup_project
from tests.review_repo_helpers import git, make_review_repo
from tests.test_worker_cli import run_worker_cli
from tests.worker_repo_helpers import make_worker_repo

from specy_road import worker_ops_launch
from specy_road.bundled_scripts import doctor_env_setup as des
from specy_road.bundled_scripts import review_cli
from specy_road.review_files import load_ready, reviews_dir
from specy_road.runtime_paths import REPO_ROOT_ENV, project_root
from specy_road.worker_state import active_for_node
from specy_road.worktree_env import EnvSetupError, setup_worktree_env

# --- A1: the enclosing worktree wins ------------------------------------------------------------


def _main_and_lane(tmp_path: Path) -> tuple[Path, Path]:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    return repo, wt


def test_ready_in_a_linked_worktree_with_the_variable_naming_the_main_checkout(tmp_path: Path, monkeypatch,
                                                                                capsys) -> None:
    repo, wt = _main_and_lane(tmp_path)
    monkeypatch.setenv(REPO_ROOT_ENV, str(repo))
    monkeypatch.chdir(wt)
    with pytest.raises(SystemExit) as e:
        review_cli.main(["ready", "M1.1", "--model", "opus", "--verify", "pytest=0"])
    assert e.value.code == 0, capsys.readouterr().err
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["commit"] == git(wt, "rev-parse", "HEAD")


def test_the_enclosing_worktree_is_resolved_silently(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, wt = _main_and_lane(tmp_path)
    (repo / "sub").mkdir()
    (wt / "sub").mkdir()
    monkeypatch.setenv(REPO_ROOT_ENV, str(repo / "sub"))
    monkeypatch.chdir(wt / "sub")
    capsys.readouterr()
    assert project_root() == (wt / "sub").resolve()   # the same project-relative path, in this worktree
    assert capsys.readouterr() == ("", "")
    monkeypatch.chdir(repo)
    assert project_root() == (repo / "sub").resolve()   # the main checkout itself: unchanged


def test_a_project_missing_from_the_enclosing_worktree_is_not_redirected_to_the_main_checkout(
        tmp_path: Path, monkeypatch) -> None:
    repo, wt = _main_and_lane(tmp_path)
    (repo / "missing-project" / "roadmap").mkdir(parents=True)
    monkeypatch.setenv(REPO_ROOT_ENV, str(repo / "missing-project"))
    monkeypatch.chdir(wt)
    assert project_root() == wt.resolve() / "missing-project"


def test_a_working_directory_in_another_repository_keeps_the_variable(tmp_path: Path, monkeypatch) -> None:
    repo, _wt = _main_and_lane(tmp_path)
    other = make_review_repo(tmp_path / "other")
    monkeypatch.setenv(REPO_ROOT_ENV, str(repo))
    monkeypatch.chdir(other)
    assert project_root() == repo.resolve()
    monkeypatch.chdir(tmp_path)   # outside git
    assert project_root() == repo.resolve()


def _capture_spawn(monkeypatch) -> list:
    launches: list = []
    monkeypatch.setattr(worker_ops_launch, "spawn", lambda _root, _rec, launch: launches.append(launch) or 1)
    monkeypatch.setattr(worker_ops_launch, "acquire_lease", lambda *a, **k: None)
    return launches


def test_delegate_sets_the_variable_to_the_workers_worktree(tmp_path: Path, monkeypatch) -> None:
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    monkeypatch.setenv(REPO_ROOT_ENV, str(repo))   # exported for the coordinator
    launches = _capture_spawn(monkeypatch)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 0
    launch = launches[-1]   # the launch delegate handed to spawn
    assert launch.env[REPO_ROOT_ENV] == str((repo / "work" / ".worktrees" / "thing").resolve())


# --- A2: env_setup.link -------------------------------------------------------------------------

LINK = "env_setup:\n  link: [node_modules, .venv]\n"


def _linked_project(tmp_path: Path) -> tuple[Path, Path]:
    """A main checkout whose ``.gitignore`` names the environments directory-only, and one new linked worktree."""
    root = make_pickup_project(tmp_path, LINK)
    (root / ".gitignore").write_text("node_modules/\n.venv/\n", encoding="utf-8")
    git(root, "add", ".gitignore")
    git(root, "commit", "-qm", "ignore environments")
    for name in ("node_modules", ".venv"):
        (root / name).mkdir()
        (root / name / "marker").write_text(name, encoding="utf-8")
    lane = tmp_path / "lane"
    git(root, "worktree", "add", "-q", "-b", "lane", str(lane))
    return root, lane


def test_link_symlinks_the_environments_and_leaves_the_worktree_clean(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    assert setup_worktree_env(root, lane) == ["linked node_modules", "linked .venv"]
    for name in ("node_modules", ".venv"):
        assert (lane / name).is_symlink() and (lane / name / "marker").read_text(encoding="utf-8") == name
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""
    assert git(root, "status", "--porcelain", "--untracked-files=all") == ""
    exclude = Path(git(lane, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    assert exclude.read_text(encoding="utf-8").splitlines()[-2:] == ["/node_modules", "/.venv"]


def test_link_refuses_a_missing_source_and_a_path_past_the_git_root(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    (root / ".venv" / "marker").unlink()
    (root / ".venv").rmdir()
    with pytest.raises(EnvSetupError, match=r"cannot link \.venv: .* does not exist"):
        setup_worktree_env(root, lane)
    cfg = root / "roadmap" / "git-workflow.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace(LINK, "env_setup:\n  link: [../escape]\n"),
                   encoding="utf-8")
    with pytest.raises(EnvSetupError, match=r"cannot link from '\.\./escape': .* outside the main checkout"):
        setup_worktree_env(root, lane)


def test_doctor_lists_the_links_and_a_missing_source(tmp_path: Path, capsys) -> None:
    root, _lane = _linked_project(tmp_path)
    (root / ".venv" / "marker").unlink()
    (root / ".venv").rmdir()
    assert des.report_env_setup(root) is True
    captured = capsys.readouterr()
    assert "env_setup: copy nothing; link node_modules, .venv; cmd none" in captured.out
    assert "env_setup links .venv, which does not exist in the main checkout" in captured.err


def test_delegate_ignores_a_declared_link_made_by_hand(tmp_path: Path, monkeypatch) -> None:
    """A worktree that already exists is not set up again, so its hand-made symlink has no exclude line."""
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    cfg = repo / "roadmap" / "git-workflow.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "env_setup:\n  link: [node_modules]\n", encoding="utf-8")
    (repo / ".gitignore").write_text("work/\nnode_modules/\n", encoding="utf-8")
    git(repo, "commit", "-qam", "link")
    (repo / "node_modules").mkdir()
    wt = repo / "work" / ".worktrees" / "thing"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    (wt / "node_modules").symlink_to(repo / "node_modules", target_is_directory=True)
    assert git(wt, "status", "--porcelain") == "?? node_modules"   # the directory-only pattern misses it
    _capture_spawn(monkeypatch)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) == 0
    assert active_for_node(repo, "M1.1") is not None


def test_delegate_refuses_an_ordinary_file_with_a_declared_link_name(tmp_path: Path, monkeypatch) -> None:
    """Only a symlink to the main checkout's path is exempt: user data under that name is still work."""
    repo, _script = make_worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    cfg = repo / "roadmap" / "git-workflow.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "env_setup:\n  link: [node_modules]\n", encoding="utf-8")
    (repo / ".gitignore").write_text("work/\nnode_modules/\n", encoding="utf-8")
    git(repo, "commit", "-qam", "link")
    (repo / "node_modules").mkdir()
    wt = repo / "work" / ".worktrees" / "thing"
    git(repo, "worktree", "add", "-q", str(wt), "feature/rm-thing")
    (wt / "node_modules").write_text("uncommitted user data\n", encoding="utf-8")
    _capture_spawn(monkeypatch)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)) != 0
    assert active_for_node(repo, "M1.1") is None
    assert (wt / "node_modules").read_text(encoding="utf-8") == "uncommitted user data\n"


def _set_link(root: Path, names: str) -> None:
    cfg = root / "roadmap" / "git-workflow.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace(LINK, f"env_setup:\n  link: {names}\n"), encoding="utf-8")


def test_link_refuses_a_parent_that_is_a_symlink_out_of_the_worktree(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    _set_link(root, "[assets/env]")
    (root / "assets" / "env").mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (lane / "assets").symlink_to(external, target_is_directory=True)
    with pytest.raises(EnvSetupError, match=r"cannot link to 'assets/env': .* not a path inside the leaf worktree"):
        setup_worktree_env(root, lane)
    assert list(external.iterdir()) == []


def test_link_excludes_a_name_with_pattern_characters_literally(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    _set_link(root, '["env[1]", "a*b?"]')
    (root / "env[1]").mkdir()
    (root / "a*b?").mkdir()
    assert setup_worktree_env(root, lane) == ["linked env[1]", "linked a*b?"]
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""
    (lane / "env1").write_text("x", encoding="utf-8")   # what the unescaped /env[1] would have matched
    (lane / "aXbY").write_text("x", encoding="utf-8")
    assert git(lane, "status", "--porcelain", "--untracked-files=all").splitlines() == ["?? aXbY", "?? env1"]
