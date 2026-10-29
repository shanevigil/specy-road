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

``validate`` also meters what those files cost: the lines and bytes each harness
injects into every session, against the limit its vendor documents.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.digest import DEFAULT_OUTPUT as DIGEST
from specy_road.doc_links import link_toolkit_docs
from specy_road.managed_block import (
    HTML_COMMENT,
    UNCHANGED,
    _split,
    apply_managed_block,
    render_block,
)
from specy_road.runtime_paths import git_root

AGENTS_MD = "AGENTS.md"

#: Codex concatenates the AGENTS.md files from the git root down to the working directory
#: and truncates them at ``project_doc_max_bytes``, 32 KiB by default:
#: https://developers.openai.com/codex/guides/agents-md
CODEX_PROJECT_DOC_MAX_BYTES = 32 * 1024
#: "target under 200 lines per CLAUDE.md file": https://code.claude.com/docs/en/memory
CLAUDE_MD_TARGET_LINES = 200
_TEMPLATE = Path(__file__).resolve().parent / "templates" / "specyrd" / "agents-md-block.md"
_H1 = "# Agents — load order\n"


def render_agents_lines() -> list[str]:
    text = link_toolkit_docs(_TEMPLATE.read_text(encoding="utf-8").replace("{{SPECYRD_VERSION}}", __version__))
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


@dataclass(frozen=True)
class InjectedFile:
    """One instruction file a harness injects into every session, and its specy-road section."""

    rel: str
    lines: int
    size: int
    block_lines: int
    block_size: int

    def describe(self) -> str:
        own = f" (specy-road section {self.block_lines} lines, {self.block_size:,} bytes)" if self.block_size else ""
        return f"{self.rel} {self.lines} lines, {self.size:,} bytes{own}"


def _measure(path: Path, rel: str) -> InjectedFile:
    data = path.read_bytes()
    _before, block, _after = _split(data.decode("utf-8", errors="replace"), HTML_COMMENT)
    own = (block or "").encode("utf-8")
    return InjectedFile(rel, len(data.splitlines()), len(data), len(own.splitlines()), len(own))


def injected_context(project_root: Path) -> tuple[list[InjectedFile], list[InjectedFile]]:
    """``(Codex, Claude Code)``: the files each injects into a session started in ``project_root``.

    Both walk from the git root down to the working directory. Claude Code reads
    ``AGENTS.md`` only when no ``CLAUDE.md`` is on that path.
    """
    project_root = project_root.resolve()
    top = git_root(project_root) or project_root
    dirs = [d for d in reversed((project_root, *project_root.parents)) if d.is_relative_to(top)]

    def found(name: str) -> list[InjectedFile]:
        return [_measure(d / name, (d / name).relative_to(top).as_posix()) for d in dirs if (d / name).is_file()]

    agents = found(AGENTS_MD)
    return agents, found(AGENT_GUIDE) or agents


def print_injected_context(project_root: Path) -> None:
    """One line per harness: what every session pays, against the documented limit."""
    codex, claude = injected_context(project_root)
    if codex:
        print(f"context: Codex reads {'; '.join(f.describe() for f in codex)} — "
              f"{sum(f.size for f in codex):,} of its {CODEX_PROJECT_DOC_MAX_BYTES:,}-byte "
              "project_doc_max_bytes budget")
    if claude:
        print(f"context: Claude Code reads {'; '.join(f.describe() for f in claude)} — "
              f"target under {CLAUDE_MD_TARGET_LINES} lines per file")


def warn_if_context_over_limits(project_root: Path) -> None:
    """A non-fatal line for each documented limit the injected files exceed."""
    codex, claude = injected_context(project_root)
    total = sum(f.size for f in codex)
    if total > CODEX_PROJECT_DOC_MAX_BYTES:
        print(
            f"context: warning — {', '.join(f.rel for f in codex)} total {total:,} bytes, and Codex "
            f"truncates AGENTS.md instructions at {CODEX_PROJECT_DOC_MAX_BYTES:,} (project_doc_max_bytes), "
            "so its sessions here never see the rest. Shorten them, or raise project_doc_max_bytes "
            "in ~/.codex/config.toml.",
            file=sys.stderr,
        )
    for f in claude:
        if f.lines > CLAUDE_MD_TARGET_LINES:
            print(
                f"context: warning — {f.rel} is {f.lines} lines; Claude Code's documented target is under "
                f"{CLAUDE_MD_TARGET_LINES} per file, because every session pays for the rest in context "
                "and adherence. Move what only some tasks need into a doc it links to.",
                file=sys.stderr,
            )
