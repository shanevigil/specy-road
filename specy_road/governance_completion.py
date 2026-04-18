"""Detect whether repo vision/constitution files still need human completion (PM GUI hints)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

# Keep in sync with `gui/pm-gantt/src/visionStarter.ts` (Create vision.md in PM UI).
VISION_STARTER = """# Vision

Describe the product vision for this repository. See README for how this relates to the roadmap.
"""


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n").strip()


def _project_vision_template_text() -> str:
    """``specy-road init project`` copies ``templates/project/vision.md`` — distinct from UI starter."""
    pkg = resources.files("specy_road").joinpath("templates", "project", "vision.md")
    return pkg.read_text(encoding="utf-8")


def _constitution_template(name: str) -> str:
    pkg = resources.files("specy_road").joinpath("templates", "constitution", name)
    return pkg.read_text(encoding="utf-8")


def vision_needs_completion(root: Path) -> bool:
    """True when ``vision.md`` is missing, blank, or still an init template (UI or ``init project``)."""
    p = root / "vision.md"
    if not p.is_file():
        return True
    content = p.read_text(encoding="utf-8", errors="replace")
    n = _norm(content)
    if not n:
        return True
    if n == _norm(VISION_STARTER):
        return True
    if n == _norm(_project_vision_template_text()):
        return True
    return False


def constitution_needs_completion(root: Path) -> bool:
    """True when either purpose/principles is missing, blank, or still the scaffold template."""
    purpose_p = root / "constitution" / "purpose.md"
    principles_p = root / "constitution" / "principles.md"
    tpl_p = _constitution_template("purpose.md.template")
    tpl_pr = _constitution_template("principles.md.template")
    if not purpose_p.is_file() or not principles_p.is_file():
        return True
    purpose = purpose_p.read_text(encoding="utf-8", errors="replace")
    principles = principles_p.read_text(encoding="utf-8", errors="replace")
    np, npr = _norm(purpose), _norm(principles)
    if not np or not npr:
        return True
    if np == _norm(tpl_p) or npr == _norm(tpl_pr):
        return True
    return False
