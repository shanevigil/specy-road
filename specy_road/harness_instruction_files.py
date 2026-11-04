"""Which instruction files each harness reads, for the ``validate`` context meter.

Split from :mod:`specy_road.agents_md_block`, which measures and reports what
these walkers find. Sources: code.claude.com/docs/en/memory,
developers.openai.com/codex/guides/agents-md, the Cursor CLI changelog
(2026.10.22) and the Copilot CLI release notes (1.0.100), as summarised in
docs/design-notes/harness-compatibility-triage.md and the 2026-11-02
harness-capabilities research.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.bundled_scripts.planning_artifacts import split_frontmatter
from specy_road.git_subprocess import git_stdout, git_text

AGENTS_MD = "AGENTS.md"
#: specy-road's own rules, which the ``AGENTS.md`` stub points at and ``CLAUDE.md`` imports;
#: the tracked team addendum; and the personal, gitignored one. All under the project root.
RULES_MD = f".specyrd/{AGENTS_MD}"
TEAM_MD = ".specyrd/AGENTS.team.md"
LOCAL_MD = ".specyrd/AGENTS.local.md"

#: Codex, per directory from the git root down, takes the first non-empty of
#: ``AGENTS.override.md`` then ``AGENTS.md``:
#: https://developers.openai.com/codex/guides/agents-md
CODEX_CANDIDATES = ("AGENTS.override.md", AGENTS_MD)
#: Loaded from the working directory and every ancestor, root-down; within a directory
#: ``CLAUDE.local.md`` follows ``CLAUDE.md``: https://code.claude.com/docs/en/memory
_CLAUDE_CANDIDATES = (AGENT_GUIDE, f".claude/{AGENT_GUIDE}", "CLAUDE.local.md")
#: Read only when no candidate above is present. ``~/.claude/CLAUDE.md`` loads too, but
#: it does not count toward that check: https://code.claude.com/docs/en/memory
_CLAUDE_AGENTS_FALLBACK = (AGENTS_MD, f".claude/{AGENTS_MD}")
#: Every ``.md`` below it, recursively, loads at launch beside ``.claude/CLAUDE.md``
#: unless its frontmatter sets ``paths``: https://code.claude.com/docs/en/memory
_CLAUDE_RULES = ".claude/rules"
#: ``@path`` imports, outside code spans and fenced blocks, resolve relative to the importing
#: file and nest up to four hops: https://code.claude.com/docs/en/memory
_CLAUDE_IMPORT = re.compile(r"(?<!\w)@(~?[\w./-]+)")
_CODE_SPAN = re.compile(r"`[^`]*`")
CLAUDE_IMPORT_HOPS = 4
#: "Claude Code skips a file over 4 MiB and loads none of it."
CLAUDE_MAX_FILE_BYTES = 4 * 1024 * 1024
#: Auto memory: Claude Code loads the first 200 lines or 25 KB of ``MEMORY.md``,
#: whichever comes first. Every worktree of one repository shares the directory.
CLAUDE_MEMORY_LINES = 200
CLAUDE_MEMORY_BYTES = 25_000
#: Cursor reads ``AGENTS.md`` and ``CLAUDE.md`` and its project rules under ``.cursor/rules``;
#: a nested ``AGENTS.md`` applies when the agent edits a file below it (2026.10.22).
#: Copilot reads ``AGENTS.md``, ``.claude/CLAUDE.md``, ``.github/copilot-instructions.md``
#: and the path-specific ``.github/instructions/**/*.instructions.md`` (1.0.100).
#: Neither documents a size limit.
_CURSOR_CANDIDATES = (AGENTS_MD, AGENT_GUIDE)
_CURSOR_RULES = ".cursor/rules"
_COPILOT_CANDIDATES = (AGENTS_MD, f".claude/{AGENT_GUIDE}")
_COPILOT_REPO_FILE = ".github/copilot-instructions.md"
_COPILOT_INSTRUCTIONS = ".github/instructions"


def dirs_from_root(start: Path) -> list[Path]:
    """``start`` and every ancestor, filesystem root first."""
    return list(reversed((start, *start.parents)))


def _present(dirs: list[Path], names: tuple[str, ...]) -> list[Path]:
    return [d / name for d in dirs for name in names if (d / name).is_file()]


def codex_paths(start: Path, top: Path) -> list[Path]:
    """One non-empty file per directory: ``AGENTS.override.md``, else ``AGENTS.md``."""
    chosen = []
    for d in (d for d in dirs_from_root(start) if d.is_relative_to(top)):
        for name in CODEX_CANDIDATES:
            path = d / name
            if path.is_file() and path.stat().st_size > 0:
                chosen.append(path)
                break
    return chosen


def inside(path: Path, top: Path) -> bool:
    """True when ``path`` is inside the git root. Only those files are metered."""
    return path.resolve().is_relative_to(top)


def user_claude_path() -> Path:
    """``~/.claude/CLAUDE.md`` on this machine, whether or not the repo sits under it."""
    return Path.home() / ".claude" / AGENT_GUIDE


def codex_home_file() -> Path | None:
    """The non-empty Codex-home file Codex reads before the project, or None.

    The Codex home is ``CODEX_HOME`` when set, else ``~/.codex``. Same order as a
    project directory: ``AGENTS.override.md``, then ``AGENTS.md``.
    https://developers.openai.com/codex/guides/agents-md
    """
    root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    for name in CODEX_CANDIDATES:
        path = root / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def claude_paths(start: Path) -> list[Path]:
    """Launch-time Claude files, ancestors included.

    A project ``CLAUDE.md``, ``.claude/CLAUDE.md`` or ``CLAUDE.local.md`` suppresses
    the ``AGENTS.md`` fallback. ``~/.claude/CLAUDE.md`` does not.
    """
    dirs = dirs_from_root(start)
    claude = _present(dirs, _CLAUDE_CANDIDATES)
    user = user_claude_path().resolve()
    if any(p.resolve() != user for p in claude):
        return claude
    return _present(dirs, (*_CLAUDE_CANDIDATES, *_CLAUDE_AGENTS_FALLBACK))


def _frontmatter(path: Path) -> dict | None:
    """The file's YAML frontmatter (``{}`` when it has none), or None when it cannot be read."""
    try:
        return split_frontmatter(path.read_text(encoding="utf-8"))[0]
    except (OSError, UnicodeDecodeError):
        return None


def claude_rules(start: Path, top: Path) -> list[Path]:
    """The ``.claude/rules`` files every session loads, from the git root down.

    A rule whose frontmatter sets ``paths`` loads only when Claude works on a matching
    file, so it is not metered.
    """
    dirs = [d for d in dirs_from_root(start) if d.is_relative_to(top)]
    rules = [p for d in dirs for p in sorted((d / _CLAUDE_RULES).rglob("*.md")) if p.is_file()]
    return [p for p in rules if not (_frontmatter(p) or {}).get("paths")]


def _imports_in(path: Path) -> list[Path]:
    """The existing files ``path`` imports with ``@path``, in order."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found: list[Path] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if fenced or line.lstrip().startswith(("```", "~~~")):
            continue
        for m in _CLAUDE_IMPORT.finditer(_CODE_SPAN.sub("", line)):
            target = Path(m.group(1)).expanduser()
            found.append(target if target.is_absolute() else path.parent / target)
    return [p for p in found if p.is_file()]


def claude_imports(files: list[Path]) -> list[Path]:
    """The files ``files`` pull in through ``@path`` imports, nested up to four hops, each once.

    A file too large to load is listed but not followed: Claude Code never reads its imports.
    """
    seen = {p.resolve() for p in files}
    out: list[Path] = []
    frontier = list(files)
    for _hop in range(CLAUDE_IMPORT_HOPS):
        found = []
        for path in (p for f in frontier for p in _imports_in(f)):
            if path.resolve() not in seen:
                seen.add(path.resolve())
                found.append(path)
        out.extend(found)
        frontier = [p for p in found if claude_loads(p)]
    return out


def claude_loads(path: Path) -> bool:
    """False for a file over :data:`CLAUDE_MAX_FILE_BYTES`, which Claude Code skips whole."""
    return path.stat().st_size <= CLAUDE_MAX_FILE_BYTES


def claude_skipped(start: Path, top: Path) -> list[Path]:
    """Every Claude instruction file present here, or imported by one, that is too large for Claude Code to load."""
    found = [p for p in (*claude_paths(start), *claude_rules(start, top), user_claude_path()) if p.is_file()]
    found += claude_imports([p for p in found if claude_loads(p)])
    skipped = {p.resolve(): p for p in found if p.is_file() and not claude_loads(p)}
    return list(skipped.values())


def machine_local_paths(start: Path, top: Path) -> list[Path]:
    """Instruction files outside the git root. Each is a note, never a warning.

    The ancestor walk and the explicit home candidates can name one file; it is listed once.
    A rule linked from inside the repository to a file outside it is one of these too.
    A Claude file too large to load is left out: :func:`claude_skipped` reports it.
    """
    discovered = [*claude_paths(start), *claude_rules(start, top)]
    outside = [p for p in discovered if not inside(p, top) and claude_loads(p)]
    seen = {p.resolve() for p in discovered}
    user = user_claude_path()
    if user.is_file() and user.resolve() not in seen and not inside(user, top) and claude_loads(user):
        outside.append(user)
    codex = codex_home_file()
    if codex is not None and codex.resolve() not in seen and not inside(codex, top):
        outside.append(codex)
    return outside


def _main_worktree(top: Path) -> Path:
    """The repository's main checkout, which names the auto-memory directory every worktree shares."""
    common = git_text(["rev-parse", "--path-format=absolute", "--git-common-dir"], top)
    return Path(common).resolve().parent if common and Path(common).name == ".git" else top


def claude_memory_file(top: Path) -> Path | None:
    """``~/.claude/projects/<repo>/memory/MEMORY.md`` when present, or None.

    ``<repo>`` is the main checkout's absolute path with every non-alphanumeric
    character replaced by ``-``.
    """
    project = re.sub(r"[^A-Za-z0-9]", "-", _main_worktree(top).as_posix())
    path = Path.home() / ".claude" / "projects" / project / "memory" / "MEMORY.md"
    return path if path.is_file() else None


def claude_memory_loaded(path: Path) -> tuple[int, int]:
    """Lines and bytes of the part of ``MEMORY.md`` Claude Code loads."""
    head = b"".join(path.read_bytes().splitlines(keepends=True)[:CLAUDE_MEMORY_LINES])[:CLAUDE_MEMORY_BYTES]
    return len(head.splitlines()), len(head)


def _always_applied(rule: Path) -> bool:
    """A Cursor rule whose YAML frontmatter sets ``alwaysApply`` true: the only kind in every session.

    Rules scoped by glob or description load only when they match, so they are not metered;
    nor is a rule whose frontmatter does not parse.
    """
    return (_frontmatter(rule) or {}).get("alwaysApply") is True


def cursor_paths(start: Path, top: Path) -> list[Path]:
    """``AGENTS.md`` and ``CLAUDE.md`` from the git root down, then the always-applied rules."""
    dirs = [d for d in dirs_from_root(start) if d.is_relative_to(top)]
    rules = [p for d in dirs for p in sorted((d / _CURSOR_RULES).rglob("*"))
             if p.suffix in (".mdc", ".md") and p.is_file() and _always_applied(p)]
    return _present(dirs, _CURSOR_CANDIDATES) + rules


def cursor_nested_agents(start: Path, top: Path) -> list[Path]:
    """``AGENTS.md`` files below the git root and off the path to ``start``.

    Cursor applies one only when the agent edits a file under it, so it is a note, not
    metered. Found with ``git ls-files``, so ignored directories are not searched; outside
    a git repository there are none.
    """
    out = git_stdout(["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--full-name",
                      "--", f":(top,glob)**/{AGENTS_MD}"], top)
    on_path = {d / AGENTS_MD for d in dirs_from_root(start) if d.is_relative_to(top)}
    found = sorted({top / rel for rel in (out or "").split("\0") if rel})
    return [p for p in found if p not in on_path and p.is_file()]


def copilot_paths(start: Path, top: Path) -> list[Path]:
    """``AGENTS.md`` and ``.claude/CLAUDE.md`` in the git root and the working directory,
    then the repo file and the path-specific ``.github/instructions/**/*.instructions.md``."""
    instructions = sorted(p for p in (top / _COPILOT_INSTRUCTIONS).rglob("*.instructions.md") if p.is_file())
    return (_present(list(dict.fromkeys((top, start))), _COPILOT_CANDIDATES)
            + _present([top], (_COPILOT_REPO_FILE,)) + instructions)
