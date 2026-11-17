"""Brainstorm v2: rounds, allocation, shards, evidence, verify, clusters, decisions, promote.

In-process through the CLI entry (no subprocess), on a copy of the dogfood
fixture, plus unit tests on the session fields and the verifier with a stub
fetcher. The prompt contracts the design note names are pinned here: round 1
plans without the roadmap or research, later rounds regenerate against the
pool, shards are independent, converge plays critics and names overlap
relations, triage is the human's, verify asks before it fetches.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts import brainstorm_verify as bv
from specy_road.bundled_scripts.brainstorm_fields import parse_origin, parse_overlap, source_record
from specy_road.brainstorm_prompt import render_shard_prompt
from specy_road.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    idea_from_dict,
    read_session,
    session_path,
    write_session,
)
from tests.support.same.cli_11f0555f0fa9 import cli
from tests.support.same.prompt_26b6cb7fef04 import prompt
from tests.support.same.session_9301503dde8a import session as session_fn
from tests.support.same.start_f653667be42d import start as start_fn
from specy_road.brainstorm_prompt import render_brainstorm_prompt, render_recommend_prompt
from tests.support.same.cli_4bb09fdf3883 import cli as cli_folded
from tests.support.extracted.folded_review_brainstorm import ROOT

SLUG = "how-do-we-expand-payments"












# --- session model ----------------------------------------------------------

def test_v2_fields_round_trip_and_stay_out_of_the_file_when_empty(tmp_path: Path) -> None:
    s = BrainstormSession(slug="p", topic="t", frame={"outcome": "fewer failed payments"},
                          allocation="grid", round=2, profile="technical", panel=3)
    plain = add_idea(s, title="Plain")
    rich = add_idea(s, title="Rich", origin=parse_origin("cursor/composer-2.5/Inversion/2/s1"),
                    cluster_id="C1", sources=[source_record("https://x", quote="q", supports="c", stance="against")],
                    overlap=[parse_overlap("M1.1:prerequisite")], critic={"feasibility": "needs billing"},
                    hypothesis="h", assumptions=["a1"], decision={"status": "parked", "reason": "later"})
    write_session(tmp_path, s)
    text = session_path(tmp_path, "p").read_text()
    assert "version: 2" in text and "panel: 3" in text and "profile: technical" in text
    plain_block = text.split("- id: B1")[1].split("- id: B2")[0]
    for key in ("origin", "cluster_id", "sources", "overlap", "critic", "hypothesis", "assumptions", "decision"):
        assert key not in plain_block
    back = read_session(tmp_path, "p")
    assert back.frame == {"outcome": "fewer failed payments"} and back.round == 2 and back.panel == 3
    b2 = back.by_id("B2")
    assert b2.origin == {"harness": "cursor", "model": "composer-2.5", "lens": "Inversion", "round": "2", "shard": "s1"}
    assert b2.sources[0]["stance"] == "against" and b2.sources[0]["verification"] == "unverified"
    assert b2.overlap == [{"node_id": "M1.1", "relation": "prerequisite"}]
    assert b2.critic == {"feasibility": "needs billing"} and b2.decision["reason"] == "later"
    assert back.by_id("B1").to_dict().keys() == plain.to_dict().keys()


def test_v1_session_files_still_read(tmp_path: Path) -> None:
    session_path(tmp_path, "old").parent.mkdir(parents=True)
    session_path(tmp_path, "old").write_text(
        "version: 1\nslug: old\ntopic: t\nmode: brainstorm\nideas:\n- id: B1\n  title: One\n"
        "  evidence: [https://a]\n  sources:\n  - url: https://a\n    quote: q\n    verification: retrieved\n",
        encoding="utf-8")
    s = read_session(tmp_path, "old")
    assert s.round == 1 and s.profile == "product" and s.ideas[0].evidence == ["https://a"]
    assert s.ideas[0].sources[0]["verification"] == "matched"   # the state's name before the rename
    write_session(tmp_path, s)
    text = session_path(tmp_path, "old").read_text()
    assert "version: 2" in text and "verification: matched" in text and "retrieved" not in text


def test_agentic_runbook_evidence_step_uses_matched_verification_state() -> None:
    from tests.helpers import REPO

    text = (REPO / "docs" / "agentic-sandbox-runbook.md").read_text(encoding="utf-8")
    start = text.index("6. **Evidence and verify.**")
    end = text.index("7. **Triage and promote.**")
    step = text[start:end]
    assert "matched" in step
    assert "retrieved" not in step


@pytest.mark.parametrize("raw, msg", [
    ({"id": "B1", "title": "x", "sources": [{"quote": "no url"}]}, "needs a url"),
    ({"id": "B1", "title": "x", "sources": [{"url": "u", "verification": "sure"}]}, "verification"),
    ({"id": "B1", "title": "x", "overlap": [{"relation": "adjacent"}]}, "node_id"),
    ({"id": "B1", "title": "x", "overlap": [{"node_id": "M1", "relation": "near"}]}, "relation"),
    ({"id": "B1", "title": "x", "status": "parked", "kind": "platform"}, None),
])
def test_v2_field_validation(raw: dict, msg: str | None) -> None:
    if msg is None:
        assert idea_from_dict(raw).status == "parked"
        return
    with pytest.raises(BrainstormError, match=msg):
        idea_from_dict(raw)


@pytest.mark.parametrize("verification_snippet", ["[]", "{}"])
def test_read_session_rejects_non_scalar_source_verification(tmp_path: Path, verification_snippet: str) -> None:
    session_path(tmp_path, "bad").parent.mkdir(parents=True)
    session_path(tmp_path, "bad").write_text(
        "version: 2\nslug: bad\ntopic: t\nmode: brainstorm\nideas:\n"
        f"- id: B1\n  title: One\n  sources:\n  - url: https://a\n    quote: q\n"
        f"    verification: {verification_snippet}\n",
        encoding="utf-8",
    )
    with pytest.raises(BrainstormError, match=r"work/brainstorm-bad\.yaml.*verification"):
        read_session(tmp_path, "bad")


def test_parsers_for_origin_overlap_and_sources() -> None:
    assert parse_origin(None) is None and parse_origin("  ") is None
    assert parse_origin("claude-code/opus") == {"harness": "claude-code", "model": "opus"}
    assert parse_overlap("M2") == {"node_id": "M2", "relation": "adjacent"}
    with pytest.raises(BrainstormError, match="relation"):
        parse_overlap("M2:sideways")
    with pytest.raises(BrainstormError, match="stance"):
        source_record("https://x", stance="maybe")
    assert "quote" not in source_record("https://x")


# --- diverge: round 1, rounds, shards, profiles -----------------------------

def test_round_one_plans_then_generates_without_anchors(repo: Path) -> None:
    code, out, _ = start_fn(repo, "--count", "30")
    assert code == 0 and "round 1 of 2" in out
    text = prompt(repo)
    assert "What would make this topic the wrong thing to brainstorm at all?" in text
    assert "neutralise the frame" in text
    assert "## Step 2 — plan the search before generating" in text
    assert "Diversity operators" in text and "Ordinary personas" in text and "Low typicality" in text
    assert "a competing team's PM" in text
    assert "concept card" in text and "bolder and more different" in text
    assert "at least 30 distinct ideas" in text
    assert "`M0.1`" not in text and "## What already exists" not in text
    # The managed block says "read roadmap-context.md first"; round 1 names what not to open.
    assert "Do not open `roadmap-context.md`, `roadmap.md`, anything under `roadmap/`" in text
    assert "this instruction overrides that rule" in text
    assert "the next round opens them" in text
    start_fn(repo, "--rounds", "1")   # no next round: say what does open them
    text = prompt(repo)
    assert "next round" not in text and "converge (`brainstorm recommend`) shows the roadmap" in text
    assert "--origin" in text and "--hypothesis" in text
    assert "specy-road calls no model and no search API from the CLI" in text


def test_frame_answers_and_allocation_are_recorded_and_shown(repo: Path) -> None:
    start_fn(repo)
    code, out, _ = cli(repo, "frame", "--answer", "outcome=fewer failed payments", "--answer", "served=SMBs",
                        "--allocation", "SCAMPER x segments: 6")
    assert code == 0 and "2 answer(s)" in out and "allocation recorded" in out
    assert session_fn(repo).frame == {"outcome": "fewer failed payments", "served": "SMBs"}
    start_fn(repo)
    text = prompt(repo)
    assert "**outcome:** fewer failed payments" in text and "SCAMPER x segments: 6" in text
    code, _, err = cli(repo, "frame", "--answer", "nonsense")
    assert code == 1 and "KEY=TEXT" in err


def test_next_round_needs_ideas_and_then_regenerates(repo: Path) -> None:
    start_fn(repo)
    code, _, err = cli(repo, "next-round")
    assert code == 1 and "no ideas yet" in err
    cli(repo, "add-idea", "--title", "Stored vault", "--origin", "claude-code/opus/SCAMPER/1")
    cli(repo, "add-idea", "--title", "Pay by link")
    cli(repo, "frame", "--answer", "outcome=fewer failed payments")
    code, out, _ = cli(repo, "next-round", "--count", "15")
    assert code == 0 and "round 2" in out and "2 ideas in the pool" in out
    text = prompt(repo, "r2")
    assert "## The agreed frame" in text and "**outcome:** fewer failed payments" in text
    assert "- B1 Stored vault" in text and "- B2 Pay by link" in text
    assert "at least 15 more" in text and "Unoccupied regions" in text
    assert "Do not research yet" not in text
    assert session_fn(repo).round == 2
    cli(repo, "next-round")
    assert "Round 3" in prompt(repo, "r3") and session_fn(repo).round == 3


def test_technical_profile_swaps_the_lenses_and_default_kind(repo: Path) -> None:
    code, out, _ = start_fn(repo, "--profile", "technical")
    assert code == 0 and "profile technical" in out
    text = prompt(repo)
    assert "Failure modes" in text and "Dependency risk" in text and "SCAMPER" not in text
    assert "--kind refactor" in text
    assert session_fn(repo).profile == "technical"


def test_panel_writes_independent_shards(repo: Path) -> None:
    code, out, _ = start_fn(repo, "--panel", "3", "--count", "30")
    assert code == 0 and out.count("shard:") == 3
    s1, s3 = prompt(repo, "r1-s1"), prompt(repo, "r1-s3")
    assert "Shard 1 of 3" in s1 and "Shard 3 of 3" in s3
    assert "Do not read the other shards" in s1
    assert "at least 10 distinct ideas" in s1
    assert s1.split("**Operator:**")[1].splitlines()[0] != s3.split("**Operator:**")[1].splitlines()[0]
    assert "/1/s1" in s1 and "/1/s3" in s3
    assert "`M0.1`" not in s1 and "Do not open `roadmap-context.md`" in s1
    # One allocation per session, replaced by `frame --allocation`: only the
    # coordinator's prompt records it, so parallel shards cannot erase each other's.
    assert "frame --slug" in prompt(repo) and "--allocation \"" in prompt(repo)
    assert "--allocation \"" not in s1 and "do not run `brainstorm frame --allocation`" in s1
    # Round 2 writes no shards: regeneration needs the whole pool.
    cli(repo, "add-idea", "--title", "x")
    cli(repo, "next-round")
    assert "Round 2" in prompt(repo, "r2")
    assert not (repo / "work" / f"brainstorm-{SLUG}-r2-s1-prompt.md").exists()
    assert render_shard_prompt(repo, session_fn(repo), count=5, shard=1, total=1).startswith("# Brainstorm shard 1/1")


def test_add_idea_records_origin_hypothesis_and_assumptions(repo: Path) -> None:
    start_fn(repo)
    code, _, _ = cli(repo, "add-idea", "--title", "One", "--origin", "codex/sol/Inversion/1",
                      "--hypothesis", "If we do this, churn drops", "--assumption", "SMBs pay by card",
                      "--assumption", "fees matter", "--kind", "platform")
    assert code == 0
    idea = session_fn(repo).by_id("B1")
    assert idea.origin["lens"] == "Inversion" and idea.hypothesis.startswith("If we")
    assert idea.assumptions == ["SMBs pay by card", "fees matter"] and idea.kind == "platform"
    payload = json.loads(cli(repo, "list", "--json")[1])
    assert payload["round"] == 1 and payload["ideas"][0]["origin"]["harness"] == "codex"


# --- converge ----------------------------------------------------------------

def test_converge_prompt_plays_critics_and_names_overlap_relations(repo: Path) -> None:
    start_fn(repo)
    cli(repo, "add-idea", "--title", "One", "--origin", "cursor/composer/SCAMPER/1")
    cli(repo, "add-evidence", "B1", "--url", "https://example.com/a", "--quote", "q")
    cli(repo, "recommend")
    text = prompt(repo, "recommend")
    assert "three independent critics" in text and "keep dissent" in text
    assert "same-problem-same-solution" in text and "superseded" in text
    assert "must cite" in text
    assert "[cursor/composer/SCAMPER/1]" in text
    assert "evidence (unverified): https://example.com/a" in text
    assert "--cluster C2 --overlap M3.1:adjacent" in text and "--why" in text
    assert "billing" not in text   # the example must not carry another product's domain


def test_revise_records_cluster_overlap_and_critics_without_triaging(repo: Path) -> None:
    start_fn(repo)
    cli(repo, "add-idea", "--title", "One")
    code, _, _ = cli(repo, "revise", "B1", "--cluster", "C1", "--overlap", "M1.1:prerequisite",
                      "--overlap", "M2", "--critic", "feasibility: billing first",
                      "--critic", "value: small segment", "--recommendation", "consider", "--why", "Principle 2")
    assert code == 0
    idea = session_fn(repo).by_id("B1")
    assert idea.cluster_id == "C1" and idea.status == "proposed" and idea.recommendation == "consider"
    assert idea.verdict_why == "Principle 2" and idea.rationale == ""
    assert idea.overlap == [{"node_id": "M1.1", "relation": "prerequisite"}, {"node_id": "M2", "relation": "adjacent"}]
    assert idea.critic == {"feasibility": "billing first", "value": "small segment"}
    code, _, err = cli(repo, "revise", "B1", "--overlap", "M2:near")
    assert code == 1 and "relation" in err


def test_recommend_check_lists_every_idea_the_converge_pass_missed(repo: Path) -> None:
    start_fn(repo)
    for t in ("One", "Two", "Three"):
        cli(repo, "add-idea", "--title", t)
    cli(repo, "revise", "B1", "--cluster", "C1", "--recommendation", "strong")
    cli(repo, "revise", "B2", "--cluster", "C1")
    code, out, _ = cli(repo, "recommend", "--check")
    assert code == 1 and "2 of 3 idea(s) not converged" in out
    assert "B1" not in out and "B2    no recommendation  Two" in out
    assert "B3    no cluster and no recommendation  Three" in out
    assert session_fn(repo).mode == "brainstorm"
    assert not (repo / "work" / f"brainstorm-{SLUG}-recommend-prompt.md").exists()
    cli(repo, "revise", "B2", "--recommendation", "park")
    cli(repo, "revise", "B3", "--cluster", "C2", "--recommendation", "consider")
    code, out, _ = cli(repo, "recommend", "--check")
    assert code == 0 and "all 3 idea(s) have a cluster and a recommendation" in out and "next:" in out


# --- triage ------------------------------------------------------------------

def test_reject_requires_a_reason_and_park_records_a_decision(repo: Path) -> None:
    start_fn(repo)
    cli(repo, "add-idea", "--title", "One")
    cli(repo, "add-idea", "--title", "Two")
    code, _, err = cli(repo, "reject", "B1")
    assert code != 0 and "--reason" in err and session_fn(repo).by_id("B1").status == "proposed"
    assert cli(repo, "reject", "B1", "--reason", "duplicates M1.1")[0] == 0
    d = session_fn(repo).by_id("B1").decision
    assert d["status"] == "rejected" and d["reason"] == "duplicates M1.1" and d["decided_at"]
    assert cli(repo, "park", "B2", "--reason", "after billing", "--revisit-when", "billing ships")[0] == 0
    p = session_fn(repo).by_id("B2")
    assert p.status == "parked" and p.decision["revisit_when"] == "billing ships"
    assert cli(repo, "accept", "B2", "--reason", "changed my mind")[0] == 0
    assert session_fn(repo).by_id("B2").decision["status"] == "accepted"


def test_list_by_cluster_hides_verdicts_unless_asked(repo: Path) -> None:
    start_fn(repo)
    for t in ("One", "Two", "Three"):
        cli(repo, "add-idea", "--title", t)
    cli(repo, "revise", "B1", "--cluster", "C1", "--recommendation", "strong", "--critic", "value: thin")
    cli(repo, "revise", "B2", "--cluster", "C1", "--recommendation", "park")
    _, out, _ = cli(repo, "list", "--by", "cluster")
    assert out.index("C1  (2)") < out.index("(unclustered)  (1)")
    assert "strong" not in out and "value: thin" not in out
    _, out, _ = cli(repo, "list", "--by", "cluster", "--show-verdicts")
    assert "strong" in out and "park" in out and "value: thin" in out


# --- promote -----------------------------------------------------------------

def test_promote_carries_evidence_hypothesis_and_alternatives_into_the_sheet(repo: Path) -> None:
    start_fn(repo)
    cli(repo, "add-idea", "--title", "Stored vault", "--hypothesis", "PCI scope shrinks",
         "--assumption", "we keep cards", "--evidence", "https://example.com/plain")
    cli(repo, "add-idea", "--title", "Vault via vendor")
    cli(repo, "add-evidence", "B1", "--url", "https://example.com/a", "--quote", "exact words")
    cli(repo, "revise", "B1", "--cluster", "C1")
    cli(repo, "revise", "B2", "--cluster", "C1")
    cli(repo, "reject", "B2", "--reason", "vendor lock-in")
    cli(repo, "accept", "B1")
    code, out, err = cli(repo, "promote")
    assert code == 0, err
    node_id = out.split("[ok] added ")[1].split()[0]
    sheet = next((repo / "planning").glob(f"{node_id}_*.md"))
    text = sheet.read_text(encoding="utf-8")
    assert "Brainstorm source: https://example.com/plain" in text
    assert 'Brainstorm evidence (for, unverified): https://example.com/a — "exact words"' in text
    assert "Hypothesis: PCI scope shrinks" in text and "Assumption: we keep cards" in text
    assert "Alternative considered: B2 Vault via vendor (rejected: vendor lock-in)" in text


def test_promote_warns_for_each_strong_idea_no_matched_source_backs(repo: Path) -> None:
    start_fn(repo)
    for t in ("Unverified", "Unsourced", "Matched", "Not found", "Consider"):
        cli(repo, "add-idea", "--title", t)
    for ident in ("B1", "B3", "B4"):
        cli(repo, "add-evidence", ident, "--url", f"https://example.com/{ident}", "--quote", "q")
    session = session_fn(repo)
    session.by_id("B3").sources[0]["verification"] = "matched"
    session.by_id("B4").sources[0]["verification"] = "not-found"
    write_session(repo, session)
    for ident, verdict in (("B1", "strong"), ("B2", "strong"), ("B3", "strong"),
                           ("B4", "strong"), ("B5", "consider")):
        cli(repo, "revise", ident, "--recommendation", verdict)
    cli(repo, "accept", "B1", "B2", "B3", "B4", "B5")
    code, _, err = cli(repo, "promote", "--dry-run")
    assert code == 0
    assert "warning: B1 is recommended strong but no source is matched (unverified)" in err
    assert f"brainstorm verify --slug {SLUG}" in err
    assert "warning: B2 is recommended strong but no source is matched (no sources)" in err
    assert f"brainstorm evidence B2 --slug {SLUG}" in err
    assert "warning: B4 is recommended strong but no source is matched (not-found)" in err
    assert "B3" not in err and "B5" not in err

FORBIDDEN = ("planning/", "roadmap/", "registry.yaml", "shared/", "Do not edit code")







def _started(repo: Path, *extra: str) -> BrainstormSession:
    code, _out, err = cli_folded(repo, "start", "--topic", "How do we expand payments?", "--under", "M1", *extra)
    assert code == 0, err
    return read_session(repo, SLUG)



# --- B8 --------------------------------------------------------------------


def test_round_one_prompt_carries_the_write_allow_list(repo: Path) -> None:
    text = render_brainstorm_prompt(repo, _started(repo), count=5)
    assert "## What you may write" in text
    for needle in FORBIDDEN:
        assert needle in text, needle
    assert "`add-idea`, `add-evidence`, and `revise`" in text



def test_later_rounds_and_shards_carry_the_allow_list_too(repo: Path) -> None:
    session = _started(repo, "--panel", "2")
    add_idea(session, title="Stored vault")
    session.round = 2
    later = render_brainstorm_prompt(repo, session, count=5)
    shard = render_shard_prompt(repo, session, count=5, shard=1, total=2)
    for text in (later, shard):
        assert "## What you may write" in text
        assert "registry.yaml" in text



def test_converge_prompt_still_forbids_new_ideas_but_is_not_a_diverge_prompt(repo: Path) -> None:
    """The allow-list is a diverge rule; converge keeps its own 'no new ideas' rule."""
    text = render_recommend_prompt(repo, _started(repo))
    assert "must not add new ideas" in text



@pytest.mark.repo
def test_suggested_prompt_and_docs_mirror_the_allow_list() -> None:
    prompt = (ROOT / "suggested_prompts" / "brainstorm-roadmap.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "brainstorming.md").read_text(encoding="utf-8")
    for text in (prompt, doc):
        assert "## What" in text and "may write" in text
        for needle in ("planning/", "registry.yaml", "shared/", "edit code"):
            assert needle in text, needle
    assert "Do not implement an idea during the session" in prompt



# --- F8 --------------------------------------------------------------------


def test_revise_rejects_an_overlap_without_a_node_id(repo: Path) -> None:
    session = _started(repo)
    add_idea(session, title="Stored vault")
    from specy_road.brainstorm_session import write_session

    write_session(repo, session)

    code, _out, err = cli_folded(repo, "revise", "B1", "--overlap", ":adjacent")

    assert code == 1
    assert "node id" in err
    assert read_session(repo, SLUG).by_id("B1").overlap == []   # nothing written; file still reads



@pytest.mark.parametrize("text", ["", ":", "  :prerequisite"])
def test_parse_overlap_needs_a_node_id(text: str) -> None:
    with pytest.raises(BrainstormError, match="node id"):
        parse_overlap(text)



def test_add_evidence_with_an_empty_url_is_a_brainstorm_error(repo: Path) -> None:
    session = _started(repo)
    add_idea(session, title="Stored vault")
    from specy_road.brainstorm_session import write_session

    write_session(repo, session)

    code, _out, err = cli_folded(repo, "add-evidence", "B1", "--url", "", "--quote", "q")

    assert code == 1
    assert "--url is required" in err
    assert read_session(repo, SLUG).by_id("B1").sources == []



@pytest.mark.parametrize("url", ["", "   "])
def test_source_record_needs_a_url(url: str) -> None:
    with pytest.raises(BrainstormError, match="--url is required"):
        source_record(url, quote="q")



def test_a_loaded_source_with_an_unknown_stance_is_rejected() -> None:
    with pytest.raises(BrainstormError, match="stance 'maybe'"):
        idea_from_dict({"id": "B1", "title": "t", "sources": [{"url": "https://x", "stance": "maybe"}]})
    ok = idea_from_dict({"id": "B1", "title": "t", "sources": [{"url": "https://x", "stance": "against"}]})
    assert ok.sources[0]["stance"] == "against"



def test_start_help_no_longer_claims_research(repo: Path) -> None:
    _code, out, _err = cli_folded(repo, "-h")
    flat = " ".join(out.split())   # argparse wraps the description
    assert "no research in round 1" in flat
    assert "Socratic questioning, research)" not in flat
