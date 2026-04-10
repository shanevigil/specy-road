"""Create or refresh `constitution/purpose.md` and `constitution/principles.md` from packaged templates."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path


PURPOSE_REL = "constitution/purpose.md"
PRINCIPLES_REL = "constitution/principles.md"


@dataclass(frozen=True)
class ConstitutionScaffoldResult:
    """Paths are repo-relative POSIX strings."""

    written: tuple[str, ...]
    skipped_existing: tuple[str, ...]


class ConstitutionExistsError(Exception):
    """Both constitution files already exist and ``force`` is false."""

    def __init__(self, existing: tuple[str, ...]) -> None:
        self.existing = existing
        super().__init__(
            "constitution files already exist: "
            + ", ".join(existing)
            + ". Use --force to overwrite, or edit the files in place."
        )


def _template_text(name: str) -> str:
    pkg = resources.files("specy_road").joinpath("templates", "constitution", name)
    return pkg.read_text(encoding="utf-8")


def write_constitution(repo_root: Path, *, force: bool = False) -> ConstitutionScaffoldResult:
    """Write missing starter files under ``constitution/``. Skip files that already exist unless ``force``.

    If **both** files already exist and ``force`` is false, raises :class:`ConstitutionExistsError`
    (so callers can map to HTTP 409). If only one exists, the missing file is written.
    """
    root = repo_root.resolve()
    const_dir = root / "constitution"
    purpose_p = root.joinpath(*PURPOSE_REL.split("/"))
    principles_p = root.joinpath(*PRINCIPLES_REL.split("/"))

    purpose_exists = purpose_p.is_file()
    principles_exists = principles_p.is_file()

    if purpose_exists and principles_exists and not force:
        raise ConstitutionExistsError((PURPOSE_REL, PRINCIPLES_REL))

    written: list[str] = []
    skipped: list[str] = []

    tpl_purpose = _template_text("purpose.md.template")
    tpl_principles = _template_text("principles.md.template")

    const_dir.mkdir(parents=True, exist_ok=True)

    if purpose_exists and not force:
        skipped.append(PURPOSE_REL)
    else:
        purpose_p.write_text(tpl_purpose, encoding="utf-8")
        written.append(PURPOSE_REL)

    if principles_exists and not force:
        skipped.append(PRINCIPLES_REL)
    else:
        principles_p.write_text(tpl_principles, encoding="utf-8")
        written.append(PRINCIPLES_REL)

    return ConstitutionScaffoldResult(
        written=tuple(written),
        skipped_existing=tuple(skipped),
    )
