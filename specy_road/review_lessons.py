"""Project review lessons in ``constraints/review-lessons.md`` (M11.78).

A defect class that escaped one review is written down once, as a one-line
rule, and every later reviewer prompt carries it under **Project review
lessons**. The file is Markdown so a human can edit it by hand: each top-level
bullet under ``## Lessons`` is one entry, with optional ``Example:`` and
``From:`` sub-bullets. Lines elsewhere in the file are prose, not entries.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from specy_road.init_project import project_template_root
from specy_road.text_sections import LEVEL2_RE, find_section, normalize_heading

LESSONS_REL = Path("constraints") / "review-lessons.md"
_SECTION = "lessons"
_ENTRY = re.compile(r"^[-*+]\s+(\S.*)$")
_SUB = re.compile(r"^\s+[-*+]\s+(example|from)\s*:\s*(\S.*)$", re.IGNORECASE)
_NODE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def lessons_path(root: Path) -> Path:
    return root / LESSONS_REL


def bundled_header() -> str:
    """The file ``init project`` writes; ``lessons add`` starts a missing file from it."""
    return (project_template_root() / LESSONS_REL).read_text(encoding="utf-8")


def parse_lessons(text: str) -> list[dict[str, Any]]:
    """Entries under ``## Lessons``, in file order: ``{rule, example?, from?}``."""
    out: list[dict[str, Any]] = []
    for line in (find_section(text, {_SECTION}) or "").splitlines():
        if m := _ENTRY.match(line):
            out.append({"rule": m.group(1).strip()})
        elif out and (m := _SUB.match(line)):
            out[-1][m.group(1).lower()] = m.group(2).strip()
    return out


def read_lessons(path: Path) -> list[dict[str, Any]]:
    """Entries in ``path``; a missing file has none. An unreadable one raises ``OSError``."""
    if not path.is_file():
        return []
    try:
        return parse_lessons(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as e:
        raise OSError(f"{path} is not UTF-8: {e}") from e


def format_lesson(e: dict[str, Any]) -> str:
    lines = [f"- {e['rule']}"]
    if e.get("example"):
        lines.append(f"  - Example: {e['example']}")
    if e.get("from"):
        lines.append(f"  - From: {e['from']}")
    return "\n".join(lines)


def _one_line(name: str, value: str | None) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise ValueError(f"{name} must be non-empty")
    return text


def _insert_entry(text: str, block: str) -> str:
    """``text`` with ``block`` at the end of its ``## Lessons`` section (a new one at the end if none)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if (m := LEVEL2_RE.match(ln)) and normalize_heading(m.group("title")) == _SECTION), None)
    if start is None:
        body = text.rstrip("\n")
        return f"{body}\n\n## Lessons\n\n{block}\n" if body else f"## Lessons\n\n{block}\n"
    end = next((i for i in range(start + 1, len(lines)) if LEVEL2_RE.match(lines[i])), len(lines))
    last = end   # just after the section's last non-blank line
    while last > start + 1 and not lines[last - 1].strip():
        last -= 1
    gap = [""] if last == start + 1 else []   # a blank line between the heading and the first entry
    rest = ["", *lines[end:]] if end < len(lines) else []
    return "\n".join(lines[:last] + gap + block.splitlines() + rest) + "\n"


def add_lesson(root: Path, *, rule: str, example: str | None = None,
               from_node: str | None = None) -> dict[str, Any]:
    """Append one entry; a missing file is created from the bundled header first."""
    entry: dict[str, Any] = {"rule": _one_line("--rule", rule)}
    if example is not None:
        entry["example"] = _one_line("--example", example)
    if from_node is not None:
        node = from_node.strip()
        if not _NODE_ID.fullmatch(node):
            raise ValueError(f"--from must be a node id such as M1.2, got {from_node!r}")
        entry["from"] = node
    path = lessons_path(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else bundled_header()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_insert_entry(text, format_lesson(entry)), encoding="utf-8")
    return entry


def reviewer_lesson_lines(root: Path) -> list[str]:
    """The reviewer prompt's ``## Project review lessons`` section; none when the file has no entries."""
    rel = LESSONS_REL.as_posix()
    head = ["## Project review lessons", ""]
    try:
        entries = read_lessons(lessons_path(root))
    except OSError as e:
        return head + [f"`{rel}` could not be read ({e}); ask the coordinator for its lessons before approving.", ""]
    if not entries:
        return []
    return head + [
        f"Defect classes that escaped an earlier review in this project (`{rel}`). Check the diff for each "
        "one; a match belongs under `required_changes`.",
        "",
        *(format_lesson(e) for e in entries),
        "",
    ]
