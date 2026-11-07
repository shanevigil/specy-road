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


def _dry_then_real(project: Path, capsys) -> tuple[list[str], list[str], str, str]:
    assert run_init_project(project, dry_run=True, profiles="none") == 0
    dry_out = capsys.readouterr().out
    assert run_init_project(project, profiles="none") == 0
    real_out = capsys.readouterr().out
    return _listed(dry_out), _listed(real_out), dry_out, real_out


def _next_steps(directory: Path, prefix: str, *, outside_git: bool = False) -> list[str]:
    steps = ["git init"] if outside_git else []
    steps += [
        f"Set integration_branch and remote in {prefix}roadmap/git-workflow.yaml",
        'git add -A && git commit -m "specy-road init"',
        "specy-road validate",
    ]
    return [f"Next steps (run from {directory}):", *(f"  {n}. {step}" for n, step in enumerate(steps, 1))]


@pytest.mark.parametrize("existing_gitignore", [False, True])
def test_dry_run_lists_what_the_real_run_writes(tmp_path: Path, capsys, existing_gitignore: bool) -> None:
    _git_init(tmp_path)
    if existing_gitignore:
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    before = _on_disk(tmp_path)

    dry, real, dry_out, real_out = _dry_then_real(tmp_path, capsys)

    assert dry == real
    count = next(int(m.group(1)) for line in dry_out.splitlines() if (m := _COUNT.match(line)))
    assert count == len(dry)
    assert "Next steps" not in dry_out
    where = tmp_path.resolve()
    assert where != Path.cwd().resolve()
    block = _next_steps(where, "")
    lines = real_out.splitlines()
    assert lines[-len(block):] == block
    assert lines[-len(block) - 1] == f"Initialized specy-road layout under {where}"
    names = [entry.split(" (")[0] for entry in real]
    for managed in ("AGENTS.md", ".specyrd/manifest.json", ".cursorindexingignore", ".gitignore"):
        assert managed in names
    # Every file the real run created or changed is named, and nothing else.
    changed = (_on_disk(tmp_path) - before) | ({".gitignore"} if existing_gitignore else set())
    assert set(names) == changed


def test_dry_run_matches_outside_a_repository(tmp_path: Path, capsys) -> None:
    dry, real, dry_out, real_out = _dry_then_real(tmp_path, capsys)

    assert dry == real
    assert ".gitignore (created)" in real
    assert set(entry.split(" (")[0] for entry in real) == _on_disk(tmp_path)
    assert "Next steps" not in dry_out
    where = tmp_path.resolve()
    block = _next_steps(where, "", outside_git=True)
    lines = real_out.splitlines()
    assert lines[-len(block):] == block
    assert lines[-len(block) - 1] == f"Initialized specy-road layout under {where}"


@pytest.mark.parametrize("sub", ["", "sr"])
def test_generated_files_are_listed_and_only_the_real_run_writes_them(tmp_path: Path, capsys, sub: str) -> None:
    _git_init(tmp_path)
    prefix = f"{sub}/" if sub else ""
    before = _on_disk(tmp_path)

    assert run_init_project(tmp_path / sub, dry_run=True, profiles="none") == 0
    dry = _listed(capsys.readouterr().out)
    assert _on_disk(tmp_path) == before

    assert run_init_project(tmp_path / sub, profiles="none") == 0
    real = _listed(capsys.readouterr().out)

    assert dry == real
    assert {f"{prefix}roadmap.md", f"{prefix}roadmap-context.md"} <= set(real)
    assert _on_disk(tmp_path) - before == {entry.split(" (")[0] for entry in real}


def test_an_existing_roadmap_md_survives_unless_forced(tmp_path: Path, capsys) -> None:
    _git_init(tmp_path)
    mine = tmp_path / "roadmap.md"
    mine.write_text("# Our plans\n", encoding="utf-8")

    assert run_init_project(tmp_path, profiles="none") == 0

    assert "skipped (exists): roadmap.md" in capsys.readouterr().out
    assert mine.read_text(encoding="utf-8") == "# Our plans\n"
    assert not (tmp_path / "roadmap-context.md").exists()

    assert run_init_project(tmp_path, force=True, profiles="none") == 0

    assert "wrote roadmap.md" in capsys.readouterr().out.splitlines()
    assert mine.read_text(encoding="utf-8") != "# Our plans\n"
    assert (tmp_path / "roadmap-context.md").is_file()


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

    dry, real, dry_out, real_out = _dry_then_real(project, capsys)

    assert dry == real
    assert "Next steps" not in dry_out
    where = tmp_path.resolve()
    assert where != project.resolve() and where != Path.cwd().resolve()
    block = _next_steps(where, "sr/")
    lines = real_out.splitlines()
    assert lines[-len(block):] == block
    assert lines[-len(block) - 1] == "Recorded project_root=sr in .specyrd/manifest.json"
    assert lines[-len(block) - 2] == f"Initialized specy-road layout under {project.resolve()}"
    assert not (project / ".gitignore").exists()
    assert not any(entry.startswith("sr/.gitignore") for entry in real)
    assert ".gitignore (created)" in real and "sr/AGENTS.md (created)" in real
    rules = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    for rule in SESSION_WORK_FILES:
        assert f"sr/{rule}" in rules
    # The block alone, no template header: its comments name unprefixed paths.
    assert rules[0].startswith("# >>> specy-road managed block")


@pytest.mark.parametrize("kind", ["manifest", "template", "profiles"])
def test_a_refused_run_prints_no_next_steps(tmp_path: Path, capsys, monkeypatch, kind: str) -> None:
    if kind == "manifest":
        (tmp_path / "roadmap").mkdir()
        (tmp_path / "roadmap" / "manifest.json").write_text("{}\n", encoding="utf-8")
        assert run_init_project(tmp_path, profiles="none") == 1
    elif kind == "template":
        monkeypatch.setattr(
            "specy_road.init_project.project_template_root",
            lambda: tmp_path / "missing-template",
        )
        assert run_init_project(tmp_path, profiles="none") == 2
    else:
        assert run_init_project(tmp_path, profiles="no-such-profile") == 1
    assert capsys.readouterr().out == ""
