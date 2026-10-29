"""Keep one specy-road section inside the project's ``AGENTS.md``.

``init project`` used to write the whole of ``AGENTS.md`` and skip an existing
one, so a team with its own file got no specy-road guidance at all, or lost the
file to ``--force``. ``AGENTS.md`` is the consumer's for the same reason
``CLAUDE.md`` is: they have their own rules in it, and the toolkit has one
section that must stay current. So it gets the same treatment
(:mod:`specy_road.managed_block`, HTML-comment markers): ``init project``
inserts the block into an existing file or creates the file with the block,
``refresh-stubs`` rewrites it, and ``validate`` warns when it is missing or
differs from what the installed version writes, and when its load order
names a file the project does not have.

The block opens with a precedence rule: the toolkit's rules on registry,
branches, review, and the shared tree are a floor; a project's own rules may
add to them, never relax them (design note
``docs/design-notes/agent-guidance-and-shared-checkouts.md``).

Unlike the ``CLAUDE.md`` block, this one is harness-neutral and lives at the
**project** root, next to ``roadmap/``: Cursor, Codex and Claude Code all read
``AGENTS.md``, and the ``CLAUDE.md`` block points at it rather than copying it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import strip_provenance
from specy_road.digest import DEFAULT_OUTPUT as DIGEST
from specy_road.doc_links import link_toolkit_docs
from specy_road.managed_block import (
    HTML_COMMENT,
    UNCHANGED,
    _split,
    apply_managed_block,
    render_block,
)

AGENTS_MD = "AGENTS.md"
_TEMPLATE = Path(__file__).resolve().parent / "templates" / "specyrd" / "agents-md-block.md"
_H1 = "# Agents — load order\n"


def render_agents_lines() -> list[str]:
    text = strip_provenance(_TEMPLATE.read_text(encoding="utf-8"))
    text = link_toolkit_docs(text.replace("{{SPECYRD_VERSION}}", __version__))
    return text.rstrip("\n").splitlines()


def apply_agents_md_block(project_root: Path, *, dry_run: bool = False) -> str:
    """Write the specy-road section into ``AGENTS.md``. Returns the outcome.

    A file that does not exist yet gets the scaffold's H1 above the block, so a
    fresh ``init project`` still produces a readable file rather than a bare
    marked section.
    """
    path = project_root / AGENTS_MD
    lines = render_agents_lines()
    if not path.is_file() and not path.is_symlink() and not dry_run:   # never write through a dangling link
        path.write_text(_H1, encoding="utf-8")
    return apply_managed_block(path, lines, style=HTML_COMMENT, dry_run=dry_run)


def agents_md_block_state(project_root: Path) -> str:
    """``"current"``, ``"stale"`` (block differs from this version), or ``"missing"``."""
    path = project_root / AGENTS_MD
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return "missing"
    _before, block, _after = _split(text, HTML_COMMENT)
    if block is None:
        return "missing"
    return "current" if block + "\n" == render_block(render_agents_lines(), style=HTML_COMMENT) else "stale"


def warn_if_agents_md_block_stale(project_root: Path) -> None:
    """One non-fatal line when ``AGENTS.md`` lacks this version's section."""
    state = agents_md_block_state(project_root)
    if state == "current":
        return
    what = ("has no specy-road section" if state == "missing"
            else f"has a specy-road section that differs from what specy-road {__version__} writes")
    print(
        f"agents: warning — {AGENTS_MD} {what}, so agents here miss the current coordination "
        "rules. Run: specy-road refresh-stubs (it needs no stub pack and touches only managed blocks)",
        file=sys.stderr,
    )


_LOAD_ORDER_ITEM = re.compile(r"^\d+\.\s+`([^`]+)`")


def load_order_paths(lines: list[str]) -> list[str]:
    """The files a block's ``### Load order`` names, in order.

    Placeholders (``planning/<id>_…``) and the digest are left out: one names no
    file, and ``digest --check`` already reports the other.
    """
    paths: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("#"):
            in_section = line.strip() == "### Load order"
            continue
        m = _LOAD_ORDER_ITEM.match(line) if in_section else None
        if m and "<" not in m.group(1) and m.group(1) != DIGEST:
            paths.append(m.group(1))
    return paths


def warn_missing_load_order_paths(project_root: Path) -> None:
    """One non-fatal line naming the files the ``AGENTS.md`` load order sends agents to that do not exist."""
    try:
        _before, block, _after = _split((project_root / AGENTS_MD).read_text(encoding="utf-8"), HTML_COMMENT)
    except (OSError, UnicodeDecodeError):
        return
    if block is None:
        return
    missing = [rel for rel in load_order_paths(block.splitlines()) if not (project_root / rel).exists()]
    if missing:
        print(
            f"agents: warning — the {AGENTS_MD} load order names {', '.join(missing)}, which "
            f"{'does' if len(missing) == 1 else 'do'} not exist here. Run: specy-road upgrade "
            "(it copies the docs specy-road ships); create the others.",
            file=sys.stderr,
        )


def apply_agents_and_report(project_root: Path, written: list[str], *, dry_run: bool = False,
                            prefix: str = "") -> None:
    """``prefix`` is the project's path under the git root, so a nested layout reports ``sr/AGENTS.md``."""
    outcome = apply_agents_md_block(project_root, dry_run=dry_run)
    if outcome != UNCHANGED:
        written.append(f"{prefix}{AGENTS_MD} ({outcome})")
