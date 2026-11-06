"""M13.2: `specy-road upgrade` says what is upgrading, validates in a dry run, and owns its line-cap overruns.

rc3 adopters ran a dry run under the old install without being told so, saw a
breaking validate error only after every refresh was written, and found a
project file pushed over its cap with no word from upgrade.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specy_road import __version__, git_subprocess
from specy_road.bundled_scripts import upgrade
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.file_limits_engine import collect_tracked_files, run_file_limits_scan
from specy_road.git_subprocess import GitResult
from specy_road.init_project import run_init_project
from tests.upgrade_repo_helpers import old_repo

GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *GIT_ID, *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def test_header_names_the_install_and_a_dry_run_says_it_previews(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
    capsys.readouterr()

    run_upgrade(root, dry_run=True)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(f"previewing what specy-road {__version__} would write")
    assert lines[1] == f"Install: specy-road {__version__} running from {sys.prefix}"

    run_upgrade(root)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"specy-road {__version__} upgrade: {root.resolve()}"
    assert lines[1] == f"Install: specy-road {__version__} running from {sys.prefix}"


def test_dry_run_exits_with_a_validate_error_only_the_refreshed_copy_raises(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The injected error needs a file only the refresh writes, so it fires on the copy and never on the checkout."""
    root = old_repo(tmp_path)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "old scaffold")
    files, status = _snapshot(root), _git(root, "status", "--porcelain")
    validated: list[Path] = []

    def new_version_validate(at: Path) -> None:
        validated.append(at)
        if (at / "schemas" / "orchestration.schema.json").is_file():
            print("error: the new version rejects this roadmap", file=sys.stderr)
            raise SystemExit(1)

    monkeypatch.setattr(upgrade, "validate_at", new_version_validate)

    assert run_upgrade(root, dry_run=True) == 1

    out, err = capsys.readouterr()
    assert "== validate" in out and "error: the new version rejects this roadmap" in err
    assert validated and all(at.name and not at.exists() and not at.is_relative_to(root.resolve())
                             for at in validated)
    assert _snapshot(root) == files
    assert _git(root, "status", "--porcelain") == status


def _capped_agents_md(root: Path, agents_lines: int, cap: int) -> None:
    (root / "AGENTS.md").write_text("".join(f"line {i}\n" for i in range(agents_lines)), encoding="utf-8")
    (root / "constraints" / "file-limits.yaml").write_text(yaml.safe_dump({
        "max_lines_per_file": cap, "applies_to_globs": ["AGENTS.md"],
    }), encoding="utf-8")


def test_a_file_the_upgrade_pushes_over_its_cap_is_named(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
    _capped_agents_md(root, 3, 10)

    run_upgrade(root, dry_run=True)
    assert "AGENTS.md: this upgrade pushed it over its cap: 3 ->" in capsys.readouterr().out
    assert (root / "AGENTS.md").read_text(encoding="utf-8").count("\n") == 3

    run_upgrade(root)
    new = (root / "AGENTS.md").read_text(encoding="utf-8").count("\n")
    out = capsys.readouterr().out
    assert f"AGENTS.md: this upgrade pushed it over its cap: 3 -> {new} lines (cap 10)" in out


def test_a_file_already_over_its_cap_is_not_blamed_on_the_upgrade(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
    _capped_agents_md(root, 30, 10)

    run_upgrade(root)
    new = (root / "AGENTS.md").read_text(encoding="utf-8").count("\n")
    out = capsys.readouterr().out
    assert out.count("AGENTS.md: already over its cap") == 1
    assert f"AGENTS.md: already over its cap before this upgrade (30 -> {new} lines, cap 10)" in out
    assert "pushed it over" not in out


def test_a_fresh_project_does_not_cap_the_root_agent_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    run_init_project(tmp_path)
    for name in ("AGENTS.md", "CLAUDE.md"):
        (tmp_path / name).write_text("x\n" * 1000, encoding="utf-8")
    text = (tmp_path / "constraints" / "file-limits.yaml").read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)

    capped = {p.relative_to(tmp_path).as_posix() for p in collect_tracked_files(tmp_path, cfg)}
    assert "AGENTS.md" not in capped and "CLAUDE.md" not in capped
    assert "planning/README.md" in capped
    assert not run_file_limits_scan(tmp_path, cfg)
    assert "# To cap them too, delete them from this list" in text


def test_other_worktrees_are_named_as_not_upgraded(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path / "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "old scaffold")
    other = (tmp_path / "other worktree").resolve()
    _git(root, "worktree", "add", "-q", "-b", "feature/x", str(other))

    run_upgrade(root)

    out = capsys.readouterr().out
    assert "\n== other worktrees\n" in out
    quoted = shlex.quote(str(other))
    assert (f"{other} (feature/x): not upgraded; it still has the old managed files while sharing this install."
            f" Run there: cd {quoted} && specy-road upgrade") in out.splitlines()
    assert str(root.resolve()) + " (" not in out
    command = out.split(" Run there: ", 1)[1].splitlines()[0]
    cd_part = command.removesuffix(" && specy-road upgrade")
    ran = subprocess.run(["bash", "-c", f"{cd_part} && pwd -P"], capture_output=True, text=True, cwd=tmp_path)
    assert ran.returncode == 0 and ran.stdout.strip() == str(other)


def test_dry_run_never_writes_through_a_link_into_the_checkout(tmp_path: Path, capsys) -> None:
    """Sol F1: a schema linked through an external alias of the same checkout stayed a link in the copy,
    and the copy's refresh overwrote the checkout's tracked file."""
    root = old_repo(tmp_path / "repo")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    (root / "schema-storage").mkdir()
    (root / "schema-storage" / "roadmap.schema.json").write_text('{"old": "schema"}\n', encoding="utf-8")
    link = root / "schemas" / "roadmap.schema.json"
    link.unlink()
    link.symlink_to(alias / "schema-storage" / "roadmap.schema.json")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "linked schema")
    files, status = _snapshot(root), _git(root, "status", "--porcelain=v1", "--ignored")

    assert run_upgrade(root, dry_run=True) in (0, 1)

    assert "dry run modified" not in capsys.readouterr().err
    assert _snapshot(root) == files
    assert _git(root, "status", "--porcelain=v1", "--ignored") == status
    assert link.is_symlink()


def test_dry_run_validates_an_ignored_claude_md_with_its_text_and_the_refreshed_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sol F2: git ignores CLAUDE.md, but the real refresh writes its block, so the copy must carry it."""
    root = old_repo(tmp_path)
    (root / "CLAUDE.md").write_text("# Claude\n\nOur own Claude notes.\n", encoding="utf-8")
    with (root / ".gitignore").open("a", encoding="utf-8") as f:
        f.write("CLAUDE.md\n")
    seen: list[str] = []
    monkeypatch.setattr(upgrade, "validate_at", lambda at: seen.append((at / "CLAUDE.md").read_text(encoding="utf-8")))

    assert run_upgrade(root, dry_run=True) == 0

    assert seen and all("Our own Claude notes." in text and "@.specyrd/AGENTS.md" in text.splitlines()
                        for text in seen)
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "# Claude\n\nOur own Claude notes.\n"


def test_a_dry_run_that_touches_the_checkout_fails_as_a_bug(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hard guard: whatever writes into the checkout during the preview, the dry run says so and fails."""
    root = old_repo(tmp_path)
    monkeypatch.setattr(upgrade, "validate_at",
                        lambda at: (root / "vision.md").write_text("changed\n", encoding="utf-8"))

    assert run_upgrade(root, dry_run=True) == 2

    err = capsys.readouterr().err
    assert "error: dry run modified" in err and "vision.md" in err and "this is a bug" in err


def _repo_state(repo: Path) -> tuple:
    """HEAD, commit count, object count, index bytes and working files of ``repo``."""
    objects = dict(line.split(": ") for line in _git(repo, "count-objects", "-v").splitlines())
    return (_git(repo, "rev-parse", "HEAD"), _git(repo, "rev-list", "--count", "HEAD"),
            int(objects["count"]) + int(objects["in-pack"]), (repo / ".git" / "index").read_bytes(),
            _git(repo, "diff", "--cached", "--name-only"), _snapshot(repo))


@pytest.mark.parametrize("env", [
    {"GIT_DIR": ".git", "GIT_WORK_TREE": "."},
    {"GIT_INDEX_FILE": ".git/index"},
    {"GIT_COMMON_DIR": ".git"},
    {"GIT_OBJECT_DIRECTORY": ".git/objects"},
], ids=lambda env: "+".join(env))
def test_dry_run_never_touches_the_repository_a_git_variable_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    """rc4 F1: inside a git hook the scratch copy's git add/commit landed in the caller's repository."""
    root = old_repo(tmp_path / "project")
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    (other / "theirs.txt").write_text("their file\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-qm", "their commit")
    before = _repo_state(other)

    with monkeypatch.context() as m:
        for name, rel in env.items():
            m.setenv(name, str(other / rel))
        assert run_upgrade(root, dry_run=True) == 0

    assert _repo_state(other) == before


def test_a_dry_run_whose_copy_has_no_git_validates_nothing(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M21.16 A1: with no scratch .git, git add/commit would find whatever repository is above the copy."""
    root = old_repo(tmp_path)
    build = upgrade.Mirror.build

    def build_without_git(self):
        copy = build(self)
        shutil.rmtree(copy.repo / ".git")
        return copy

    monkeypatch.setattr(upgrade.Mirror, "build", build_without_git)
    validated: list[Path] = []
    monkeypatch.setattr(upgrade, "validate_at", validated.append)

    assert run_upgrade(root, dry_run=True) == 2

    assert not validated and "git init failed in the temporary copy" in capsys.readouterr().err


def _committed(root: Path) -> Path:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "scaffold")
    return root


def _checkout_state(root: Path) -> tuple:
    return (*_repo_state(root), _git(root, "for-each-ref"))


def _marker_config(tmp_path: Path, marker: Path) -> dict[str, dict[str, str]]:
    """Each way a git config runs a command on the scratch ``git add``, ``status`` or ``commit``."""
    attributes = tmp_path / "attributes"
    attributes.write_text("* filter=evil\n", encoding="utf-8")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "post-commit").write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    (hooks / "post-commit").chmod(0o755)
    return {
        "fsmonitor": {"core.fsmonitor": f"touch {marker}"},
        "filter": {"filter.evil.clean": f"touch {marker}; cat", "core.attributesFile": str(attributes)},
        "hooks": {"core.hooksPath": str(hooks)},
    }


@pytest.mark.parametrize("injected", ["fsmonitor", "filter", "hooks"])
def test_git_config_count_runs_no_command_in_a_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, injected: str
) -> None:
    """rc4 final F1: five variables stripped left GIT_CONFIG_COUNT, and the scratch git ran what it named."""
    root = _committed(old_repo(tmp_path / "project"))
    marker = tmp_path / "marker"
    config = _marker_config(tmp_path, marker)[injected]
    before = _checkout_state(root)

    with monkeypatch.context() as m:
        m.setenv("GIT_CONFIG_COUNT", str(len(config)))
        for n, (key, value) in enumerate(config.items()):
            m.setenv(f"GIT_CONFIG_KEY_{n}", key)
            m.setenv(f"GIT_CONFIG_VALUE_{n}", value)
        assert run_upgrade(root, dry_run=True) == 0

    assert not marker.exists()
    assert _checkout_state(root) == before


@pytest.mark.parametrize("config_file", [".gitconfig", "xdg/git/config"])
def test_the_callers_global_git_config_never_reaches_the_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_file: str
) -> None:
    """Dropping GIT_CONFIG_GLOBAL alone only sends git to the default files, validate's git calls included.

    A .gitignore the refresh rewrites also sends the plan's ignore note to git, in the plan's mirror.
    """
    root = old_repo(tmp_path / "project")
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    _committed(root)
    marker = tmp_path / "marker"
    config = _marker_config(tmp_path, marker)
    home = tmp_path / "home"
    (home / config_file).parent.mkdir(parents=True, exist_ok=True)
    (home / config_file).write_text(
        "[specy]\n\tprobe = reached\n"
        f"[core]\n\tfsmonitor = {config['fsmonitor']['core.fsmonitor']}\n"
        f"\tattributesFile = {config['filter']['core.attributesFile']}\n"
        f"[filter \"evil\"]\n\tclean = \"{config['filter']['filter.evil.clean']}\"\n", encoding="utf-8")
    before = _checkout_state(root)
    validate, probes, live_envs = upgrade.validate_at, [], []
    run = git_subprocess.run

    def spied_validate(at: Path) -> None:
        probes.append(git_subprocess.git_text(["config", "--get", "specy.probe"], at))
        validate(at)

    def spied_run(args: list[str], cwd: Path, **kw: object) -> GitResult:
        if "--error-unmatch" in args:
            live_envs.append(kw["env"])
        return run(args, cwd, **kw)

    with monkeypatch.context() as m:
        m.setenv("HOME", str(home))
        m.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
        m.setattr(upgrade, "validate_at", spied_validate)
        m.setattr(git_subprocess, "run", spied_run)
        assert run_upgrade(root, dry_run=True) == 0

    assert not marker.exists()
    assert _checkout_state(root) == before
    assert probes == [None]
    # The checkout's own ls-files keeps the caller's config: their HOME, and no isolation.
    assert [env["HOME"] for env in live_envs] == [str(home)]
    assert not [k for k in live_envs[0] if k.startswith("GIT_")]


def test_the_scratch_repository_has_no_template_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = old_repo(tmp_path)
    git_dirs: list[list[str]] = []
    monkeypatch.setattr(upgrade, "validate_at", lambda at: git_dirs.append([p.name for p in (at / ".git").iterdir()]))

    assert run_upgrade(root, dry_run=True) == 0

    assert git_dirs and "HEAD" in git_dirs[0] and "hooks" not in git_dirs[0]


@pytest.mark.parametrize("dry_run, verb", [(True, "would write"), (False, "wrote")])
def test_git_ceiling_directories_does_not_hide_a_tracked_roadmap_md(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, dry_run: bool, verb: str
) -> None:
    """A ceiling at the checkout hides .git only from a subdirectory: the nested project, where ls-files runs."""
    root = tmp_path.resolve()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert run_init_project(root / "sr") == 0
    (root / "sr" / "roadmap.md").write_text("drifted\n", encoding="utf-8")
    _committed(root)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(root))

    assert run_upgrade(root / "sr", dry_run=dry_run) == 0

    assert f"{verb} roadmap.md (specy-road export)" in capsys.readouterr().out


FAILURES = {
    "exit-128": (GitResult(128, "", "fatal: no such thing\n"), "fatal: no such thing"),
    "exit-1-silent": (GitResult(1, "", ""), "exit 1"),
    "timeout": (GitResult(-1, "", "Command timed out after 60 seconds", "timeout"), "timed out"),
}


def _stub_git(monkeypatch: pytest.MonkeyPatch, word: str, result: GitResult) -> None:
    """``git_subprocess.run`` answers ``result`` for the git calls with ``word`` in their arguments."""
    run = git_subprocess.run
    monkeypatch.setattr(git_subprocess, "run",
                        lambda args, cwd, **kw: result if word in args else run(args, cwd, **kw))


@pytest.mark.parametrize("failure", sorted(FAILURES))
@pytest.mark.parametrize("command", ["init", "add", "commit"])
def test_a_failed_scratch_git_call_stops_the_dry_run(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, command: str, failure: str
) -> None:
    root = old_repo(tmp_path)
    result, reason = FAILURES[failure]
    _stub_git(monkeypatch, command, result)
    applied: list[object] = []
    validated: list[Path] = []
    monkeypatch.setattr(upgrade, "apply_plan", lambda *a: applied.append(a))
    monkeypatch.setattr(upgrade, "validate_at", validated.append)

    assert run_upgrade(root, dry_run=True) == 2

    assert f"error: git {command} failed in the temporary copy ({reason})" in capsys.readouterr().err
    assert not applied and not validated


@pytest.mark.parametrize("failure", ["exit-128", "timeout"])
@pytest.mark.parametrize("dry_run, where", [(True, "the temporary copy"), (False, "the checkout")])
def test_a_failed_ls_files_writes_no_generated_file(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, dry_run: bool, where: str, failure: str
) -> None:
    root = old_repo(tmp_path)
    result, reason = FAILURES[failure]
    _stub_git(monkeypatch, "--error-unmatch", result)

    assert run_upgrade(root, dry_run=dry_run) == 2

    out, err = capsys.readouterr()
    assert f"error: git ls-files failed in {where} ({reason})" in err
    assert "roadmap-context.md (specy-road digest)" not in out
    assert not (root / "roadmap-context.md").exists()


def test_ls_files_exit_1_means_untracked(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    root = old_repo(tmp_path)
    (root / "roadmap.md").write_text("drifted\n", encoding="utf-8")
    _committed(root)
    _stub_git(monkeypatch, "--error-unmatch", GitResult(1, "", "error: pathspec did not match\n"))

    assert run_upgrade(root, dry_run=True) == 0

    out = capsys.readouterr().out
    assert "would write roadmap-context.md (specy-road digest)" in out and "roadmap.md (specy-road export)" not in out
