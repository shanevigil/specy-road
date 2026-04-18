"""Tests for vision/constitution completion hints (PM GUI)."""

from __future__ import annotations

from pathlib import Path

from specy_road.governance_completion import (
    VISION_STARTER,
    constitution_needs_completion,
    vision_needs_completion,
)


def test_vision_needs_when_missing(tmp_path: Path) -> None:
    assert vision_needs_completion(tmp_path) is True


def test_vision_needs_when_starter_only(tmp_path: Path) -> None:
    (tmp_path / "vision.md").write_text(VISION_STARTER, encoding="utf-8")
    assert vision_needs_completion(tmp_path) is True


def test_vision_ok_when_customized(tmp_path: Path) -> None:
    (tmp_path / "vision.md").write_text(
        VISION_STARTER + "\n\nOur actual vision statement.",
        encoding="utf-8",
    )
    assert vision_needs_completion(tmp_path) is False


def test_vision_needs_when_project_template_only(tmp_path: Path) -> None:
    """`specy-road init project` ships templates/project/vision.md (differs from PM UI starter)."""
    from importlib import resources

    tpl = resources.files("specy_road").joinpath("templates", "project", "vision.md")
    (tmp_path / "vision.md").write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")
    assert vision_needs_completion(tmp_path) is True


def test_constitution_needs_when_missing(tmp_path: Path) -> None:
    assert constitution_needs_completion(tmp_path) is True


def test_constitution_needs_when_templates_only(tmp_path: Path) -> None:
    from importlib import resources

    root = tmp_path
    const_dir = root / "constitution"
    const_dir.mkdir(parents=True)
    pkg = resources.files("specy_road").joinpath("templates", "constitution")
    (const_dir / "purpose.md").write_text(
        pkg.joinpath("purpose.md.template").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (const_dir / "principles.md").write_text(
        pkg.joinpath("principles.md.template").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert constitution_needs_completion(tmp_path) is True


def test_constitution_ok_when_customized(tmp_path: Path) -> None:
    from importlib import resources

    root = tmp_path
    const_dir = root / "constitution"
    const_dir.mkdir(parents=True)
    pkg = resources.files("specy_road").joinpath("templates", "constitution")
    (const_dir / "purpose.md").write_text(
        pkg.joinpath("purpose.md.template").read_text(encoding="utf-8")
        + "\n\nShip the toolkit.",
        encoding="utf-8",
    )
    (const_dir / "principles.md").write_text(
        pkg.joinpath("principles.md.template").read_text(encoding="utf-8")
        + "\n\nWe value clarity.",
        encoding="utf-8",
    )
    assert constitution_needs_completion(tmp_path) is False
