"""The brainstorm session file: round-trip, id allocation, and triage guards.

The session is the contract between the two modes and between the two front
ends (CLI and PM GUI), so it is validated in code rather than by a JSON schema.
These tests are that validation's only enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.brainstorm_session import (
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
from tests.support.review import make_review_repo
import io
from specy_road.bundled_scripts import brainstorm_cli
from tests.support.same.session_9311e77aa0c8 import session


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
    path.write_text(path.read_text(encoding="utf-8").replace("version: 2", "version: 3"))

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



def test_a_session_file_whose_slug_disagrees_is_refused(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    write_session(repo, BrainstormSession(slug="b", topic="t"))
    (repo / "work" / "brainstorm-a.yaml").write_text((repo / "work" / "brainstorm-b.yaml").read_text())
    with pytest.raises(Exception, match="says slug 'b'"):
        read_session(repo, "a")





def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    import contextlib

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main([*args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()



def _start(repo: Path) -> None:
    assert _cli(repo, "start", "--topic", "How do we expand payments?")[0] == 0





def test_triage_checks_every_id_before_printing_or_saving(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-idea", "--title", "Two")
    code, out, err = _cli(repo, "accept", "B1", "B9")
    assert code == 1 and not out.strip() and "B9" in err
    assert session(repo).by_id("B1").status == "proposed"
    code, out, err = _cli(repo, "park", "B1", "B9", "--reason", "later")
    assert code == 1 and not out.strip()
    assert session(repo).by_id("B1").status == "proposed"



def test_triage_prints_nothing_when_a_batch_holds_a_promoted_idea(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-idea", "--title", "Two")
    assert _cli(repo, "realize", "B2", "--node", "M1")[0] == 0
    before = session(repo)
    assert before.by_id("B1").status == "proposed" and before.by_id("B2").promoted_node_key
    code, out, err = _cli(repo, "accept", "B1", "B2")
    assert code == 1 and not out.strip() and "already on the roadmap" in err
    assert session(repo).by_id("B1").status == "proposed"
    code, out, err = _cli(repo, "park", "B1", "B2", "--reason", "later")
    assert code == 1 and not out.strip()
    assert session(repo).by_id("B1").status == "proposed"
    code, out, err = _cli(repo, "reject", "B1", "B2", "--reason", "no")
    assert code == 1 and not out.strip()
    assert session(repo).by_id("B1").status == "proposed"



def test_realize_records_a_hand_built_node(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "Hand built")
    code, out, err = _cli(repo, "realize", "B1", "--node", "M1")
    assert code == 0, err
    idea = session(repo).by_id("B1")
    assert idea.promoted_node_key
    assert "M1" in out and idea.promoted_node_key[:8] in out
    code, _, err = _cli(repo, "realize", "B1", "--node", "M1.1")
    assert code == 1 and "already on the roadmap" in err



def test_revise_append_why_adds_to_verdict_why(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "revise", "B1", "--why", "first line")
    _cli(repo, "revise", "B1", "--append-why", "second line")
    assert session(repo).by_id("B1").verdict_why == "first line\nsecond line"



def test_list_summary_prints_status_and_recommendation_counts(repo: Path) -> None:
    _start(repo)
    _cli(repo, "add-idea", "--title", "One")
    _cli(repo, "add-idea", "--title", "Two")
    _cli(repo, "revise", "B1", "--recommendation", "strong")
    _cli(repo, "accept", "B1")
    _cli(repo, "reject", "B2", "--reason", "no")
    _, out, _ = _cli(repo, "list", "--summary")
    assert "status:" in out and "  proposed: 0" in out and "  accepted: 1" in out and "  rejected: 1" in out
    assert "recommendation:" in out and "  strong: 1" in out and "  -: 1" in out
