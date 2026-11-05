"""Missing ``work/*.template.md`` files that prompts and command stubs reference."""

from __future__ import annotations

import re
from pathlib import Path

import shutil

from specy_road.init_project import project_template_root
from specy_road.managed_block import resolves_outside
from specy_road.runtime_paths import specy_road_package_dir

_WORK = Path("work")
_TEMPLATE_SUFFIX = ".template.md"
_REF_IN_SOURCE = re.compile(r"work/([A-Za-z0-9][A-Za-z0-9.-]*\.template\.md)")
_README_SECTION = re.compile(
    r"## Updating after `pip install -U specy-road`\s*\n\n(.*?)(?:\n## |\Z)",
    re.DOTALL,
)

# Kept in sync with ``upgrade``'s module docstring and ``.specyrd/README.md``.
UPGRADE_STEP_LABELS: tuple[str, ...] = (
    "refresh-schemas",
    "refresh-profiles",
    "shipped docs and templates",
    "refresh-stubs",
    "validate",
    "digest --check",
)


def bundled_work_template_names() -> frozenset[str]:
    """Basenames of every ``*.template.md`` under ``templates/project/work/``."""
    root = project_template_root() / _WORK
    if not root.is_dir():
        return frozenset()
    return frozenset(p.name for p in root.glob(f"*{_TEMPLATE_SUFFIX}"))


def _prompt_builder_sources() -> list[Path]:
    bundled = specy_road_package_dir() / "bundled_scripts"
    paths = [bundled / "do_next_prompt.py"]
    paths.extend(sorted(bundled.glob("role_prompt*.py")))
    paths.extend(sorted((specy_road_package_dir() / "templates" / "specyrd" / "commands").glob("*.md")))
    return paths


def referenced_work_template_names() -> frozenset[str]:
    """Names of ``work/*.template.md`` cited in prompt builders and specyrd command stubs."""
    found: set[str] = set()
    for path in _prompt_builder_sources():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for match in _REF_IN_SOURCE.finditer(text):
            found.add(match.group(1))
    return frozenset(found)


def upgrade_help_step_labels(doc: str | None) -> tuple[str, ...]:
    """Step labels in order, as ``upgrade --help`` lists them."""
    if not doc:
        return ()
    labels: list[str] = []
    for line in doc.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] not in "123456789":
            continue
        if ". ``" in stripped:
            head, _, rest = stripped.partition(". ``")
            if not head.isdigit():
                continue
            name, _, tail = rest.partition("``")
            labels.append(name.strip())
            if ", then ``" in tail:
                _, _, second = tail.partition(", then ``")
                second_name, _, _ = second.partition("``")
                labels.append(second_name.strip())
        elif stripped[0].isdigit() and ". " in stripped:
            head, _, rest = stripped.partition(". ")
            if not head.isdigit():
                continue
            title, _, _ = rest.partition(" —")
            labels.append(title.strip().rstrip(","))
    return tuple(labels)


def readme_upgrade_step_labels(readme_text: str) -> tuple[str, ...]:
    """Parse the upgrade step labels from the ``Updating after pip install`` paragraph."""
    section = _README_SECTION.search(readme_text)
    if not section:
        return ()
    body = section.group(1)
    positions = [body.find(label) for label in UPGRADE_STEP_LABELS]
    if any(p < 0 for p in positions) or positions != sorted(positions):
        return ()
    return UPGRADE_STEP_LABELS


def missing_work_template_rels(existence_root: Path) -> list[str]:
    """Project-relative paths of referenced work templates the tree lacks."""
    ship = bundled_work_template_names() & referenced_work_template_names()
    missing: list[str] = []
    for name in sorted(ship):
        rel = f"{_WORK.as_posix()}/{name}"
        path = existence_root / rel
        if path.exists() or path.is_symlink():
            continue
        src = project_template_root() / _WORK / name
        if src.is_file():
            missing.append(rel)
    return missing


def copy_missing_work_templates(
    project: Path,
    *,
    dry_run: bool = False,
    existence_root: Path | None = None,
) -> list[str]:
    """Copy bundled work templates the prompts reference when the project lacks them.

    Never overwrites an existing file or symlink. Returns project-relative paths
    such as ``work/review-record.template.md``.

    ``existence_root`` is where to test for an existing file; copies land under
    ``project`` (defaults to the same root).
    """
    exists_at = existence_root or project
    copied: list[str] = []
    for rel in missing_work_template_rels(exists_at):
        src = project_template_root() / rel
        dst = project / rel
        if resolves_outside(project, dst):
            print(f"skipped {rel} (a symlink leads outside the repository)")
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied.append(rel)
    return copied
