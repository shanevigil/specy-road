"""Every optional extra in pyproject.toml (except ``dev``) is named in the install docs, and the GUI
install lines name ``[gui]``, never its deprecated alias ``[gui-next]``."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL_DOCS = ("docs/install-and-usage.md",)


def test_install_docs_name_every_extra() -> None:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    extras = set(pyproject["project"]["optional-dependencies"]) - {"dev"}
    text = "\n".join((REPO / path).read_text(encoding="utf-8") for path in INSTALL_DOCS)
    missing = sorted(extra for extra in extras if f"[{extra}]" not in text)
    assert missing == [], f"name these extras in {' or '.join(INSTALL_DOCS)}: {missing}"


#: The docs whose install lines name the GUI extra (M16.6.1, A8).
GUI_INSTALL_DOCS = ("README.md", "docs/install-and-usage.md", "docs/pm-gui.md", "docs/pm-workflow.md",
                    "docs/contributor-guide.md")


def test_gui_install_lines_name_gui_not_its_alias() -> None:
    """A line that installs (``pip install`` or a ``specy-road[...]`` spec) never names gui-next; the
    one line that does is install-and-usage's deprecation note, which installs nothing."""
    hits = [f"{path}:{n}" for path in GUI_INSTALL_DOCS
            for n, line in enumerate((REPO / path).read_text(encoding="utf-8").splitlines(), 1)
            if "gui-next" in line and ("pip install" in line or "specy-road[" in line)]
    assert hits == []
