"""M15.15: upgrade ships work templates prompts reference; README lists upgrade steps."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts import upgrade
from specy_road.bundled_scripts.upgrade import run_upgrade
from specy_road.runtime_paths import specy_road_package_dir
from specy_road.upgrade_templates import (
    UPGRADE_STEP_LABELS,
    bundled_work_template_names,
    copy_missing_work_templates,
    readme_upgrade_step_labels,
    referenced_work_template_names,
    upgrade_help_step_labels,
)
from tests.upgrade_repo_helpers import old_repo

_README = (
    specy_road_package_dir() / "templates" / "specyrd" / "dot-specyrd" / "README.md"
)


def test_every_prompt_referenced_work_template_is_bundled_and_ships() -> None:
    referenced = referenced_work_template_names()
    bundled = bundled_work_template_names()
    assert referenced, "expected at least one work/*.template.md reference in prompt builders"
    assert referenced <= bundled, f"prompts reference templates not shipped: {referenced - bundled}"


def test_upgrade_adds_missing_referenced_work_templates(tmp_path: Path) -> None:
    root = old_repo(tmp_path)
    work = root / "work"
    for path in work.glob("*.template.md"):
        path.unlink()

    assert run_upgrade(root, prune=True) == 0

    for name in referenced_work_template_names():
        assert (work / name).is_file()


def test_upgrade_never_overwrites_an_existing_work_template(tmp_path: Path) -> None:
    root = old_repo(tmp_path)
    custom = root / "work" / "review-record.template.md"
    custom.write_text("ours\n", encoding="utf-8")

    assert copy_missing_work_templates(root) == []
    assert custom.read_text(encoding="utf-8") == "ours\n"


def test_dry_run_lists_work_templates_it_would_add(tmp_path: Path, capsys) -> None:
    root = old_repo(tmp_path)
    for path in (root / "work").glob("*.template.md"):
        path.unlink()

    assert run_upgrade(root, dry_run=True, prune=True) == 0

    out = capsys.readouterr().out
    for name in referenced_work_template_names():
        assert f"would write work/{name} (work template referenced by prompts)" in out


def test_dot_specyrd_readme_upgrade_steps_match_upgrade_help() -> None:
    readme_text = _README.read_text(encoding="utf-8")
    assert upgrade_help_step_labels(upgrade.__doc__) == UPGRADE_STEP_LABELS
    assert readme_upgrade_step_labels(readme_text) == UPGRADE_STEP_LABELS
