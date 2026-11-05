"""M14.6: review delegate keeps each round's RUN files and notes; ``review usage``; reviewers in ``worker usage``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import commit_file, git
from tests.test_review_delegate import FAKE, _delegate, _files_record, _repo, _run, _steps

from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli
from specy_road.bundled_scripts.worker_cli_render import usage, usage_lines
from specy_road.review_files import reviews_dir
from specy_road.worker_adapter_parsers import USAGE_FIELDS

# The fake harness's result line also carries the step's usage, as Claude's stream-json result does.
# It writes the step's notes during the run, as a reviewer does.
FAKE_USAGE = FAKE.replace('"result": "filed", "session_id": sid}', '"result": "filed", "session_id": sid, **step.get("result", {})}')
FAKE_USAGE = FAKE_USAGE.replace('if step.get("say"):', 'if step.get("notes"):\n    open(step["notes"]["path"], "w").write(step["notes"]["text"])\nif step.get("say"):')
assert FAKE_USAGE.count("step.get") == FAKE.count("step.get") + 2


def _round(repo: Path, notes: str, **result) -> dict:
    notes_step = {"path": str(reviews_dir(repo, "M1.1") / "notes-opus.md"), "text": notes}
    return {**_files_record(repo), "notes": notes_step, "say": "reviewing", "result": result}


@pytest.fixture()
def two_rounds(tmp_path: Path) -> tuple[Path, str, str]:
    repo, spec = _repo(tmp_path)
    (tmp_path / "fake.py").write_text(FAKE_USAGE)
    c1 = git(repo, "rev-parse", "HEAD")
    _steps(repo, spec, _round(repo, "round one notes\n", usage={"input_tokens": 100, "output_tokens": 10},
                              total_cost_usd=0.5, num_turns=3))
    assert _delegate(repo) == 0
    c2 = commit_file(repo, "src/a.py", "print('fixed')\n", "fix")
    _steps(repo, spec, _round(repo, "round two notes\n", usage={"input_tokens": 200, "output_tokens": 20},
                              total_cost_usd=0.25, num_turns=2))
    assert _delegate(repo) == 0
    return repo, c1, c2


def test_each_round_keeps_its_run_json_log_and_notes_in_history(two_rounds) -> None:
    """A1/A4: round 1's files are kept under history/ with its commit and round; the current files are round 2's."""
    repo, c1, c2 = two_rounds
    d = reviews_dir(repo, "M1.1")
    hist = d / "history"
    kept = json.loads((hist / f"RUN-opus-{c1[:12]}-1.json").read_text())
    assert kept["commit"] == c1 and kept["model"] == "opus"
    assert '"input_tokens": 100' in (hist / f"RUN-opus-{c1[:12]}-1.log").read_text()
    assert (hist / "notes" / f"notes-opus-{c1[:12]}-1.md").read_text() == "round one notes\n"
    assert json.loads((d / "RUN-opus.json").read_text())["commit"] == c2
    current_log = (d / "RUN-opus.log").read_text()
    assert '"input_tokens": 200' in current_log and '"input_tokens": 100' not in current_log
    assert (d / "notes-opus.md").read_text() == "round two notes\n"
    assert not list(hist.glob("notes-*.md"))   # never beside the filed records history/*.md holds


def test_review_usage_lists_each_run_and_the_total(two_rounds, capsys) -> None:
    """A2: per run (model, round, commit) and a total, --json and text; '?' where the harness reported nothing."""
    repo, c1, c2 = two_rounds
    capsys.readouterr()
    assert _run("review", "usage", "M1.1", "--json", "--repo-root", str(repo)) == 0
    data = json.loads(capsys.readouterr().out)
    assert [(r["model"], r["round"], r["commit"]) for r in data["runs"]] == [("opus", 1, c1), ("opus", 2, c2)]
    assert [(r["input_tokens"], r["output_tokens"], r["cost_usd"]) for r in data["runs"]] == [(100, 10, 0.5),
                                                                                              (200, 20, 0.25)]
    t = data["total"]
    assert (t["runs"], t["turns"], t["input_tokens"], t["output_tokens"], t["cost_usd"]) == (2, 2, 300, 30, 0.75)
    assert t["reasoning_tokens"] is None
    assert _run("review", "usage", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert f"opus round 1 at {c1[:12]} (complete), 1 turn(s): in 100 (? cached), out 10, reasoning ?" in out
    assert "  total, 2 turn(s): in 300 (? cached), out 30, reasoning ?, $0.7500 est." in out


def test_worker_usage_adds_reviewers_to_the_node_total(two_rounds, capsys) -> None:
    """A3: executors, reviewers and the combined total, each on its own line."""
    repo, _c1, _c2 = two_rounds
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.append_event(repo, rec, "usage", source="worker", summary="usage",
                    detail={**dict.fromkeys(USAGE_FIELDS), "input_tokens": 1000, "output_tokens": 100, "cost_usd": 1.0})
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        worker_cli.main(["worker", "usage", "M1.1", "--repo-root", str(repo)])
    assert (exc.value.code or 0) == 0
    out = capsys.readouterr().out
    assert "  executors, 1 turn(s): in 1000 (? cached), out 100, reasoning ?, $1.0000" in out
    assert "  reviewers, 2 run(s), 2 turn(s): in 300 (? cached), out 30, reasoning ?, $0.7500 est." in out
    assert "  total, 3 turn(s): in 1300 (? cached), out 130, reasoning ?, $1.7500 est." in out


def test_a_removed_worktree_still_finds_its_projects_reviews(two_rounds) -> None:
    """A finished leaf's worktree is gone; its nearest existing parent names the project."""
    repo, _c1, _c2 = two_rounds
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo / "work" / ".worktrees" / "gone")
    lines = usage_lines(usage([(rec, [])]))
    assert any(line.startswith("  reviewers, 2 run(s)") for line in lines)


def test_no_delegated_review_keeps_the_single_total_line(tmp_path: Path) -> None:
    repo, _spec = _repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    lines = usage_lines(usage([(rec, [])]))
    assert lines[-1] == "  total, 0 turn(s): in ? (? cached), out ?, reasoning ?, $?"
    assert not any("reviewers" in line or "executors" in line for line in lines)
