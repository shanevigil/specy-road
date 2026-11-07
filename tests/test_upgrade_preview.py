"""M13.2: `specy-road upgrade` says what is upgrading, validates in a dry run, and owns its line-cap overruns.

rc3 adopters ran a dry run under the old install without being told so, saw a
breaking validate error only after every refresh was written, and found a
project file pushed over its cap with no word from upgrade.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

import pytest
import yaml

from specy_road import __version__, git_subprocess
from specy_road.bundled_scripts import upgrade
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.file_limits_engine import collect_tracked_files, run_file_limits_scan
from specy_road.git_subprocess import GitResult
from specy_road.init_project import run_init_project
from specy_road.digest import render_digest
from tests.test_digest_quality import land
from tests.upgrade_repo_helpers import OLD_STUB, old_repo

GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *GIT_ID, *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_tracked_file_a_new_rule_matches_is_reported_from_the_checkout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], dry_run: bool
) -> None:
    """A real run observes the checkout around the write; a dry run labels the mirror's note as an estimate."""
    from specy_road.ignore_report import ESTIMATE_HEADER, REAL_HEADER, TRACKED_NOTE

    root = old_repo(tmp_path)
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8").replace(".specyrd/AGENTS.local.md\n", ""), encoding="utf-8")
    local = root / ".specyrd" / "AGENTS.local.md"
    local.write_text("local notes\n", encoding="utf-8")
    _committed(root)
    capsys.readouterr()

    assert run_upgrade(root, dry_run=dry_run) == 0

    out = capsys.readouterr().out
    assert ".specyrd/AGENTS.local.md" in _git(root, "ls-files")
    if dry_run:
        assert ESTIMATE_HEADER in out and REAL_HEADER not in out
    else:
        assert f".specyrd/AGENTS.local.md (.specyrd/AGENTS.local.md): {TRACKED_NOTE}" in out
        assert "git rm --cached -- .specyrd/AGENTS.local.md" in out
        assert REAL_HEADER in out and ESTIMATE_HEADER not in out


def test_a_pruned_untracked_orphan_is_not_reported_as_hidden(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``--prune`` deletes the orphan before the ignore note, so a deleted file is not reported as hidden."""
    from specy_road.ignore_report import HIDDEN_NOTE, REAL_HEADER, TRACKED_NOTE

    root = old_repo(tmp_path)
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8").replace(".specyrd/AGENTS.local.md\n", ""), encoding="utf-8")
    (root / ".specyrd" / "AGENTS.local.md").write_text("local notes\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "reset", "-q", "--", OLD_STUB)
    _git(root, "commit", "-qm", "scaffold")
    assert OLD_STUB not in _git(root, "ls-files") and (root / OLD_STUB).is_file()
    capsys.readouterr()

    assert run_upgrade(root, prune=True) == 0

    out = capsys.readouterr().out
    assert f"removed {OLD_STUB}" in out and not (root / OLD_STUB).exists()
    assert not any(OLD_STUB in line and HIDDEN_NOTE in line for line in out.splitlines())
    assert f".specyrd/AGENTS.local.md (.specyrd/AGENTS.local.md): {TRACKED_NOTE}" in out
    assert "git rm --cached -- .specyrd/AGENTS.local.md" in out and REAL_HEADER in out


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


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("env", [
    {"GIT_DIR": ".git", "GIT_WORK_TREE": "."},
    {"GIT_INDEX_FILE": ".git/index"},
    {"GIT_COMMON_DIR": ".git"},
    {"GIT_OBJECT_DIRECTORY": ".git/objects"},
], ids=lambda env: "+".join(env))
def test_upgrade_never_touches_the_repository_a_git_variable_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], dry_run: bool
) -> None:
    """rc4 F1: a git variable naming a second repository must not receive the plan, in either run."""
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
        assert run_upgrade(root, dry_run=dry_run) == 0

    assert _repo_state(other) == before
    if not dry_run:
        for rel in (".gitignore", ".cursorindexingignore", ".specyrd/manifest.json"):
            assert (root / rel).is_file()


def test_a_dry_run_whose_copy_has_no_git_validates_nothing(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M21.16 A1: with no scratch .git, git add/commit would find whatever repository is above the copy."""
    root = old_repo(tmp_path)
    build = upgrade.Mirror.build

    def build_without_git(self, *args, **kwargs):
        copy = build(self, *args, **kwargs)
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


def _landed_leaf(root: Path) -> Path:
    """M1.1 landed with a tally and the digest committed current, its Quality by area read from that history."""
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    chunk = root / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text(encoding="utf-8"))
    doc["nodes"][1]["status"] = "Complete"
    chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    _committed(root)
    land(root, "project-setup", "M1.1 rounds=1 blocks=0 approvals=1 integrity=0 rca=0 findings=none")
    return root


def _shallow_clone(root: Path, tmp_path: Path) -> Path:
    clone = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth=1", root.as_uri(), str(clone)], check=True, capture_output=True)
    return clone


@pytest.mark.parametrize("history", [lambda root, tmp: root, _shallow_clone], ids=["full", "shallow"])
def test_dry_run_and_real_run_agree_on_a_current_digest(tmp_path: Path, capsys, history) -> None:
    """The dry run reads the checkout's history, so a digest with Quality by area is current in both."""
    root = history(_landed_leaf(old_repo(tmp_path / "repo")), tmp_path)
    digest = root / "roadmap-context.md"
    digest.write_text(render_digest(root), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "digest")
    assert "## Quality by area" in digest.read_text(encoding="utf-8")
    git_files = _snapshot_git(root)
    capsys.readouterr()

    assert run_upgrade(root, dry_run=True) == 0

    out = capsys.readouterr().out
    assert "would write roadmap-context.md" not in out and "generated files already current" in out
    assert "OK: roadmap-context.md matches the roadmap." in out
    assert _snapshot_git(root) == git_files

    current = digest.read_bytes()
    assert run_upgrade(root) == 0
    assert "wrote roadmap-context.md" not in capsys.readouterr().out
    assert digest.read_bytes() == current


def _snapshot_git(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in (root / ".git").rglob("*") if p.is_file()}


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


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("injected", ["fsmonitor", "filter", "hooks"])
def test_git_config_count_runs_no_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, injected: str, dry_run: bool
) -> None:
    """rc4 final F1: GIT_CONFIG_COUNT must not run the command it names, in either run.

    A real run still writes its plan. HEAD, refs and the index stay as they were.
    """
    root = _committed(old_repo(tmp_path / "project"))
    marker = tmp_path / "marker"
    config = _marker_config(tmp_path, marker)[injected]
    before = _checkout_state(root)

    with monkeypatch.context() as m:
        m.setenv("GIT_CONFIG_COUNT", str(len(config)))
        for n, (key, value) in enumerate(config.items()):
            m.setenv(f"GIT_CONFIG_KEY_{n}", key)
            m.setenv(f"GIT_CONFIG_VALUE_{n}", value)
        assert run_upgrade(root, dry_run=dry_run) == 0

    assert not marker.exists()
    after = _checkout_state(root)
    if dry_run:
        assert after == before
    else:
        assert after[:5] == before[:5] and after[6] == before[6]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("config_file", [".gitconfig", "xdg/git/config"])
def test_the_callers_global_git_config_never_reaches_the_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_file: str, dry_run: bool
) -> None:
    """The plan's mirror reads no global config, in a dry run or a real one. Validate's git calls included.

    A .gitignore the refresh rewrites also sends the plan's ignore note to git, in the plan's mirror.
    The caller's ``core.fsmonitor`` appends ``$PWD`` to a marker: absent in a dry run, and only the
    checkout's path in a real run.
    """
    root = old_repo(tmp_path / "project")
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
    _committed(root)
    marker = tmp_path / "marker"
    script = tmp_path / "fsmonitor.sh"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$PWD\" >> {marker}\n", encoding="utf-8")
    script.chmod(0o755)
    config = _marker_config(tmp_path, marker)
    home = tmp_path / "home"
    (home / config_file).parent.mkdir(parents=True, exist_ok=True)
    (home / config_file).write_text(
        "[specy]\n\tprobe = reached\n"
        f"[core]\n\tfsmonitor = {script}\n"
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
        assert run_upgrade(root, dry_run=dry_run) == 0

    lines = marker.read_text(encoding="utf-8").splitlines() if marker.exists() else []
    checkout = str(root.resolve())
    if dry_run:
        assert lines == []
        assert _checkout_state(root) == before
        assert probes == [None]
    else:
        assert lines and all(line == checkout for line in lines)
        assert probes == ["reached"]
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


def _stub_git(monkeypatch: pytest.MonkeyPatch, word: str, result: GitResult, nth: int = 1) -> None:
    """``git_subprocess.run`` answers ``result`` for the ``nth`` git call with ``word`` in its arguments, and no other."""
    run = git_subprocess.run
    seen = iter(range(1, 100))

    def stub(args: list[str], cwd: Path, **kw: object) -> GitResult:
        return result if word in args and next(seen) == nth else run(args, cwd, **kw)

    monkeypatch.setattr(git_subprocess, "run", stub)


@pytest.mark.parametrize("failure", sorted(FAILURES))
@pytest.mark.parametrize("command, nth, dry_run", [
    pytest.param("init", 1, True, id="plan-mirror-init-dry"),
    pytest.param("init", 1, False, id="plan-mirror-init-real"),
    pytest.param("init", 2, True, id="validation-mirror-init"),
    pytest.param("add", 1, True, id="add"),
    pytest.param("commit", 1, True, id="commit"),
])
def test_a_failed_scratch_git_call_stops_the_run(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, command: str, nth: int, dry_run: bool, failure: str
) -> None:
    """The plan's mirror and the dry run's copy are two inits: either failing alone stops everything."""
    root = old_repo(tmp_path)
    files = _snapshot(root)
    result, reason = FAILURES[failure]
    _stub_git(monkeypatch, command, result, nth)
    applied: list[object] = []
    validated: list[Path] = []
    monkeypatch.setattr(upgrade, "apply_plan", lambda *a: applied.append(a))
    monkeypatch.setattr(upgrade, "validate_at", validated.append)

    assert run_upgrade(root, dry_run=dry_run) == 2

    assert f"error: git {command} failed in the temporary copy ({reason})" in capsys.readouterr().err
    assert not applied and not validated
    assert _snapshot(root) == files


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


@pytest.mark.parametrize("failure", sorted(FAILURES))
@pytest.mark.parametrize("call, command, where", [
    pytest.param(["rev-parse"], "rev-parse", "the checkout", id="git-paths"),
    pytest.param(["for-each-ref"], "for-each-ref", "the checkout", id="refs"),
    pytest.param(["remote"], "remote", "the checkout", id="remotes"),
    pytest.param(["remote", "add"], "remote add", "the temporary copy", id="remote-add"),
])
def test_a_failed_history_step_stops_the_dry_run(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, call: list[str], command: str, where: str, failure: str
) -> None:
    root = _committed(old_repo(tmp_path))
    _git(root, "remote", "add", "origin", str(root))
    files = _snapshot(root)
    result, reason = FAILURES[failure]
    run = git_subprocess.run

    def stub(args: list[str], cwd: Path, **kw: object) -> GitResult:
        hit = args[:2] == call if len(call) > 1 else args[0] == call[0] and kw.get("env")
        return result if hit else run(args, cwd, **kw)

    monkeypatch.setattr(git_subprocess, "run", stub)

    assert run_upgrade(root, dry_run=True) == 2

    assert f"error: git {command} failed in {where} ({reason})" in capsys.readouterr().err
    assert _snapshot(root) == files


def test_a_timed_out_check_ignore_still_finishes_the_real_run(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checkout's check-ignore timing out gives the scan no ignored set, and the run still exits 0."""
    root = old_repo(tmp_path)
    real_run = subprocess.run

    def stub(args, **kw):
        argv = list(args)
        if argv and argv[0] == "git" and "-C" in argv and "check-ignore" in argv and "--stdin" in argv:
            raise subprocess.TimeoutExpired(argv, git_subprocess.DEFAULT_TIMEOUT)
        return real_run(args, **kw)

    monkeypatch.setattr(subprocess, "run", stub)

    assert run_upgrade(root) == 0

    out, err = capsys.readouterr()
    assert "== next" in out
    assert "Traceback" not in out and "Traceback" not in err


def test_upgrade_help_states_exit_2_when_a_git_call_fails(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        upgrade.main(["--help"])
    assert caught.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "The exit code is 2 when a git call it depends on fails or times out" in text


def test_ls_files_exit_1_means_untracked(tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    root = old_repo(tmp_path)
    (root / "roadmap.md").write_text("drifted\n", encoding="utf-8")
    _committed(root)
    _stub_git(monkeypatch, "--error-unmatch", GitResult(1, "", "error: pathspec did not match\n"))

    assert run_upgrade(root, dry_run=True) == 0

    out = capsys.readouterr().out
    assert "would write roadmap-context.md (specy-road digest)" in out and "roadmap.md (specy-road export)" not in out


def _tree_names(root: Path) -> set[str]:
    names: set[str] = set()
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            names.add((Path(dirpath) / name).relative_to(root).as_posix())
    return names


def _file_texts(root: Path) -> str:
    """Text of regular files under ``root``. Symlinks are not followed, so a link cannot pull the checkout in."""
    parts: list[str] = []
    for dirpath, _dirs, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(parts)


class _ListingTemp(tempfile.TemporaryDirectory):
    """Records the temp directory's paths and file text in ``listings`` and ``texts`` while they still exist."""

    listings: list[set[str]] = []
    texts: list[str] = []

    def __exit__(self, exc, value, tb):
        path = Path(self.name)
        if path.is_dir():
            type(self).listings.append(_tree_names(path))
            type(self).texts.append(_file_texts(path))
        return super().__exit__(exc, value, tb)


def _has(paths: set[str], name: str) -> bool:
    return any(name in path.split("/") for path in paths)


@pytest.mark.parametrize("dry_run", [True, False])
def test_ignored_secrets_and_a_nested_repo_stay_out_of_the_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, dry_run: bool
) -> None:
    """Listed while the temp directory exists: an ignored secret, an ignored directory and a nested repo are absent."""
    from specy_road.bundled_scripts import upgrade_plan

    root = old_repo(tmp_path / "repo")
    (root / "keep-me.txt").write_text("visible\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    secret = root / "node_modules" / "pkg"
    secret.mkdir(parents=True)
    (secret / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8") + ".env\nnode_modules/\n", encoding="utf-8")
    nested = root / "vendor" / "other"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(nested)], check=True)
    (nested / "key.txt").write_text("nested-secret\n", encoding="utf-8")
    (root / "env-link").symlink_to(".env")
    (root / "modules-link").symlink_to("node_modules", target_is_directory=True)
    (root / "nested-link").symlink_to(Path("vendor") / "other", target_is_directory=True)
    _ListingTemp.listings, _ListingTemp.texts = [], []
    monkeypatch.setattr(upgrade.tempfile, "TemporaryDirectory", _ListingTemp)
    monkeypatch.setattr(upgrade_plan.tempfile, "TemporaryDirectory", _ListingTemp)

    assert run_upgrade(root, dry_run=dry_run) == 0

    assert _ListingTemp.listings
    for names, text in zip(_ListingTemp.listings, _ListingTemp.texts, strict=True):
        assert not _has(names, ".env")
        assert not _has(names, "node_modules")
        assert not any("vendor/other" in path for path in names)
        assert _has(names, "env-link") and _has(names, "modules-link") and _has(names, "nested-link")
        assert _has(names, "keep-me.txt") and _has(names, "AGENTS.md")
        assert "SECRET=1" not in text and "nested-secret" not in text and "module.exports" not in text
    if dry_run:
        assert capsys.readouterr().out.count("ignored files are not copied") == 1


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_global_excludes_file_keeps_a_secret_out_of_both_mirrors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    """A ``core.excludesFile`` in the caller's gitconfig hides the secret on a real run and a dry run."""
    from specy_road.bundled_scripts import upgrade_plan

    root = old_repo(tmp_path / "repo")
    (root / "keep-me.txt").write_text("visible\n", encoding="utf-8")
    (root / "secret.env").write_text("GLOBALSECRET=1\n", encoding="utf-8")
    excludes = tmp_path / "excludes"
    excludes.write_text("secret.env\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text(f"[core]\n\texcludesFile = {excludes}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM"):
        monkeypatch.delenv(name, raising=False)
    _ListingTemp.listings, _ListingTemp.texts = [], []
    monkeypatch.setattr(upgrade.tempfile, "TemporaryDirectory", _ListingTemp)
    monkeypatch.setattr(upgrade_plan.tempfile, "TemporaryDirectory", _ListingTemp)

    assert run_upgrade(root, dry_run=dry_run) == 0

    assert _ListingTemp.listings
    for names, text in zip(_ListingTemp.listings, _ListingTemp.texts, strict=True):
        assert not _has(names, "secret.env")
        assert "GLOBALSECRET=1" not in text
        assert _has(names, "keep-me.txt")


@pytest.mark.parametrize("dry_run", [True, False])
def test_an_unsearchable_directory_is_left_out_of_the_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    """A mode-000 directory does not abort either run, and it is not in the temp directory."""
    from specy_road.bundled_scripts import upgrade_plan

    root = old_repo(tmp_path / "repo")
    (root / "keep-me.txt").write_text("visible\n", encoding="utf-8")
    private = root / "private"
    private.mkdir()
    (private / "secret.txt").write_text("NOSEE\n", encoding="utf-8")
    private.chmod(0)
    (root / "private-link").symlink_to("private", target_is_directory=True)
    _ListingTemp.listings, _ListingTemp.texts = [], []
    monkeypatch.setattr(upgrade.tempfile, "TemporaryDirectory", _ListingTemp)
    monkeypatch.setattr(upgrade_plan.tempfile, "TemporaryDirectory", _ListingTemp)
    caught: PermissionError | None = None
    try:
        code: int | None = run_upgrade(root, dry_run=dry_run)
    except PermissionError as exc:
        code, caught = None, exc
    finally:
        private.chmod(0o755)

    assert _ListingTemp.listings
    for names, text in zip(_ListingTemp.listings, _ListingTemp.texts, strict=True):
        assert not _has(names, "private")
        assert "NOSEE" not in text
        assert _has(names, "private-link") and _has(names, "keep-me.txt")
    # The copy leaves the directory out on both paths. A dry run validates that copy, so it finishes.
    # A real run still reaches the checkout's own sibling walk, which is outside this leaf.
    if dry_run:
        assert code == 0 and caught is None
    else:
        assert caught is not None and "private/.git" in str(caught)
        assert "upgrade_plan" not in "".join(traceback.format_tb(caught.__traceback__))


def test_an_ignored_current_digest_is_not_predicted_as_a_rewrite(tmp_path: Path, capsys) -> None:
    """An ignored ``roadmap-context.md`` that matches the roadmap is current in the preview and the real run."""
    root = old_repo(tmp_path)
    assert run_upgrade(root) == 0
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8") + "roadmap-context.md\n", encoding="utf-8")
    digest = root / "roadmap-context.md"
    assert digest.is_file() and digest.read_bytes() == render_digest(root).encode()
    assert subprocess.run(["git", "check-ignore", "-q", "--", "roadmap-context.md"], cwd=root).returncode == 0
    current = digest.read_bytes()
    capsys.readouterr()

    assert run_upgrade(root, dry_run=True) == 0

    dry = capsys.readouterr().out
    assert "would write roadmap-context.md" not in dry and "generated files already current" in dry

    assert run_upgrade(root) == 0
    assert "wrote roadmap-context.md" not in capsys.readouterr().out
    assert digest.read_bytes() == current


def test_large_ignored_content_does_not_change_the_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dry run's plan is the same with or without a large ignored tree beside the checkout."""
    root = old_repo(tmp_path)
    ignore = root / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8") + ".env\nnode_modules/\n", encoding="utf-8")
    plans: list[list[tuple]] = []
    real = upgrade.make_plan

    def spy(*args, **kwargs):
        plan = real(*args, **kwargs)
        plans.append([(entry.path, entry.action, entry.data, entry.link, entry.mode) for entry in plan.entries])
        return plan

    monkeypatch.setattr(upgrade, "make_plan", spy)

    assert run_upgrade(root, dry_run=True) == 0
    bulk = root / "node_modules" / "pkg"
    bulk.mkdir(parents=True)
    (bulk / "bulk.bin").write_bytes(b"x" * 1_000_000)
    (root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    assert run_upgrade(root, dry_run=True) == 0

    assert plans[0] == plans[1]
