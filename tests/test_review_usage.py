"""M14.6: review delegate keeps each round's RUN files and notes; ``review usage``; reviewers in ``worker usage``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_delegate_helpers import (
    CAPACITY,
    files_record_step,
    make_delegate_repo,
    run_review_delegate,
    run_review_cli,
    set_delegate_steps,
)
from tests.review_repo_helpers import commit_file, git

from specy_road import worker_state as ws
from specy_road.bundled_scripts import worker_cli
from specy_road.bundled_scripts.worker_cli_render import usage, usage_lines
from specy_road.review_files import reviews_dir
from specy_road.review_usage import archive_round, review_usage
from specy_road.reviewer_run_failure import run_path, save_run
from specy_road.worker_adapter_parsers import USAGE_FIELDS

def _round(repo: Path, notes: str, **result) -> dict:
    """One round: the fake's result line carries ``result`` (usage, cost, turns), as Claude's stream-json does, and
    its final JSON carries ``notes``, which specy-road writes to ``notes-opus.md`` below the front matter (M8.3:
    the reviewer writes no file)."""
    step = files_record_step(repo)
    return {"answer": {**step["answer"], "notes": notes}, "say": "reviewing", "result": result}


def _notes(path: Path) -> str:
    """The reviewer's notes in a ``notes-<model>.md`` specy-road wrote: the text after its front matter."""
    return path.read_text().split("\n---\n", 1)[1].lstrip("\n")


@pytest.fixture()
def two_rounds(tmp_path: Path) -> tuple[Path, str, str]:
    repo, spec = make_delegate_repo(tmp_path)
    c1 = git(repo, "rev-parse", "HEAD")
    set_delegate_steps(repo, spec, _round(repo, "round one notes\n", usage={"input_tokens": 100, "output_tokens": 10},
                              total_cost_usd=0.5, num_turns=3))
    assert run_review_delegate(repo) == 0
    c2 = commit_file(repo, "src/a.py", "print('fixed')\n", "fix")
    set_delegate_steps(repo, spec, _round(repo, "round two notes\n", usage={"input_tokens": 200, "output_tokens": 20},
                              total_cost_usd=0.25, num_turns=2))
    assert run_review_delegate(repo) == 0
    return repo, c1, c2


def test_each_round_keeps_its_run_json_log_and_notes_in_history(two_rounds) -> None:
    """A1/A4: round 1's files are kept under history/ with its commit and round; the current files are round 2's."""
    repo, c1, c2 = two_rounds
    d = reviews_dir(repo, "M1.1")
    hist = d / "history"
    kept = json.loads((hist / f"RUN-opus-{c1[:12]}-1.json").read_text())
    assert kept["commit"] == c1 and kept["model"] == "opus"
    assert '"input_tokens": 100' in (hist / f"RUN-opus-{c1[:12]}-1.log").read_text()
    assert _notes(hist / "notes" / f"notes-opus-{c1[:12]}-1.md") == "round one notes\n"
    assert json.loads((d / "RUN-opus.json").read_text())["commit"] == c2
    current_log = (d / "RUN-opus.log").read_text()
    assert '"input_tokens": 200' in current_log and '"input_tokens": 100' not in current_log
    assert _notes(d / "notes-opus.md") == "round two notes\n"
    assert not list(hist.glob("notes-*.md"))   # never beside the filed records history/*.md holds


def test_review_usage_lists_each_run_and_the_total(two_rounds, capsys) -> None:
    """A2: per run (model, round, commit) and a total, --json and text; '?' where the harness reported nothing."""
    repo, c1, c2 = two_rounds
    capsys.readouterr()
    assert run_review_cli("review", "usage", "M1.1", "--json", "--repo-root", str(repo)) == 0
    data = json.loads(capsys.readouterr().out)
    assert [(r["model"], r["round"], r["commit"]) for r in data["runs"]] == [("opus", 1, c1), ("opus", 2, c2)]
    assert [(r["input_tokens"], r["output_tokens"], r["cost_usd"]) for r in data["runs"]] == [(100, 10, 0.5),
                                                                                              (200, 20, 0.25)]
    t = data["total"]
    assert (t["runs"], t["turns"], t["input_tokens"], t["output_tokens"], t["cost_usd"]) == (2, 2, 300, 30, 0.75)
    assert t["reasoning_tokens"] is None
    assert run_review_cli("review", "usage", "M1.1", "--repo-root", str(repo)) == 0
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
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        worker_cli.main(["worker", "usage", "M1.1", "--json", "--repo-root", str(repo)])
    assert (exc.value.code or 0) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["executors"]["input_tokens"] == 1000 and payload["reviewers"]["input_tokens"] == 300
    t = payload["total"]
    assert (t["turns"], t["input_tokens"], t["output_tokens"], t["cost_usd"]) == (3, 1300, 130, 1.75)


def test_notes_are_not_relabeled_when_a_later_run_writes_no_notes(tmp_path: Path) -> None:
    """A4/RC2: a capacity failure at a new commit must not archive the previous commit's notes under that run."""
    repo, spec = make_delegate_repo(tmp_path)
    c1_notes = "Only commit-one notes\n"
    set_delegate_steps(repo, spec, _round(repo, c1_notes, usage={"input_tokens": 100, "output_tokens": 10}, total_cost_usd=0.5))
    assert run_review_delegate(repo) == 0
    c1 = git(repo, "rev-parse", "HEAD")
    commit_file(repo, "src/a.py", "print('fixed')\n", "fix")
    c2 = git(repo, "rev-parse", "HEAD")
    set_delegate_steps(repo, spec, {"error": CAPACITY, "exit": 1})
    assert run_review_delegate(repo, "--retries", "0") == 1
    notes_hist = reviews_dir(repo, "M1.1") / "history" / "notes"
    assert _notes(notes_hist / f"notes-opus-{c1[:12]}-1.md") == c1_notes
    assert not list(notes_hist.glob(f"notes-opus-{c2[:12]}-*.md"))
    set_delegate_steps(repo, spec, _round(repo, "Commit-two retry notes\n", usage={"input_tokens": 50, "output_tokens": 5},
                              total_cost_usd=0.25))
    assert run_review_delegate(repo) == 0
    assert _notes(reviews_dir(repo, "M1.1") / "notes-opus.md") == "Commit-two retry notes\n"
    assert not any(_notes(p) == c1_notes for p in notes_hist.glob(f"notes-opus-{c2[:12]}-*.md"))


_PROMPT_CLI_USAGE_LOG = json.dumps({"type": "result", "subtype": "success", "result": "ok", "is_error": False,
                                   "usage": {"input_tokens": 900, "output_tokens": 90}, "total_cost_usd": 0.9}) + "\n"


def _write_prompt_cli_run(path: Path, commit: str) -> None:
    save_run(path, {"node_id": "M1.1", "model": path.stem.removeprefix("RUN-"), "harness": "claude-code",
                  "commit": commit, "state": "complete", "source": "prompt-cli", "resumed": False,
                  "log": str(path.with_suffix(".log"))})
    path.with_suffix(".log").write_text(_PROMPT_CLI_USAGE_LOG, encoding="utf-8")


def test_prompt_cli_runs_are_excluded_from_review_and_worker_usage(two_rounds, capsys) -> None:
    """A3/R1: ``source=prompt-cli`` RUN files in history and at the current path do not enter reviewer totals."""
    repo, c1, _c2 = two_rounds
    d, hist = reviews_dir(repo, "M1.1"), reviews_dir(repo, "M1.1") / "history"
    archived = hist / f"RUN-plain-{c1[:12]}-1.json"
    archived.write_text(json.dumps({"node_id": "M1.1", "model": "plain", "harness": "claude-code", "commit": c1,
                                    "state": "complete", "source": "prompt-cli", "resumed": False}), encoding="utf-8")
    archived.with_suffix(".log").write_text(_PROMPT_CLI_USAGE_LOG, encoding="utf-8")
    _write_prompt_cli_run(run_path(repo, "M1.1", "plain"), git(repo, "rev-parse", "HEAD"))
    data = review_usage(repo, "M1.1")
    assert [r["model"] for r in data["runs"]] == ["opus", "opus"]
    t = data["total"]
    assert (t["runs"], t["turns"], t["input_tokens"], t["output_tokens"], t["cost_usd"]) == (2, 2, 300, 30, 0.75)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    ws.append_event(repo, rec, "usage", source="worker", summary="usage",
                    detail={**dict.fromkeys(USAGE_FIELDS), "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.01})
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        worker_cli.main(["worker", "usage", "M1.1", "--json", "--repo-root", str(repo)])
    assert (exc.value.code or 0) == 0
    reviewers = json.loads(capsys.readouterr().out)["reviewers"]
    assert reviewers["runs"] == 2 and reviewers["input_tokens"] == 300
    assert archive_round(repo, "M1.1", "plain") is None


def test_archive_round_skips_the_current_run_when_it_is_not_review_delegate(tmp_path: Path) -> None:
    """R1: ``archive_round`` must not move a ``prompt-cli`` RUN into ``history/``."""
    repo, _spec = make_delegate_repo(tmp_path)
    _write_prompt_cli_run(run_path(repo, "M1.1", "opus"), git(repo, "rev-parse", "HEAD"))
    assert archive_round(repo, "M1.1", "opus") is None
    assert not list((reviews_dir(repo, "M1.1") / "history").glob("RUN-opus*"))
    assert not run_path(repo, "M1.1", "opus").with_suffix(".log").is_file()


def test_delegate_after_prompt_cli_does_not_append_to_the_old_log(tmp_path: Path) -> None:
    """A3: a ``prompt-cli`` log must not carry into the next ``review delegate`` run's usage."""
    repo, spec = make_delegate_repo(tmp_path)
    path = run_path(repo, "M1.1", "opus")
    _write_prompt_cli_run(path, git(repo, "rev-parse", "HEAD"))
    set_delegate_steps(repo, spec, _round(repo, "delegate notes\n", usage={"input_tokens": 10, "output_tokens": 1},
                                          total_cost_usd=0.1))
    assert run_review_delegate(repo) == 0
    data = review_usage(repo, "M1.1")
    assert len(data["runs"]) == 1 and data["runs"][0]["input_tokens"] == 10 and data["total"]["turns"] == 1
    assert "900" not in path.with_suffix(".log").read_text()
    assert not list((reviews_dir(repo, "M1.1") / "history").glob("RUN-opus*"))


def test_a_removed_worktree_still_finds_its_projects_reviews(two_rounds) -> None:
    """A finished leaf's worktree is gone; its nearest existing parent names the project."""
    repo, _c1, _c2 = two_rounds
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo / "work" / ".worktrees" / "gone")
    lines = usage_lines(usage([(rec, [])]))
    assert any(line.startswith("  reviewers, 2 run(s)") for line in lines)


def test_no_delegated_review_keeps_the_single_total_line(tmp_path: Path) -> None:
    repo, _spec = make_delegate_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    lines = usage_lines(usage([(rec, [])]))
    assert lines[-1] == "  total, 0 turn(s): in ? (? cached), out ?, reasoning ?, $?"
    assert not any("reviewers" in line or "executors" in line for line in lines)


def test_worker_usage_uses_its_repo_root_not_the_worktree(two_rounds, tmp_path_factory, capsys) -> None:
    """A3: ``worker usage --repo-root`` finds the reviewers even when the worker's worktree names no project."""
    repo, _c1, _c2 = two_rounds
    elsewhere = tmp_path_factory.mktemp("not-a-project")
    ws.create_record(repo, "M1.1", "claude-code", "opus", elsewhere)
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        worker_cli.main(["worker", "usage", "M1.1", "--repo-root", str(repo)])
    assert (exc.value.code or 0) == 0
    assert "  reviewers, 2 run(s), 2 turn(s):" in capsys.readouterr().out
