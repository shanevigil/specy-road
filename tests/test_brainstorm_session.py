"""The brainstorm session file: round-trip, id allocation, and triage guards.

The session is the contract between the two modes and between the two front
ends (CLI and PM GUI), so it is validated in code rather than by a JSON schema.
These tests are that validation's only enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    idea_from_dict,
    list_slugs,
    prompt_path,
    read_session,
    resolve_slug,
    session_path,
    set_status,
    slugify,
    write_session,
)


def _session(**kw) -> BrainstormSession:
    base = {"slug": "payments", "topic": "How do we expand payments?"}
    return BrainstormSession(**{**base, **kw})


def test_round_trip_preserves_every_idea_field(tmp_path: Path) -> None:
    s = _session(under="M1")
    add_idea(
        s,
        title="Stored payment vault",
        rationale="Cuts PCI scope",
        kind="capability",
        effort="M",
        evidence=["https://example.com/a", "https://example.com/b"],
    )
    write_session(tmp_path, s)

    back = read_session(tmp_path, "payments")

    assert back.topic == "How do we expand payments?"
    assert back.under == "M1"
    assert back.mode == "brainstorm"
    idea = back.ideas[0]
    assert idea.title == "Stored payment vault"
    assert idea.rationale == "Cuts PCI scope"
    assert idea.kind == "capability"
    assert idea.effort == "M"
    assert idea.evidence == ["https://example.com/a", "https://example.com/b"]
    assert idea.status == "proposed"
    assert idea.recommendation is None
    assert idea.promoted_node_key is None


def test_ids_are_never_reused_after_a_deletion(tmp_path: Path) -> None:
    """Ids are cited in prompts and in promoted sheets, so they must be stable."""
    s = _session()
    add_idea(s, title="One")
    add_idea(s, title="Two")
    add_idea(s, title="Three")
    del s.ideas[1]

    assert s.next_idea_id() == "B4"
    assert add_idea(s, title="Four").id == "B4"


def test_ideas_are_addressable_case_insensitively(tmp_path: Path) -> None:
    s = _session()
    add_idea(s, title="One")

    assert s.by_id("b1").title == "One"


def test_unknown_idea_names_the_session(tmp_path: Path) -> None:
    s = _session()

    with pytest.raises(BrainstormError, match="no idea 'B9' in session 'payments'"):
        s.by_id("B9")


def test_a_promoted_idea_cannot_be_retriaged(tmp_path: Path) -> None:
    """It is a roadmap node now; flipping the idea would say nothing true."""
    s = _session()
    idea = add_idea(s, title="One")
    idea.status = "accepted"
    idea.promoted_node_key = "abc"

    with pytest.raises(BrainstormError, match="already on the roadmap"):
        set_status(s, "B1", "rejected")


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("kind", "nonsense", "kind"),
        ("status", "maybe", "status"),
        ("recommendation", "great", "recommendation"),
    ],
)
def test_enumerated_fields_are_rejected_when_unknown(
    field: str, value: str, message: str
) -> None:
    raw = {"id": "B1", "title": "One", field: value}

    with pytest.raises(BrainstormError, match=message):
        idea_from_dict(raw)


def test_an_idea_without_a_title_is_rejected() -> None:
    with pytest.raises(BrainstormError, match="missing a title"):
        idea_from_dict({"id": "B1"})


def test_a_future_version_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    write_session(tmp_path, _session())
    path = session_path(tmp_path, "payments")
    path.write_text(path.read_text(encoding="utf-8").replace("version: 1", "version: 2"))

    with pytest.raises(BrainstormError, match="unsupported version"):
        read_session(tmp_path, "payments")


def test_duplicate_ids_are_refused_on_read(tmp_path: Path) -> None:
    write_session(tmp_path, _session())
    session_path(tmp_path, "payments").write_text(
        "version: 1\nslug: payments\nmode: brainstorm\nideas:\n"
        "- id: B1\n  title: One\n- id: B1\n  title: Two\n",
        encoding="utf-8",
    )

    with pytest.raises(BrainstormError, match="duplicate idea id"):
        read_session(tmp_path, "payments")


def test_the_only_open_session_needs_no_slug(tmp_path: Path) -> None:
    write_session(tmp_path, _session())

    assert resolve_slug(tmp_path, None) == "payments"


def test_several_open_sessions_refuse_to_be_guessed(tmp_path: Path) -> None:
    write_session(tmp_path, _session())
    write_session(tmp_path, _session(slug="billing"))

    with pytest.raises(BrainstormError, match="pass --slug"):
        resolve_slug(tmp_path, None)
    assert list_slugs(tmp_path) == ["billing", "payments"]


def test_no_sessions_points_at_start(tmp_path: Path) -> None:
    with pytest.raises(BrainstormError, match="brainstorm start"):
        resolve_slug(tmp_path, None)


def test_reading_a_missing_session_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(BrainstormError, match="brainstorm-ghost.yaml"):
        read_session(tmp_path, "ghost")


def test_session_and_prompt_live_in_work(tmp_path: Path) -> None:
    """The prompt is regenerated and gitignored; the session is tracked."""
    assert session_path(tmp_path, "x") == tmp_path / "work" / "brainstorm-x.yaml"
    assert prompt_path(tmp_path, "x") == tmp_path / "work" / "brainstorm-x-prompt.md"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("How do we expand payments?", "how-do-we-expand-payments"),
        ("  Mixed CASE  ", "mixed-case"),
        ("???", ""),
    ],
)
def test_slugify_matches_codename_rules(text: str, expected: str) -> None:
    assert slugify(text) == expected


@pytest.mark.parametrize(
    "slug",
    [
        "../../../../tmp/escaped",
        "x/../../roadmap/registry",
        "a/b",
        "..",
        "Has Spaces",
        "trailing-",
        "",
    ],
)
def test_a_slug_can_never_name_a_file_outside_work(slug: str, tmp_path: Path) -> None:
    """A slug is interpolated into a filename and reaches us from `--slug` and
    from a GUI request body, so anything but a bare name is a write primitive:
    `x/../../roadmap/registry` lands on the tracked registry."""
    with pytest.raises(BrainstormError):
        session_path(tmp_path, slug)
    with pytest.raises(BrainstormError):
        prompt_path(tmp_path, slug)
    with pytest.raises(BrainstormError):
        resolve_slug(tmp_path, slug)


def test_an_ordinary_slug_still_lands_in_work(tmp_path: Path) -> None:
    assert session_path(tmp_path, "how-do-we-expand-payments").parent == (
        tmp_path / "work"
    )
