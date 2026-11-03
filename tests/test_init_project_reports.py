"""``init project`` names every path it writes, identically in the dry run and the real run."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from specy_road.agent_ignores import SESSION_WORK_FILES
from specy_road.init_project import run_init_project

_ENTRY = re.compile(r"^(?:would write|wrote) (.+)$")
_COUNT = re.compile(r"^dry-run: (\d+) path\(s\) would be written")


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)


def _listed(out: str) -> list[str]:
    return [m.group(1) for line in out.splitlines() if (m := _ENTRY.match(line))]


def _on_disk(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def _dry_then_real(project: Path, capsys) -> tuple[list[str], list[str], str]:
    assert run_init_project(project, dry_run=True, profiles="none") == 0
    dry_out = capsys.readouterr().out
    assert run_init_project(project, profiles="none") == 0
    return _listed(dry_out), _listed(capsys.readouterr().out), dry_out


@pytest.mark.parametrize("existing_gitignore", [False, True])
def test_dry_run_lists_what_the_real_run_writes(tmp_path: Path, capsys, existing_gitignore: bool) -> None:
    _git_init(tmp_path)
    if existing_gitignore:
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    before = _on_disk(tmp_path)

    dry, real, dry_out = _dry_then_real(tmp_path, capsys)

    assert dry == real
    count = next(int(m.group(1)) for line in dry_out.splitlines() if (m := _COUNT.match(line)))
    assert count == len(dry)
    names = [entry.split(" (")[0] for entry in real]
    for managed in ("AGENTS.md", ".specyrd/manifest.json", ".cursorindexingignore", ".gitignore"):
        assert managed in names
    # Every file the real run created or changed is named, and nothing else.
    changed = (_on_disk(tmp_path) - before) | ({".gitignore"} if existing_gitignore else set())
    assert set(names) == changed


def test_dry_run_matches_outside_a_repository(tmp_path: Path, capsys) -> None:
    dry, real, _ = _dry_then_real(tmp_path, capsys)

    assert dry == real
    assert ".gitignore (created)" in real
    assert set(entry.split(" (")[0] for entry in real) == _on_disk(tmp_path)


def test_existing_gitignore_reported_as_updated_with_the_runtime_rules(tmp_path: Path, capsys) -> None:
    _git_init(tmp_path)
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")

    assert run_init_project(tmp_path) == 0
    out = capsys.readouterr().out

    assert "wrote .gitignore (updated)" in out
    assert "skipped (exists): .gitignore" not in out
    text = gi.read_text(encoding="utf-8")
    assert text.startswith("node_modules/\n")
    block = text[text.index(">>> specy-road managed block"):]
    for rule in SESSION_WORK_FILES:
        assert f"\n{rule}\n" in block


def test_fresh_gitignore_keeps_the_template_header_and_one_copy_of_each_rule(tmp_path: Path) -> None:
    _git_init(tmp_path)

    assert run_init_project(tmp_path) == 0

    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ")
    rules = [ln for ln in lines if ln and not ln.startswith("#")]
    assert len(rules) == len(set(rules))
    assert set(SESSION_WORK_FILES) <= set(rules)


def test_nested_layout_writes_no_project_gitignore(tmp_path: Path, capsys) -> None:
    _git_init(tmp_path)
    project = tmp_path / "sr"

    dry, real, _ = _dry_then_real(project, capsys)

    assert dry == real
    assert not (project / ".gitignore").exists()
    assert not any(entry.startswith("sr/.gitignore") for entry in real)
    assert ".gitignore (created)" in real and "sr/AGENTS.md (created)" in real
    rules = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    for rule in SESSION_WORK_FILES:
        assert f"sr/{rule}" in rules
    # The block alone, no template header: its comments name unprefixed paths.
    assert rules[0].startswith("# >>> specy-road managed block")
