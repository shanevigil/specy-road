"""M15.21: in a linked worktree, ``SPECY_ROAD_REPO_ROOT`` resolves the enclosing worktree, and ``env_setup.link``
symlinks the main checkout's environments into a new worktree without leaving it dirty."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road import worktree_env
from specy_road.worktree_env import EnvSetupError, info_exclude_lines, info_exclude_records, link_into, linked_status_paths, setup_worktree_env

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
    names = ["env[1]", "a*b?", "!bang", "#hash", "c]d", "e\\\\f"]
    _set_link(root, "[" + ", ".join(f"'{n}'" for n in names) + "]")
    for name in names:
        (root / name).mkdir()
    assert setup_worktree_env(root, lane) == [f"linked {n}" for n in names]
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""
    (lane / "env1").write_text("x", encoding="utf-8")   # what the unescaped /env[1] would have matched
    (lane / "aXbY").write_text("x", encoding="utf-8")
    assert git(lane, "status", "--porcelain", "--untracked-files=all").splitlines() == ["?? aXbY", "?? env1"]


@pytest.mark.parametrize("entry", ["node_modules/..", "../escape"])
def test_link_refuses_dot_dot_out_of_place(tmp_path: Path, entry: str) -> None:
    root, lane = _linked_project(tmp_path)
    _set_link(root, f"['{entry}']")
    before = git(lane, "status", "--porcelain", "--untracked-files=all")
    with pytest.raises(EnvSetupError, match="cannot link"):
        setup_worktree_env(root, lane)
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == before


def test_an_absolute_link_path_is_refused_by_the_schema_and_by_the_link_guard(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    absolute = str(tmp_path / "elsewhere" / "node_modules")
    _set_link(root, f"['{absolute}']")
    assert "does not match '^(?!/)'" in load_git_workflow_config(root)[1]
    assert setup_worktree_env(root, lane) == []   # an invalid config sets nothing up
    with pytest.raises(EnvSetupError, match="cannot link"):   # and the guard holds without the schema
        link_into({"link": [str(root / "node_modules")]}, root, lane, "")
    assert not (tmp_path / "elsewhere").exists() and not (lane / "node_modules").exists()


def test_a_source_that_is_a_symlink_links_its_resolved_target(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    (root / "store").mkdir()
    (root / "node_modules" / "marker").rename(root / "store" / "marker")
    (root / "node_modules").rmdir()
    (root / "node_modules").symlink_to(root / "store", target_is_directory=True)
    _set_link(root, "[node_modules]")
    assert setup_worktree_env(root, lane) == ["linked node_modules"]
    assert (lane / "node_modules").resolve() == (root / "store").resolve()
    assert linked_status_paths(root, lane) == {"node_modules"}
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "node_modules").unlink()
    (root / "node_modules").symlink_to(outside, target_is_directory=True)   # a source past the git root
    (lane / "node_modules").unlink()
    with pytest.raises(EnvSetupError, match="outside the main checkout"):
        setup_worktree_env(root, lane)
    assert not (lane / "node_modules").exists()


def test_link_in_a_nested_project_excludes_git_root_relative_lines(tmp_path: Path) -> None:
    top = make_pickup_project(tmp_path)
    project = top / "sr"
    (project / "roadmap").mkdir(parents=True)
    (project / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\nenv_setup:\n  link: [node_modules, ../.venv]\n",
        encoding="utf-8")
    (project / "node_modules").mkdir()
    (top / ".venv").mkdir()
    (top / ".gitignore").write_text("sr/\n.venv/\n", encoding="utf-8")
    git(top, "add", ".gitignore")
    git(top, "commit", "-qm", "ignore")
    lane = tmp_path / "lane"
    git(top, "worktree", "add", "-q", "-b", "lane", str(lane))
    assert setup_worktree_env(project, lane / "sr") == ["linked node_modules", "linked ../.venv"]
    exclude = Path(git(lane, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    assert exclude.read_text(encoding="utf-8").splitlines()[-2:] == ["/sr/node_modules", "/.venv"]
    assert linked_status_paths(project, lane / "sr") == {"sr/node_modules", ".venv"}


def test_a_checkout_path_with_a_newline_resolves_the_enclosing_worktree(tmp_path: Path, monkeypatch, capsys) -> None:
    main = tmp_path / "main\ncheckout"
    (main / "roadmap").mkdir(parents=True)
    (main / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: main\nremote: origin\nenv_setup:\n  link: [node_modules]\n", encoding="utf-8")
    (main / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    git(main, "init", "-q", "-b", "main")
    git(main, "-c", "user.email=t@e.com", "-c", "user.name=T", "add", "-A")
    git(main, "-c", "user.email=t@e.com", "-c", "user.name=T", "commit", "-qm", "init")
    (main / "node_modules").mkdir()
    lane = tmp_path / "lane"
    git(main, "worktree", "add", "-q", "-b", "lane", str(lane))
    monkeypatch.setenv(REPO_ROOT_ENV, str(main))
    monkeypatch.chdir(lane)
    capsys.readouterr()
    assert project_root() == lane.resolve()
    assert capsys.readouterr() == ("", "")
    assert setup_worktree_env(main, lane) == ["linked node_modules"]   # the exclude file sits under main\ncheckout
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""


def test_a_second_setup_does_not_corrupt_exclude_lines_with_vertical_tab(tmp_path: Path) -> None:
    main = tmp_path / "main"
    (main / "roadmap").mkdir(parents=True)
    odd = "env\vodd"
    (main / "roadmap" / "git-workflow.yaml").write_text(
        yaml.safe_dump({"version": 1, "integration_branch": "main", "remote": "origin",
                        "env_setup": {"link": [odd]}}), encoding="utf-8")
    git(main, "init", "-q", "-b", "main")
    git(main, "-c", "user.email=t@e.com", "-c", "user.name=T", "add", "-A")
    git(main, "-c", "user.email=t@e.com", "-c", "user.name=T", "commit", "-qm", "init")
    (main / odd).mkdir()
    lane = tmp_path / "lane"
    git(main, "worktree", "add", "-q", "-b", "lane", str(lane))
    assert setup_worktree_env(main, lane) == [f"linked {odd}"]
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""
    (main / "second").mkdir()
    (main / "roadmap" / "git-workflow.yaml").write_text(
        yaml.safe_dump({"version": 1, "integration_branch": "main", "remote": "origin",
                        "env_setup": {"link": ["second"]}}), encoding="utf-8")
    lane2 = tmp_path / "lane2"
    git(main, "worktree", "add", "-q", "-b", "lane2", str(lane2))
    assert setup_worktree_env(main, lane2) == ["linked second"]
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""


def test_exclude_append_starts_a_new_line_when_the_file_has_no_trailing_lf(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    exclude = Path(git(lane, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    existing = exclude.read_text(encoding="utf-8")
    exclude.write_text(existing.removesuffix("\n"), encoding="utf-8")
    assert setup_worktree_env(root, lane) == ["linked node_modules", "linked .venv"]
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""
    assert info_exclude_lines(exclude.read_text(encoding="utf-8"))[-2:] == ["/node_modules", "/.venv"]


def test_setup_with_non_utf8_bytes_in_info_exclude(tmp_path: Path) -> None:
    root, lane = _linked_project(tmp_path)
    exclude = Path(git(lane, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    prefix = exclude.read_bytes()
    legacy = b"# legacy\xff\n"
    exclude.write_bytes(prefix + legacy)
    assert setup_worktree_env(root, lane) == ["linked node_modules", "linked .venv"]
    assert git(lane, "status", "--porcelain", "--untracked-files=all") == ""
    body = exclude.read_bytes()
    assert body.startswith(prefix + legacy)
    assert info_exclude_records(body)[-2:] == [b"/node_modules", b"/.venv"]


def test_setup_leaves_no_symlink_when_exclude_append_fails(tmp_path: Path, monkeypatch) -> None:
    root, lane = _linked_project(tmp_path)

    def boom(*_args, **_kwargs) -> None:
        raise EnvSetupError("exclude write failed")

    monkeypatch.setattr(worktree_env, "exclude_links", boom)
    with pytest.raises(EnvSetupError, match="exclude write failed"):
        setup_worktree_env(root, lane)
    assert not (lane / "node_modules").exists()
    assert not (lane / ".venv").exists()
