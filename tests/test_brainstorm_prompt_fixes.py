"""Brainstorm prompt fixes from rc1 feedback (M3.4).

Start before reading anything; frame with proposed answers over the
canonical keys; panel shard cells from the recorded allocation, with the
frame; one prompt file per pass; no "(missing)" digest line; a warning on the
integration branch; and every command naming the next step.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import brainstorm_cli
from specy_road.bundled_scripts.brainstorm_prompt import render_brainstorm_prompt, render_recommend_prompt
from specy_road.bundled_scripts.brainstorm_session import add_idea, read_session

ROOT = Path(__file__).resolve().parents[1]
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
            brainstorm_cli.main([*args, "--repo-root", str(repo)])
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    return code, out.getvalue(), err.getvalue()


def _start(repo: Path, *extra: str) -> tuple[int, str, str]:
    return _cli(repo, "start", "--topic", "How do we expand payments?", "--under", "M1", *extra)


def _prompt(repo: Path, pass_name: str) -> str:
    return (repo / "work" / f"brainstorm-{SLUG}-{pass_name}-prompt.md").read_text(encoding="utf-8")


def test_skill_and_managed_block_say_to_start_before_reading_the_digest() -> None:
    skill = (ROOT / "specy_road/templates/specyrd/commands/specyrd-brainstorm.md").read_text(encoding="utf-8")
    block = (ROOT / "specy_road/templates/specyrd/agents-md-block.md").read_text(encoding="utf-8")
    load_order_0 = next(ln for ln in block.splitlines() if ln.startswith("0. `roadmap-context.md`"))
    assert "run `brainstorm start` before reading this or anything else" in load_order_0
    head = skill.split("```bash")[0]
    assert "Run `start` **before reading anything else**" in head
    assert "`roadmap-context.md`" in head and "roadmap" in head


def test_round_one_frame_proposes_answers_over_the_canonical_keys(repo: Path) -> None:
    _start(repo)
    text = _prompt(repo, "r1")
    step1 = text.split("## Step 1")[1].split("## Step 2")[0]
    assert "Do not hand the PM a questionnaire" in step1 and "**propose an answer**" in step1
    assert "mark your answer `assumed`" in step1 and "Wait for answers" not in step1
    assert ("**Required** before you generate: `outcome`, `served`, `assumed-vs-known`, "
            "`not-the-question`.") in step1
    for key in ("outcome", "served", "assumed-vs-known", "not-the-question"):
        assert f"- `{key}` (required) — " in step1, key
    for key in ("metric", "tried", "fixed-or-choice", "do-nothing", "deadline", "budget"):
        assert f"- `{key}` — " in step1, key
    assert "--answer \"served=assumed: ...\"" in step1


def test_frame_rewrites_panel_shards_with_their_allocation_cells_and_the_frame(repo: Path) -> None:
    _start(repo, "--panel", "3", "--count", "12")
    assert "label" in _prompt(repo, "r1") and "`s1:`" in _prompt(repo, "r1")
    assert "**outcome:**" not in _prompt(repo, "r1-s1")   # written before any frame

    code, out, err = _cli(repo, "frame", "--answer", "outcome=fewer failed payments",
                          "--allocation", "s1: Inversion x user segments, Random constraints, 4\n"
                                          "S2 = Pre-mortem x risk and compliance, Low typicality, 4")
    assert code == 0, err
    assert out.count("(rewritten)") == 3
    s1, s2, s3 = (_prompt(repo, f"r1-s{k}") for k in (1, 2, 3))
    assert "**Cell (from the recorded allocation):** Inversion x user segments, Random constraints, 4" in s1
    assert "**Cell (from the recorded allocation):** Pre-mortem x risk and compliance, Low typicality, 4" in s2
    assert "**Operator:**" not in s1 and "**Operator:**" in s3   # unlabelled shard: by its number
    for shard in (s1, s2, s3):
        assert "## The agreed frame" in shard and "**outcome:** fewer failed payments" in shard
        assert "at least 4 distinct ideas" in shard   # the --count recorded at start, not the default


def test_each_pass_keeps_its_own_prompt_and_names_the_next_command(repo: Path) -> None:
    nxt = f"--slug {SLUG}`"
    _, out, _ = _start(repo)
    assert f"next: when the agent has recorded its ideas, `specy-road brainstorm next-round {nxt} (round 2 of 2)" in out
    _cli(repo, "add-idea", "--title", "Stored vault")
    _, out, _ = _cli(repo, "next-round")
    assert f"`specy-road brainstorm recommend {nxt}" in out
    _, out, _ = _cli(repo, "recommend")
    assert f"`specy-road brainstorm evidence {nxt} for the shortlist, then `specy-road brainstorm verify {nxt}" in out
    _cli(repo, "revise", "B1", "--recommendation", "strong")
    _, out, _ = _cli(repo, "evidence")
    assert f"next: when the sources are recorded, `specy-road brainstorm verify {nxt}" in out
    _, out, _ = _cli(repo, "verify")
    assert f"next: triage: `specy-road brainstorm list --by cluster {nxt}" in out
    _, out, _ = _cli(repo, "accept", "B1")
    assert f"`specy-road brainstorm promote --dry-run {nxt}, then `specy-road brainstorm promote {nxt}" in out
    code, out, err = _cli(repo, "promote")
    assert code == 0, err
    assert f"next: `specy-road export && specy-road digest`, then `specy-road brainstorm close {nxt}" in out

    assert _prompt(repo, "r1").startswith("# Brainstorm: ")
    assert _prompt(repo, "r2").startswith("# Brainstorm, round 2: ")
    assert _prompt(repo, "recommend").startswith("# Recommend: ")
    assert _prompt(repo, "evidence").startswith("# Evidence: ")
    assert not (repo / "work" / f"brainstorm-{SLUG}-prompt.md").exists()


def test_in_pass_and_session_commands_name_the_step_too(repo: Path) -> None:
    nxt = f"--slug {SLUG}`"
    _start(repo)
    for args in (("frame", "--answer", "outcome=fewer failed payments"), ("add-idea", "--title", "Stored vault"),
                 ("list",)):
        code, out, err = _cli(repo, *args)
        assert code == 0, err
        assert f"next: when the agent has recorded its ideas, `specy-road brainstorm next-round {nxt}" in out, args
    _, out, err = _cli(repo, "list", "--json")
    assert json.loads(out)["slug"] == SLUG and "next-round" in err   # stdout stays JSON
    _cli(repo, "recommend")
    _, out, _ = _cli(repo, "revise", "B1", "--recommendation", "strong")
    assert f"next: when the verdicts are recorded, `specy-road brainstorm evidence {nxt}" in out
    _, out, _ = _cli(repo, "add-evidence", "B1", "--url", "https://example.com/a", "--quote", "a quote")
    assert f"next: when the sources are recorded, `specy-road brainstorm verify {nxt}" in out
    _cli(repo, "accept", "B1")
    code, out, err = _cli(repo, "promote", "--dry-run")
    assert code == 0, err
    assert "Dry run — nothing written." in out and f"next: `specy-road brainstorm promote {nxt} to apply" in out
    _, out, _ = _cli(repo, "sessions")
    assert "next: `specy-road brainstorm list --slug SLUG`" in out
    _, out, _ = _cli(repo, "close")
    assert out.splitlines()[-1].startswith("done: nothing follows for this session")
    _, out, _ = _cli(repo, "sessions")
    assert "next: `specy-road brainstorm start --topic '<question>'`" in out


def test_prompts_omit_the_digest_line_when_there_is_no_digest(repo: Path) -> None:
    _start(repo)
    session = read_session(repo, SLUG)
    add_idea(session, title="Stored vault")
    session.round = 2
    assert "**Current roadmap state:** `roadmap-context.md`\n" in render_brainstorm_prompt(repo, session, count=5)
    (repo / "roadmap-context.md").unlink()
    for text in (render_brainstorm_prompt(repo, session, count=5), render_recommend_prompt(repo, session)):
        assert "Current roadmap state" not in text and "_(missing)_" not in text


def test_start_warns_on_the_integration_branch_only(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECY_ROAD_INTEGRATION_BRANCH", raising=False)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)   # the fixture's integration branch

    code, _out, err = _start(repo)
    assert code == 0
    assert ("warning: on the integration branch 'main'; the session file is tracked, so brainstorm on a "
            f"branch of its own: git checkout -b chore/brainstorm-{SLUG}") in err

    subprocess.run(["git", "checkout", "-q", "-b", f"chore/brainstorm-{SLUG}"], cwd=repo, check=True)
    assert "integration branch" not in _start(repo)[2]
