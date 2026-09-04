"""The marked-block editor for files specy-road does not own.

`.gitignore` and `.cursorindexingignore` belong to the consumer. The contract is
absolute: everything outside the markers survives untouched, and applying the
same block twice changes nothing.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.managed_block import (
    CREATED,
    FAILED,
    MARKER_END,
    MARKER_START,
    UNCHANGED,
    UPDATED,
    apply_managed_block,
    remove_managed_block,
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


def test_applying_the_same_block_twice_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_text(USER_CONTENT, encoding="utf-8")
    apply_managed_block(path, [".specyrd/cache/"])
    first = path.read_text(encoding="utf-8")

    assert apply_managed_block(path, [".specyrd/cache/"]) == UNCHANGED
    assert path.read_text(encoding="utf-8") == first


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


def test_removing_the_block_leaves_the_rest_alone(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_text(USER_CONTENT, encoding="utf-8")
    apply_managed_block(path, ["a/"])

    assert remove_managed_block(path) == UPDATED
    assert path.read_text(encoding="utf-8").startswith("# my own rules")
    assert MARKER_START not in path.read_text(encoding="utf-8")


def test_removing_when_there_is_no_block_is_a_no_op(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    path.write_text(USER_CONTENT, encoding="utf-8")

    assert remove_managed_block(path) == UNCHANGED
    assert path.read_text(encoding="utf-8") == USER_CONTENT


def test_an_unwritable_path_reports_failure_rather_than_raising(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "afile"
    blocked.write_text("not a directory", encoding="utf-8")

    assert apply_managed_block(blocked / "nested" / ".gitignore", ["x/"]) == FAILED
