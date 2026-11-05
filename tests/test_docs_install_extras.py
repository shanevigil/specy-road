"""Every optional extra in pyproject.toml (except ``dev``) is named in the install docs."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL_DOCS = ("docs/install-and-usage.md", "docs/install-release-candidates.md")


def test_install_docs_name_every_extra() -> None:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    extras = set(pyproject["project"]["optional-dependencies"]) - {"dev"}
    text = "\n".join((REPO / path).read_text(encoding="utf-8") for path in INSTALL_DOCS)
    missing = sorted(extra for extra in extras if f"[{extra}]" not in text)
    assert missing == [], f"name these extras in {' or '.join(INSTALL_DOCS)}: {missing}"
