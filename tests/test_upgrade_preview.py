"""M13.2: `specy-road upgrade` says what is upgrading, validates in a dry run, and owns its line-cap overruns.

rc3 adopters ran a dry run under the old install without being told so, saw a
breaking validate error only after every refresh was written, and found a
project file pushed over its cap with no word from upgrade.
"""

from __future__ import annotations

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
from tests.test_upgrade import _old_repo

GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *GIT_ID, *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def test_header_names_the_install_and_a_dry_run_says_it_previews(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)
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
    root = _old_repo(tmp_path)
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
    assert len(validated) == 1 and validated[0] != root.resolve() and not validated[0].exists()
    assert _snapshot(root) == files
    assert _git(root, "status", "--porcelain") == status


def _capped_agents_md(root: Path, agents_lines: int, cap: int) -> None:
    (root / "AGENTS.md").write_text("".join(f"line {i}\n" for i in range(agents_lines)), encoding="utf-8")
    (root / "constraints" / "file-limits.yaml").write_text(yaml.safe_dump({
        "max_lines_per_file": cap, "applies_to_globs": ["AGENTS.md"],
    }), encoding="utf-8")


def test_a_file_the_upgrade_pushes_over_its_cap_is_named(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)
    _capped_agents_md(root, 3, 10)

    run_upgrade(root, dry_run=True)
    assert "AGENTS.md: this upgrade pushed it over its cap: 3 ->" in capsys.readouterr().out
    assert (root / "AGENTS.md").read_text(encoding="utf-8").count("\n") == 3

    run_upgrade(root)
    new = (root / "AGENTS.md").read_text(encoding="utf-8").count("\n")
    out = capsys.readouterr().out
    assert f"AGENTS.md: this upgrade pushed it over its cap: 3 -> {new} lines (cap 10)" in out


def test_a_file_already_over_its_cap_is_not_blamed_on_the_upgrade(tmp_path: Path, capsys) -> None:
    root = _old_repo(tmp_path)
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
    root = _old_repo(tmp_path / "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "old scaffold")
    other = (tmp_path / "other").resolve()
    _git(root, "worktree", "add", "-q", "-b", "feature/x", str(other))

    run_upgrade(root)

    out = capsys.readouterr().out
    assert "\n== other worktrees\n" in out
    assert (f"{other} (feature/x): not upgraded; it still has the old managed files while sharing this install."
            f" Run there: cd {other} && specy-road upgrade") in out.splitlines()
    assert str(root.resolve()) + " (" not in out
