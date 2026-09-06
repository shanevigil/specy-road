"""Keep one specy-road section inside a consumer's ``CLAUDE.md``.

``specyrd init`` used to write the whole of ``CLAUDE.md`` from a template, and
``--force`` — documented only as "overwrite existing specyrd-managed command
files and README" — replaced a consumer's hand-authored guide with it. No
warning, no backup, no diff, and the file was never listed in
``.specyrd/manifest.json``, so nothing downstream could even tell whether the
kit owned it.

``CLAUDE.md`` belongs to the consumer for exactly the reason ``.gitignore``
does: they have their own content in it, and we have one section that must stay
current. So it gets the same treatment — a marked block, rewritten in place,
with everything outside the markers never read and never touched. See
:mod:`specy_road.managed_block`.

The markers here are HTML comments rather than ``#``: in Markdown a ``#``
marker would render as a top-level heading in the middle of someone's document.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from specy_road import __version__
from specy_road.managed_block import (
    HTML_COMMENT,
    UNCHANGED,
    apply_managed_block,
)

AGENT_GUIDE = "CLAUDE.md"
_TEMPLATE_NAME = "claude-md-block.md"

# Which agent packs contribute a guide section. Cursor is steered by
# `.cursor/rules/` and `.cursorindexingignore` instead, and `generic` has no
# convention to hook into.
GUIDE_AGENTS = frozenset({"claude-code"})


def _read_block_template() -> str:
    pkg_dir = Path(__file__).resolve().parent / "templates" / "specyrd"
    path = pkg_dir / _TEMPLATE_NAME
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return (
        resources.files("specy_road")
        .joinpath("templates", "specyrd", _TEMPLATE_NAME)
        .read_text(encoding="utf-8")
    )


def render_guide_lines(project_prefix: str = "") -> list[str]:
    """The block body, with the project prefix and version substituted.

    ``project_prefix`` is the project root's path within the checkout (``"sr/"``
    or ``""``). ``CLAUDE.md`` lives at the **git** root while every path it
    names is inside the **project** root, and those coincide only in the
    embedded layout — so without this a nested repo got a guide in which every
    pointer was wrong.
    """
    text = _read_block_template()
    text = text.replace("{{SPECYRD_VERSION}}", __version__)
    text = text.replace("{{PROJECT_PREFIX}}", project_prefix)
    return text.rstrip("\n").splitlines()


def apply_agent_guide_block(
    git_root: Path, project_prefix: str = "", *, dry_run: bool = False
) -> str:
    """Write the specy-road section into ``CLAUDE.md``. Returns the outcome."""
    return apply_managed_block(
        git_root / AGENT_GUIDE,
        render_guide_lines(project_prefix),
        style=HTML_COMMENT,
        dry_run=dry_run,
    )


def apply_guide_and_report(
    git_root: Path,
    prefix: str,
    written: list[str],
    *,
    agent: str,
    dry_run: bool = False,
) -> None:
    """:func:`apply_agent_guide_block` for packs that have one, reporting it.

    Mirrors ``agent_ignores.apply_and_report`` so a caller reports both managed
    blocks the same way.
    """
    if agent not in GUIDE_AGENTS:
        return
    outcome = apply_agent_guide_block(git_root, prefix, dry_run=dry_run)
    if outcome != UNCHANGED:
        written.append(f"{AGENT_GUIDE} ({outcome})")
