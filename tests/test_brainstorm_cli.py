"""``specy-road brainstorm`` end to end, through the real CLI dispatch.

Covers the two-mode contract the feature rests on: `start` must ask for volume
and forbid evaluation, `recommend` must ask for judgement and forbid new ideas,
and the PM's triage must stay the PM's.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.bundled_scripts.brainstorm_session import resolve_slug
from tests.helpers import DOGFOOD, REPO, script_subprocess_env


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "brainstorm", *args,
         "--repo-root", str(repo)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )


def _start(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return _run(repo, "start", "--topic", "How do we expand payments?", *extra)


def _prompt(repo: Path) -> str:
    path = repo / "work" / "brainstorm-how-do-we-expand-payments-prompt.md"
    return path.read_text(encoding="utf-8")


def test_start_writes_a_session_and_a_prompt(repo: Path) -> None:
    r = _start(repo, "--under", "M1")

    assert r.returncode == 0, r.stderr
    assert (repo / "work" / "brainstorm-how-do-we-expand-payments.yaml").is_file()
    assert (repo / "work" / "brainstorm-how-do-we-expand-payments-prompt.md").is_file()


def test_the_slug_falls_out_of_the_topic(repo: Path) -> None:
    assert _start(repo).returncode == 0

    assert "brainstorm-how-do-we-expand-payments.yaml" in _start(repo).stdout


def test_start_without_a_topic_or_slug_is_refused(repo: Path) -> None:
    r = _run(repo, "start")

    assert r.returncode == 1
    assert "--topic" in r.stderr


def test_the_diverge_prompt_asks_for_volume_and_forbids_ranking(repo: Path) -> None:
    _start(repo, "--count", "40")

    text = _prompt(repo)
    assert "at least 40 distinct ideas" in text
    assert "Do not rank, cluster, sequence, or estimate" in text


def test_the_diverge_prompt_carries_the_brainstorming_techniques(repo: Path) -> None:
    _start(repo)

    text = _prompt(repo)
    for lens in ("SCAMPER", "Analogous domains", "Inversion", "Pre-mortem",
                 "Constraint removal", "10x / 0.1x"):
        assert lens in text


def test_the_diverge_prompt_opens_with_socratic_questions(repo: Path) -> None:
    _start(repo)

    text = _prompt(repo)
    assert "interrogate the question before answering it" in text
    assert "Who exactly is served, and who is deliberately not?" in text


def test_round_one_defers_research_and_round_two_opens_it(repo: Path) -> None:
    """Early search results and the roadmap inventory both anchor the model
    (design note B3), so round 1 generates without them and round 2 opens research."""
    _start(repo)

    text = _prompt(repo)
    assert "Do not research yet and do not read the roadmap" in text
    assert "web search" not in text.split("## Step 3")[1].split("## Record")[0]
    _run(repo, "add-idea", "--title", "One")
    assert _run(repo, "next-round").returncode == 0

    text = _prompt(repo)
    assert "Round 2 — add only what is outside the pool" in text
    assert "- B1 One" in text
    assert "use your web search" in text and "--evidence" in text
    assert "probability a typical PM would propose it" in text


def test_the_diverge_prompt_points_at_the_ide_agents_own_tools(repo: Path) -> None:
    """The CLI calls no model and no search API; the IDE agent does the work."""
    _start(repo)

    text = _prompt(repo)
    assert "slash commands and skills" in text
    assert "specy-road calls no model and no search API from the CLI" in text


def test_the_roadmap_inventory_moves_to_the_converge_prompt(repo: Path) -> None:
    """Ideas that restate committed work waste the PM's triage — but the
    inventory shown before generation anchors the model, so overlap is
    checked at converge, where it is needed."""
    _start(repo)
    assert "`M0.1`" not in _prompt(repo)
    _run(repo, "add-idea", "--title", "One")
    _run(repo, "recommend")

    text = _prompt(repo)
    assert "Do not propose work that is already on the roadmap" in text
    assert "`M0.1`" in text


def test_add_idea_allocates_ids_in_order(repo: Path) -> None:
    _start(repo)

    first = _run(repo, "add-idea", "--title", "One")
    second = _run(repo, "add-idea", "--title", "Two")

    assert "[ok] B1 One" in first.stdout
    assert "[ok] B2 Two" in second.stdout


def test_list_reports_status_and_recommendation(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "One")
    _run(repo, "accept", "B1")

    out = _run(repo, "list").stdout

    assert "B1" in out and "accepted" in out


def test_list_json_is_machine_readable(repo: Path) -> None:
    _start(repo, "--under", "M1")
    _run(repo, "add-idea", "--title", "One", "--evidence", "https://x")

    payload = json.loads(_run(repo, "list", "--json").stdout)

    assert payload["under"] == "M1"
    assert payload["ideas"][0]["title"] == "One"
    assert payload["ideas"][0]["evidence"] == ["https://x"]


def test_list_filters_by_status(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "Keep")
    _run(repo, "add-idea", "--title", "Drop")
    _run(repo, "accept", "B1")
    _run(repo, "reject", "B2")

    payload = json.loads(_run(repo, "list", "--json", "--status", "accepted").stdout)

    assert [i["title"] for i in payload["ideas"]] == ["Keep"]


def test_accept_takes_several_ideas_at_once(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "One")
    _run(repo, "add-idea", "--title", "Two")

    r = _run(repo, "accept", "B1", "B2")

    assert r.returncode == 0, r.stderr
    payload = json.loads(_run(repo, "list", "--json", "--status", "accepted").stdout)
    assert len(payload["ideas"]) == 2


def test_a_recommendation_alone_does_not_consume_the_triage_decision(repo: Path) -> None:
    """The agent advises; accepting and rejecting stays the PM's call."""
    _start(repo)
    _run(repo, "add-idea", "--title", "One")

    _run(repo, "revise", "B1", "--recommendation", "strong")

    idea = json.loads(_run(repo, "list", "--json").stdout)["ideas"][0]
    assert idea["recommendation"] == "strong"
    assert idea["status"] == "proposed"


def test_editing_content_marks_the_idea_revised(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "One")

    _run(repo, "revise", "B1", "--title", "One, sharpened")

    idea = json.loads(_run(repo, "list", "--json").stdout)["ideas"][0]
    assert idea["title"] == "One, sharpened"
    assert idea["status"] == "revised"


def test_recommend_switches_the_session_to_roadmap_mode(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "One")

    assert _run(repo, "recommend").returncode == 0

    assert json.loads(_run(repo, "list", "--json").stdout)["mode"] == "roadmap"


def test_the_converge_prompt_asks_for_judgement_not_ideas(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "Stored payment vault")
    _run(repo, "recommend")

    text = _prompt(repo)
    assert "you must not add new ideas" in text
    assert "Cluster near-duplicates" in text
    assert "**B1** (proposed, feature) — Stored payment vault" in text


def test_promote_writes_accepted_ideas_into_the_graph(repo: Path) -> None:
    _start(repo, "--under", "M1")
    _run(repo, "add-idea", "--title", "Stored payment vault")
    _run(repo, "accept", "B1")

    r = _run(repo, "promote")

    assert r.returncode == 0, r.stderr
    assert "Stored payment vault" in r.stdout
    listed = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "validate", "--repo-root", str(repo)],
        cwd=REPO, capture_output=True, text=True, env=script_subprocess_env(),
    )
    assert listed.returncode == 0, listed.stderr


def test_promote_with_nothing_accepted_says_so(repo: Path) -> None:
    _start(repo, "--under", "M1")
    _run(repo, "add-idea", "--title", "One")

    r = _run(repo, "promote")

    assert r.returncode == 0
    assert "nothing to promote" in r.stdout


def test_several_open_sessions_require_a_slug(repo: Path) -> None:
    _start(repo)
    _run(repo, "start", "--topic", "Something else entirely")

    r = _run(repo, "list")

    assert r.returncode == 1
    assert "--slug" in r.stderr


def test_sessions_lists_every_open_brainstorm(repo: Path) -> None:
    _start(repo)
    _run(repo, "start", "--topic", "Something else entirely")

    out = _run(repo, "sessions").stdout

    assert "how-do-we-expand-payments" in out
    assert "something-else-entirely" in out


def test_reopening_a_session_keeps_its_ideas(repo: Path) -> None:
    _start(repo)
    _run(repo, "add-idea", "--title", "One")
    _run(repo, "recommend")

    r = _start(repo)

    assert "(1 ideas, round 1 of 2" in r.stdout
    assert json.loads(_run(repo, "list", "--json").stdout)["mode"] == "brainstorm"


def _seed(repo: Path, slug: str) -> None:
    assert _run(repo, "start", "--slug", slug, "--topic", slug).returncode == 0


def test_an_unreadable_session_is_flagged_and_the_rest_still_listed(repo: Path) -> None:
    for slug in ("aa", "bb", "cc"):
        _seed(repo, slug)
    bad = repo / "work" / "brainstorm-bb.yaml"
    text = bad.read_text(encoding="utf-8").replace(
        "ideas: []", "ideas:\n- id: B3\n  title: T\n  recommendation: ship it soon\n")
    bad.write_text(text, encoding="utf-8")

    r = _run(repo, "sessions")

    assert r.returncode == 1
    assert "aa" in r.stdout and "cc" in r.stdout and "bb" not in r.stdout
    assert "bb: unreadable — work/brainstorm-bb.yaml: idea B3: recommendation 'ship it soon'" in r.stderr
    assert "edit the file: use one of those or remove the key" in r.stderr
    assert bad.read_text(encoding="utf-8") == text   # reported, not rewritten


def test_close_moves_the_session_and_its_prompts_and_nothing_else(repo: Path) -> None:
    _seed(repo, "a")
    _seed(repo, "ab")
    work = repo / "work"
    (work / "brainstorm-a-s1-prompt.md").write_text("shard", encoding="utf-8")

    r = _run(repo, "close", "--slug", "a")

    assert r.returncode == 0, r.stderr
    closed = work / "brainstorm-closed"
    assert sorted(p.name for p in closed.iterdir()) == [
        "brainstorm-a-prompt.md", "brainstorm-a-s1-prompt.md", "brainstorm-a.yaml"]
    assert "moved work/brainstorm-a.yaml -> work/brainstorm-closed/brainstorm-a.yaml" in r.stdout
    assert (work / "brainstorm-ab.yaml").is_file() and (work / "brainstorm-ab-prompt.md").is_file()
    assert resolve_slug(repo, None) == "ab"   # the closed session no longer counts as open
    assert json.loads(_run(repo, "list", "--json").stdout)["slug"] == "ab"


def test_close_refuses_a_missing_session_and_an_existing_destination(repo: Path) -> None:
    _seed(repo, "a")
    assert _run(repo, "close").returncode == 0

    again = _run(repo, "close", "--slug", "a")
    assert again.returncode == 1 and "no open brainstorm session 'a'" in again.stderr

    _seed(repo, "a")
    clash = _run(repo, "close", "--slug", "a")
    assert clash.returncode == 1 and "work/brainstorm-closed/brainstorm-a.yaml already exists" in clash.stderr
    assert (repo / "work" / "brainstorm-a.yaml").is_file()   # nothing moved
