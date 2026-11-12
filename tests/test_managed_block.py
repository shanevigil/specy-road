"""The marked-block editor for files specy-road does not own.

`.gitignore`, `.cursorindexingignore`, `CLAUDE.md` and `AGENTS.md` belong to the
consumer. The contract is absolute: everything outside the markers survives
untouched, and applying the same block twice changes nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from specy_road.agent_guide_block import apply_agent_guide_block
from specy_road.agent_ignores import apply_agent_ignores
from specy_road.agents_md_block import apply_agents_md_block
from specy_road.managed_block import (
    CREATED,
    FAILED,
    HASH,
    HTML_COMMENT,
    MARKER_END,
    MARKER_START,
    UNCHANGED,
    UPDATED,
    MarkerStyle,
    apply_managed_block,
    render_block,
)

USER_CONTENT = "# my own rules\nnode_modules/\n.env\n"


def test_a_missing_file_is_created_with_just_the_block(tmp_path: Path) -> None:
    path = tmp_path / ".cursorindexingignore"

    assert apply_managed_block(path, ["roadmap/archive/"]) == CREATED
    text = path.read_text(encoding="utf-8")

    assert text.startswith(MARKER_START)
    assert "roadmap/archive/" in text
    assert text.rstrip().endswith(MARKER_END)


def test_existing_content_is_preserved_when_the_block_is_added(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_text(USER_CONTENT, encoding="utf-8")

    assert apply_managed_block(path, [".specyrd/cache/"]) == UPDATED
    text = path.read_text(encoding="utf-8")

    assert text.startswith(USER_CONTENT)
    assert ".specyrd/cache/" in text


#: The three block kinds, each through its own public writer: ``(file, marker style, write it)``.
BLOCK_KINDS = [
    pytest.param(
        ".gitignore", HASH, lambda root: apply_agent_ignores(root)[".gitignore"], id="ignore"
    ),
    pytest.param("CLAUDE.md", HTML_COMMENT, apply_agent_guide_block, id="claude-guide"),
    pytest.param("AGENTS.md", HTML_COMMENT, apply_agents_md_block, id="agents-stub"),
]
BEFORE = "# Our own notes\n\nkeep-before/\n\n"
AFTER = "## Added after the block\nkeep-after/\n"


@pytest.mark.parametrize(("name", "style", "write"), BLOCK_KINDS)
def test_replacing_a_block_twice_gives_the_same_file_and_keeps_the_rest(
    tmp_path: Path, name: str, style: MarkerStyle, write: Callable[[Path], str]
) -> None:
    """A stale block is replaced once; the second run is a no-op; outside text is byte-identical."""
    path = tmp_path / name
    path.write_text(BEFORE + render_block(["stale/"], style=style) + "\n" + AFTER, encoding="utf-8")

    assert write(tmp_path) == UPDATED
    first = path.read_text(encoding="utf-8")
    assert write(tmp_path) == UNCHANGED
    assert path.read_text(encoding="utf-8") == first

    assert first.startswith(BEFORE + style.start)
    assert first.endswith(style.end + "\n\n" + AFTER)
    assert first.count(style.start) == 1 and first.count(style.end) == 1
    assert "stale/" not in first


def test_a_changed_recommendation_replaces_the_old_one(tmp_path: Path) -> None:
    """Rewriting in place is why a dropped entry actually disappears."""
    path = tmp_path / ".gitignore"
    apply_managed_block(path, ["old-rule/"])

    assert apply_managed_block(path, ["new-rule/"]) == UPDATED
    text = path.read_text(encoding="utf-8")

    assert "new-rule/" in text and "old-rule/" not in text


def test_content_after_the_block_survives_a_rewrite(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    apply_managed_block(path, ["a/"])
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# added later by a human\ndist/\n",
        encoding="utf-8",
    )

    apply_managed_block(path, ["b/"])
    text = path.read_text(encoding="utf-8")

    assert "# added later by a human" in text and "dist/" in text
    assert "b/" in text and "a/" not in text


def test_content_before_and_after_both_survive(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_text(USER_CONTENT, encoding="utf-8")
    apply_managed_block(path, ["a/"])
    path.write_text(path.read_text(encoding="utf-8") + "trailing/\n", encoding="utf-8")

    apply_managed_block(path, ["b/"])
    text = path.read_text(encoding="utf-8")

    assert text.startswith(USER_CONTENT)
    assert "trailing/" in text


def test_a_truncated_block_is_repaired(tmp_path: Path) -> None:
    """A half-edited file must not accumulate a second broken block."""
    path = tmp_path / ".gitignore"
    path.write_text(f"{USER_CONTENT}{MARKER_START}\nhalf-written/\n", encoding="utf-8")

    assert apply_managed_block(path, ["good/"]) == UPDATED
    text = path.read_text(encoding="utf-8")

    assert text.count(MARKER_START) == 1
    assert text.count(MARKER_END) == 1
    assert "half-written/" not in text
    assert text.startswith(USER_CONTENT)


def test_the_note_is_rendered_as_comments_without_trailing_space() -> None:
    block = render_block(["x/"], note="why this exists\n\nsecond paragraph")

    assert "# why this exists" in block
    assert "\n#\n" in block  # a blank note line, not "# "
    assert not any(line.endswith(" ") for line in block.splitlines())


def test_an_unwritable_path_reports_failure_rather_than_raising(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "afile"
    blocked.write_text("not a directory", encoding="utf-8")

    assert apply_managed_block(blocked / "nested" / ".gitignore", ["x/"]) == FAILED
