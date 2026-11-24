"""The ``##`` section parser shared by the brief and the search index.

These sheets are hand-written, so the parser has to be forgiving about heading
shape without ever silently swallowing a section's content.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.text_sections import (
    find_section,
    normalize_heading,
    read_text_safely,
    split_sections,
)

SHEET = """## Intent

Ship a retry queue.

## Approach

Exponential backoff.
Capped at 30s.

## Tasks / checklist

- [ ] write it
"""


def headings(text: str) -> list[str | None]:
    return [h for h, _ in split_sections(text)]


def test_sections_come_back_in_document_order() -> None:
    assert headings(SHEET) == ["Intent", "Approach", "Tasks / checklist"]


def test_a_body_keeps_its_internal_structure() -> None:
    body = dict(split_sections(SHEET))["Approach"]
    assert body == "Exponential backoff.\nCapped at 30s."


def test_blank_edges_are_trimmed_but_inner_blanks_survive() -> None:
    text = "## A\n\n\nfirst\n\nsecond\n\n\n"
    assert dict(split_sections(text))["A"] == "first\n\nsecond"


def test_content_before_the_first_heading_is_a_none_headed_section() -> None:
    text = "Preamble prose.\n\n## Intent\n\nBody.\n"
    sections = split_sections(text)
    assert sections[0] == (None, "Preamble prose.")
    assert sections[1] == ("Intent", "Body.")


def test_a_blank_preamble_is_omitted_entirely() -> None:
    assert headings("\n\n## Intent\n\nBody.\n") == ["Intent"]


def test_deeper_headings_stay_inside_their_parent_section() -> None:
    """`### Tasks (if any)` belongs to the `## Resolution` it sits under."""
    text = "## Resolution\n\nDecided.\n\n### Tasks (if any)\n\n- [ ] one\n"
    sections = split_sections(text)
    assert headings(text) == ["Resolution"]
    assert "### Tasks (if any)" in sections[0][1]


def test_a_heading_with_no_body_is_kept_with_an_empty_body() -> None:
    """Callers decide whether an empty section is interesting; the parser reports it."""
    assert split_sections("## Empty\n\n## Next\n\nx\n")[0] == ("Empty", "")


def test_a_document_with_no_headings_is_all_preamble() -> None:
    assert split_sections("just prose\n") == [(None, "just prose")]


def test_empty_input_yields_nothing() -> None:
    assert split_sections("") == []


def test_heading_normalisation_folds_case_whitespace_and_trailing_colon() -> None:
    assert normalize_heading("  Why   This  Gate Exists : ") == "why this gate exists"
    assert normalize_heading("INTENT:") == "intent"


def test_find_section_matches_case_insensitively_and_through_a_colon() -> None:
    assert find_section("## intent:\n\nBody.\n", {"intent"}) == "Body."


def test_find_section_returns_the_first_match() -> None:
    text = "## Intent\n\nFirst.\n\n## Approach\n\nx\n\n## Intent\n\nSecond.\n"
    assert find_section(text, {"intent"}) == "First."


def test_find_section_is_none_when_absent() -> None:
    assert find_section(SHEET, {"resolution"}) is None


def test_find_section_treats_an_empty_section_as_absent() -> None:
    """An empty block carries no more than a missing one; callers render one fallback."""
    assert find_section("## Intent\n\n## Approach\n\nx\n", {"intent"}) is None


def test_find_section_with_no_wanted_headings_is_none() -> None:
    assert find_section(SHEET, set()) is None


def test_a_none_heading_preamble_never_matches() -> None:
    assert find_section("stray text\n", {"intent"}) is None


def test_read_text_safely_reports_a_missing_file(tmp_path: Path) -> None:
    assert read_text_safely(tmp_path / "nope.md") == ("", False)


def test_read_text_safely_reports_a_directory_rather_than_raising(tmp_path: Path) -> None:
    assert read_text_safely(tmp_path) == ("", False)


def test_read_text_safely_survives_undecodable_bytes(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe\x00 not utf-8")
    assert read_text_safely(bad) == ("", False)


def test_read_text_safely_returns_content_for_a_good_file(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text("hello\n", encoding="utf-8")
    assert read_text_safely(good) == ("hello\n", True)
