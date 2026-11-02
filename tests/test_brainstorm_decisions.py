"""M4.4: policy kind and `decide`, promote's Decided policies section, frame amend/provisional/confirm."""

from __future__ import annotations

import contextlib
import io
import shutil
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_promote import promote_session
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    prompt_path,
    read_session,
    session_path,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from tests.helpers import DOGFOOD

SLUG = "how-do-we-expand-payments"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _cli(repo: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            brainstorm_cli.main(["brainstorm", *args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _start(repo: Path, *titles: str, under: str = "M1") -> None:
    assert _cli(repo, "start", "--topic", "How do we expand payments?", "--under", under)[0] == 0
    for title in titles:
        assert _cli(repo, "add-idea", "--title", title)[0] == 0


def _sheet(root: Path, node_id: str) -> str:
    node = next(n for n in load_roadmap(root)["nodes"] if n["id"] == node_id)
    return (root / node["planning_dir"]).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    body = text.split(f"## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]


def _node_count(root: Path) -> int:
    return len(load_roadmap(root)["nodes"])


# A1: policy kind and decide


def test_add_idea_accepts_kind_policy(repo: Path) -> None:
    _start(repo)
    code, _out, err = _cli(repo, "add-idea", "--title", "No card data at rest", "--kind", "policy")

    assert code == 0, err
    assert read_session(repo, SLUG).by_id("B1").kind == "policy"


def test_decide_sets_status_decided_and_records_the_decision(repo: Path) -> None:
    _start(repo, "Store card data?")

    code, out, err = _cli(repo, "decide", "B1", "--decision", "We never store card numbers")

    assert code == 0, err
    assert "[ok] B1 decided: We never store card numbers" in out
    idea = read_session(repo, SLUG).by_id("B1")
    assert idea.status == "decided"
    assert idea.decision["decision"] == "We never store card numbers"
    assert idea.decision["status"] == "decided" and idea.decision["decided_at"]
    assert "decision: We never store card numbers" in _cli(repo, "list")[1]
    assert "decided: 1" in _cli(repo, "list", "--summary")[1]


def test_decide_needs_a_decision(repo: Path) -> None:
    _start(repo, "Store card data?")

    assert _cli(repo, "decide", "B1")[0] == 2
    code, _out, err = _cli(repo, "decide", "B1", "--decision", "  ")
    assert code == 1 and "--decision" in err
    assert read_session(repo, SLUG).by_id("B1").status == "proposed"


def test_decide_refuses_a_merged_idea(repo: Path) -> None:
    _start(repo, "Vault", "Token vault")
    assert _cli(repo, "merge", "B1", "--into", "B2")[0] == 0

    code, _out, err = _cli(repo, "decide", "B1", "--decision", "x")

    assert code == 1 and "merged" in err


# A2: promote renders decided ideas into the anchor's sheet


def test_promote_writes_decided_ideas_into_the_anchor_sheet_not_as_nodes(repo: Path) -> None:
    _start(repo, "Store card data?", "Stored payment vault")
    _cli(repo, "decide", "B1", "--decision", "We never store card numbers")
    _cli(repo, "accept", "B2")
    before = _node_count(repo)

    code, out, err = _cli(repo, "promote")

    assert code == 0, err
    assert _node_count(repo) == before + 1
    assert "Stored payment vault" in out and "Store card data?" not in out
    assert "## Decided policies" in err
    policies = _section(_sheet(repo, "M1"), "Decided policies")
    assert f"- **Store card data?:** We never store card numbers (brainstorm `{SLUG}`, B1)" in policies
    assert "Stored payment vault" not in policies
    assert read_session(repo, SLUG).by_id("B1").promoted_node_key is None


def test_promote_with_only_decided_ideas_writes_the_section(repo: Path) -> None:
    _start(repo, "Store card data?")
    _cli(repo, "decide", "B1", "--decision", "Never")
    before = _node_count(repo)

    code, out, _err = _cli(repo, "promote")

    assert code == 0 and "nothing to promote" not in out
    assert _node_count(repo) == before
    assert "Never (brainstorm" in _section(_sheet(repo, "M1"), "Decided policies")


def test_promote_dry_run_writes_no_policies(repo: Path) -> None:
    _start(repo, "Store card data?")
    _cli(repo, "decide", "B1", "--decision", "Never")
    sheet_before = _sheet(repo, "M1")

    code, _out, err = _cli(repo, "promote", "--dry-run")

    assert code == 0 and "would write 1 decided idea(s)" in err
    assert _sheet(repo, "M1") == sheet_before


def test_a_rerun_replaces_this_sessions_policies_and_keeps_other_sessions(repo: Path) -> None:
    other = BrainstormSession(slug="refunds", topic="Refunds", under="M1")
    add_idea(other, title="Refund window", status="decided", decision={"decision": "30 days"})
    promote_session(repo, other)
    _start(repo, "Store card data?", "Retry failed charges")
    _cli(repo, "decide", "B1", "--decision", "Never")
    _cli(repo, "decide", "B2", "--decision", "Three retries")
    _cli(repo, "promote")
    _cli(repo, "reject", "B2", "--reason", "too early")

    _cli(repo, "promote")

    policies = _section(_sheet(repo, "M1"), "Decided policies")
    assert "30 days (brainstorm `refunds`, B1)" in policies
    assert policies.count(f"(brainstorm `{SLUG}`") == 1 and "Never" in policies
    assert "Three retries" not in policies


def test_decided_ideas_without_an_anchor_sheet_are_reported_not_written(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    session = BrainstormSession(slug="root", topic="t")
    add_idea(session, title="Policy", status="decided", decision={"decision": "x"})
    planning = sorted(p.read_text(encoding="utf-8") for p in (repo / "planning").glob("*.md"))

    assert promote_session(repo, session) == []

    assert "decided idea(s) B1 not written: the roadmap root has no planning sheet" in capsys.readouterr().err
    assert sorted(p.read_text(encoding="utf-8") for p in (repo / "planning").glob("*.md")) == planning


# A3: frame amend, provisional, confirm


def test_amend_keeps_the_previous_answer_in_history(repo: Path) -> None:
    _start(repo)
    _cli(repo, "frame", "--answer", "served=assumed: SMBs")

    code, out, err = _cli(repo, "frame", "--amend", "served", "--answer", "SMBs and marketplaces")

    assert code == 0, err
    assert "served amended" in out
    session = read_session(repo, SLUG)
    assert session.frame["served"] == "SMBs and marketplaces"
    [entry] = session.frame_history
    assert entry["key"] == "served" and entry["answer"] == "assumed: SMBs" and entry["replaced_at"]
    raw = yaml.safe_load(session_path(repo, SLUG).read_text(encoding="utf-8"))
    assert raw["frame_history"][0]["answer"] == "assumed: SMBs"


def test_amend_takes_key_equals_text_too(repo: Path) -> None:
    _start(repo)
    _cli(repo, "frame", "--answer", "outcome=fewer failures")

    assert _cli(repo, "frame", "--amend", "outcome", "--answer", "outcome=fewer retries")[0] == 0

    assert read_session(repo, SLUG).frame["outcome"] == "fewer retries"


def test_amend_refuses_an_unrecorded_key_or_several_answers(repo: Path) -> None:
    _start(repo)
    _cli(repo, "frame", "--answer", "outcome=x")

    code, _out, err = _cli(repo, "frame", "--amend", "budget", "--answer", "small")
    assert code == 1 and "--answer budget=TEXT" in err
    code, _out, err = _cli(repo, "frame", "--amend", "outcome", "--answer", "a", "--answer", "b")
    assert code == 1 and "exactly one --answer" in err
    assert read_session(repo, SLUG).frame_history == []


def test_re_answering_a_key_keeps_only_changed_answers_in_history(repo: Path) -> None:
    _start(repo)
    _cli(repo, "frame", "--answer", "outcome=x")
    _cli(repo, "frame", "--answer", "outcome=x")
    _cli(repo, "frame", "--answer", "outcome=y")

    assert [h["answer"] for h in read_session(repo, SLUG).frame_history] == ["x"]


def test_provisional_and_confirm_mark_the_frame_and_later_prompts_show_it(repo: Path) -> None:
    _start(repo, "Vault")
    _cli(repo, "frame", "--answer", "outcome=x", "--provisional")
    assert read_session(repo, SLUG).frame_state == "provisional"
    assert _cli(repo, "next-round")[0] == 0
    assert "Frame state: provisional" in prompt_path(repo, SLUG, "r2").read_text(encoding="utf-8")

    code, out, _err = _cli(repo, "frame", "--confirm")

    assert code == 0 and ", confirmed" in out
    assert read_session(repo, SLUG).frame_state == "confirmed"
    assert _cli(repo, "next-round")[0] == 0
    text = prompt_path(repo, SLUG, "r3").read_text(encoding="utf-8")
    assert "Frame state: confirmed" in text and "provisional" not in text


def test_shard_prompts_show_the_frame_state(repo: Path) -> None:
    assert _cli(repo, "start", "--topic", "How do we expand payments?", "--panel", "2")[0] == 0

    assert _cli(repo, "frame", "--answer", "outcome=x", "--provisional")[0] == 0

    assert "Frame state: provisional" in prompt_path(repo, SLUG, "r1-s1").read_text(encoding="utf-8")


def test_provisional_and_confirm_are_exclusive_and_need_a_frame(repo: Path) -> None:
    _start(repo)

    assert _cli(repo, "frame", "--provisional", "--confirm")[0] == 2
    code, _out, err = _cli(repo, "frame", "--confirm")
    assert code == 1 and "no frame recorded" in err
    assert read_session(repo, SLUG).frame_state == ""


def test_an_unmarked_frame_adds_no_state_line(repo: Path) -> None:
    _start(repo, "Vault")
    _cli(repo, "frame", "--answer", "outcome=x")
    _cli(repo, "next-round")

    assert "Frame state" not in prompt_path(repo, SLUG, "r2").read_text(encoding="utf-8")


def test_a_bad_frame_state_in_the_file_is_reported(repo: Path) -> None:
    _start(repo)
    path = session_path(repo, SLUG)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    path.write_text(yaml.safe_dump({**raw, "frame_state": "maybe"}), encoding="utf-8")

    with pytest.raises(BrainstormError, match="frame_state 'maybe' not one of provisional, confirmed"):
        read_session(repo, SLUG)
