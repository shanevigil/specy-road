"""M13.2: `specy-road upgrade` says what is upgrading, validates in a dry run, and owns its line-cap overruns.

rc3 adopters ran a dry run under the old install without being told so, saw a
breaking validate error only after every refresh was written, and found a
project file pushed over its cap with no word from upgrade.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specy_road import __version__
from specy_road.bundled_scripts import upgrade
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.file_limits_engine import collect_tracked_files, run_file_limits_scan
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
