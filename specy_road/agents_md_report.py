"""The ``agents_block`` setting, the notice when ``.specyrd/AGENTS.md`` first arrives, and per-harness totals.

Split from :mod:`specy_road.agents_md_block` (file-limits). Adopters reported an
18-line ``AGENTS.md`` section pushing a project file over its cap, their own
pickup rules silently duplicating the new rules file (one copy went stale), and a
Claude Code context line with no total that hid a file read twice.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from specy_road import __version__
from specy_road.harness_instruction_files import AGENTS_MD, RULES_MD, _imports_in, claude_paths, claude_rules
from specy_road.managed_block import HTML_COMMENT, _split
from specy_road.runtime_paths import SPECYRD_MANIFEST, git_root
from specy_road.text_sections import normalize_heading

#: ``agents_block`` in ``.specyrd/manifest.json``: ``full`` (default) or ``minimal``.
MINIMAL = "minimal"
_MINIMAL_LINE = (
    "Written by specy-road {v} (minimum {v}); `specy-road upgrade` rewrites only this section. "
    "**Read `.specyrd/AGENTS.md` before any roadmap, registry or git work:** it holds specy-road's rules. "
    "Then read `.specyrd/AGENTS.team.md` and `.specyrd/AGENTS.local.md` when present; "
    "they add to the rules, never relax them."
)
#: An ATX heading, level 2-6, indented up to three spaces, with an optional closing run of ``#``.
_ATX = re.compile(r"^ {0,3}#{2,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
#: A code fence, indented up to three spaces: a run of 3+ backticks or tildes, then the info string.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_COMMENT = re.compile(r"<!--.*?-->")

def agents_block_mode(project_root: Path) -> str:
    """``"minimal"`` when the git root's manifest says so, else ``"full"``."""
    path = (git_root(project_root) or project_root) / SPECYRD_MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "full"
    return MINIMAL if isinstance(data, dict) and data.get("agents_block") == MINIMAL else "full"


def minimal_lines() -> list[str]:
    """The pointer-only ``AGENTS.md`` section: one line, three with its markers."""
    return [_MINIMAL_LINE.format(v=__version__)]


def _headings(text: str) -> list[tuple[int, str]]:
    """``(line number, heading text)`` for each ``##``-or-deeper heading: a hint, so the input class is bounded.

    Recognised: ATX headings indented 0-3 spaces. Skipped: fenced code (a backtick or tilde fence indented
    0-3 spaces, closed by the same character at least as long) and HTML comments, on one line or several.
    Out of scope: setext headings, other HTML blocks, indented code, list or blockquote nesting and every
    other CommonMark construct.
    """
    found: list[tuple[int, str]] = []
    fence = ""        # the open fence's run, e.g. "````"
    comment = False   # inside a ``<!--`` that has not closed yet
    for n, line in enumerate(text.splitlines(), 1):
        if comment:
            comment = "-->" not in line
            continue
        if fence:
            m = _FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = ""
            continue
        if (m := _FENCE.match(line)) and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = m.group(1)   # a backtick in a backtick fence's info string makes it a code span instead
            continue
        line, opener, _rest = _COMMENT.sub("", line).partition("<!--")   # what precedes an unclosed comment still counts
        comment = bool(opener)
        if m := _ATX.match(line):
            found.append((n, m.group(1)))
    return found

def print_rules_overlap(project_root: Path, rules: str, prefix: str = "") -> None:
    """Before :data:`RULES_MD` is first created: its headings, and the project's own ``AGENTS.md`` headings it repeats."""
    new = _headings(rules)
    print(f"rules: {prefix}{RULES_MD} is new; its headings: {'; '.join(h for _n, h in new)}")
    path = project_root / AGENTS_MD
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        text = ""
    before, block, _after = _split(text, HTML_COMMENT)
    first = before.count("\n") + 1   # the managed section's lines, which are specy-road's own
    ours = range(first, first + block.count("\n") + 1) if block is not None else range(0)
    keys = {normalize_heading(h) for _n, h in new}
    dupes = [(n, h) for n, h in _headings(text) if normalize_heading(h) in keys and n not in ours]
    for n, heading in dupes:
        print(f"rules: {prefix}{AGENTS_MD}:{n} \"{heading}\" (outside the specy-road section) "
              f"matches a heading in {prefix}{RULES_MD}")
    if dupes:
        print(f"rules: compare these with {prefix}{RULES_MD} and drop the copy that is stale")


def total(files: list) -> str:
    """The end of a harness's context line: the lines and bytes of its ``InjectedFile`` list."""
    return f"total {sum(f.lines for f in files)} lines, {sum(f.size for f in files):,} bytes"


def claude_reread(loaded: list[Path], root: Path, top: Path) -> str:
    """`` (<file> imported twice, counted once)`` for each file in ``loaded`` that Claude Code reaches more than once.

    A file is reached once when Claude Code loads it directly and once per loaded file that ``@``-imports it.
    """
    direct = {p.resolve() for p in (*claude_paths(root), *claude_rules(root, top))}
    reached = Counter(p.resolve() for p in loaded if p.resolve() in direct)
    for importer in loaded:
        reached.update(p.resolve() for p in _imports_in(importer))   # each @ line counts, even twice in one file
    notes = []
    for path in loaded:
        n = reached[path.resolve()]
        if n > 1:
            notes.append(f" ({path.resolve().relative_to(top.resolve()).as_posix()} imported {'twice' if n == 2 else f'{n} times'}, "
                         "counted once)")
    return "".join(notes)
