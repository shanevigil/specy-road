"""Every dotfile under specy_road/templates/ must be named in package-data.

setuptools package-data globs are ``fnmatch``-style, where ``*`` does not match
a leading dot. A dotfile covered only by ``templates/project/**/*`` is dropped
from the wheel with no warning, and because ``init project`` copies whatever is
on disk, an editable checkout still scaffolds correctly — so the gap only shows
up for pip-installed users. That is how the scaffold shipped without its
``.gitignore``, which left consumer repos committing the toolkit's own ``work/``
session artifacts.

``scripts/verify_wheel_contents.py`` asserts the same thing against a built
wheel at release time; this catches it at PR time.
"""

from __future__ import annotations

from tests.support import REPO
import pytest

import tomllib
from pathlib import Path
from tests.support.same.declared_package_data_d6ce072f444e import declared_package_data
pytestmark = pytest.mark.repo

TEMPLATES = REPO / "specy_road" / "templates"




def _template_dotfiles() -> list[str]:
    out = []
    for p in sorted(TEMPLATES.rglob("*")):
        if p.is_file() and any(part.startswith(".") for part in p.relative_to(TEMPLATES).parts):
            out.append(p.relative_to(REPO / "specy_road").as_posix())
    return out


def test_template_dotfiles_are_explicitly_declared() -> None:
    declared = set(declared_package_data())
    undeclared = [rel for rel in _template_dotfiles() if rel not in declared]
    assert not undeclared, (
        "these template dotfiles are not listed in [tool.setuptools.package-data] "
        f"and would be silently dropped from the wheel: {undeclared}"
    )


def test_the_scaffold_gitignore_is_one_of_them() -> None:
    """Guards the guard: a rename must not quietly empty the check above."""
    assert "templates/project/.gitignore" in _template_dotfiles()
