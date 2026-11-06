"""Tests for `specy-road handoff status`, `specy-road review record` and `specy-road review list`."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, diverge, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

# One AI reviewer beside the default human: `review record` refuses `human`.
ONE_AI = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
"""

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import load_review, review_path, reviews_dir
from specy_road.review_rejected import rejected_path


def _run(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def _ready(repo: Path, commit: str | None = None) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = commit or git(repo, "rev-parse", "HEAD")
    (d / "READY-composer.md").write_text(
        f"---\nnode_id: M1.1\nagent: composer\nbranch: feature/rm-thing\ncommit: {commit}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n"
    )


def _notes(repo: Path, model: str = "opus", **kw) -> Path:
    p = repo.parent / f"notes-{model}.md"
    p.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, **kw))
    return p


def _status(repo: Path, capsys) -> dict:
    """One node's status; its exit is 0 when the gate is met and 1 when it is not."""
    capsys.readouterr()
    code = _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert code == (0 if st["policy_met"] else 1), st["state"]
    return st


def test_status_walks_waiting_review_approved_stale(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _status(repo, capsys)["state"] == "waiting"
    _ready(repo)
    assert _status(repo, capsys)["state"] == "in-review"
    notes = _notes(repo)
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    st = _status(repo, capsys)
    assert st["state"] == "approved" and st["policy_met"]
    commit_file(repo, "src/b.py", "x\n", "fix")
    st = _status(repo, capsys)
    assert st["state"] == "stale" and not st["policy_met"]


def test_status_blocked_and_text_output(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo)
    notes = _notes(repo, verdict="block", a1="fail")
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    assert _status(repo, capsys)["state"] == "blocked"
    assert _run("handoff", "status", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "M1.1: blocked" in out
    assert "REVIEW-opus.md: block by opus (anthropic)" in out


def test_status_with_no_handoffs(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _run("handoff", "status", "--repo-root", str(repo)) == 0
    assert "No hand-offs" in capsys.readouterr().out


def test_record_fills_family_and_labels_independence(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    for model in ("opus", "sonnet"):
        assert _run("review", "record", "M1.1", "--model", model, "--verdict", "approve",
                    "--file", str(_notes(repo, model)), "--repo-root", str(repo)) == 0
    sonnet = load_review(review_path(repo, "M1.1", "sonnet"))
    assert sonnet.data["family"] == "anthropic"
    assert sonnet.data["independence"] == "same-family"
    assert "less independent" in capsys.readouterr().out


def test_record_refuses_a_stale_commit(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    notes = _notes(repo)
    commit_file(repo, "src/b.py", "x\n", "fix")
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 1
    assert "Re-review the current commit" in capsys.readouterr().err
    assert not review_path(repo, "M1.1", "opus").exists()


def test_record_overwrites_bogus_toolkit_version_in_notes(tmp_path: Path, capsys) -> None:
    from specy_road.toolkit_version import running_toolkit_version

    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo)
    notes = _notes(repo, toolkit_version="bogus")
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes), "--repo-root", str(repo)) == 0
    filed = load_review(review_path(repo, "M1.1", "opus"))
    assert filed.ok
    assert filed.data["toolkit_version"] == running_toolkit_version()
    assert filed.data["toolkit_version"] != "bogus"


def test_record_refuses_mismatched_flags_and_invalid_notes(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    notes = _notes(repo)
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 1
    assert "verdict is 'approve'" in capsys.readouterr().err
    bad = _notes(repo, a1="fail")
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(bad), "--repo-root", str(repo)) == 1
    assert "failing acceptance A1" in capsys.readouterr().err


def test_record_refuses_unrostered_models_and_human(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    assert _run("review", "record", "M1.1", "--model", "sol", "--verdict", "approve",
                "--file", str(_notes(repo, "sol")), "--repo-root", str(repo)) == 1
    assert "not in the roster" in capsys.readouterr().err
    assert not rejected_path(reviews, "sol").exists()
    assert _run("review", "record", "M1.1", "--model", "human", "--verdict", "approve",
                "--file", str(_notes(repo, "human")), "--repo-root", str(repo)) == 1
    assert "interactive approve" in capsys.readouterr().err
    assert rejected_path(reviews, "human").is_file()


def test_counted_reviews_outrank_a_stale_ready_file(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo)
    commit_file(repo, "src/b.py", "x\n", "follow-up")
    assert _status(repo, capsys)["state"] == "stale"
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(_notes(repo)), "--repo-root", str(repo)) == 0
    assert _status(repo, capsys)["state"] == "approved"


def _drop_claim(repo: Path) -> None:
    (repo / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")


def test_records_without_a_claim_are_listed_with_their_verdicts(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _ready(repo)
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(_notes(repo)), "--repo-root", str(repo)) == 0
    _drop_claim(repo)
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 2   # no commit: undeterminable
    out = capsys.readouterr().out
    assert "M1.1: unclaimed — no commit under review" in out
    assert "READY-composer.md (ok)" in out
    assert "REVIEW-opus.md: approve by opus (anthropic)" in out
    assert "--ref <branch>" in out and "do-next-available-task --under M1.1 --local" in out
    assert "leftover" not in out and "--under M1.1`" not in out
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--ref", "feature/rm-thing", "--json",
                "--repo-root", str(repo)) == 0
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert st["state"] == "approved" and st["policy_met"]
    assert _run("handoff", "status", "--ref", "feature/rm-thing", "--repo-root", str(repo)) == 2


def _complete(repo: Path) -> None:
    _drop_claim(repo)
    (repo / "roadmap" / "phases" / "M1.json").write_text(json.dumps({"nodes": [{**NODE, "status": "Complete"}]}))


def test_a_complete_node_without_a_claim_exits_0(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(_notes(repo)), "--repo-root", str(repo)) == 0
    _complete(repo)
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "M1.1: complete_no_claim — no commit under review" in out
    assert "REVIEW-opus.md: approve by opus (anthropic)" in out
    assert "--ref <branch or commit>" in out and "do-next-available-task" not in out
    assert _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out)["nodes"][0]["state"] == "complete_no_claim"


def test_review_list_prints_records_and_the_gate_and_writes_nothing(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(_notes(repo)), "--repo-root", str(repo)) == 0
    d = reviews_dir(repo, "M1.1")
    before = {p.relative_to(d): p.read_text() for p in d.rglob("*") if p.is_file()}
    head = git(repo, "rev-parse", "HEAD")
    capsys.readouterr()
    assert _run("review", "list", "M1.1", "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert f"REVIEW-opus.md: approve by opus (anthropic) at {head[:12]}" in out
    assert f"gate at feature/rm-thing @ {head[:12]}: 1/1 approvals, 0 block(s): met" in out
    _complete(repo)
    assert _run("review", "list", "M1.1", "--repo-root", str(repo)) == 0
    assert "gate: not evaluated" in capsys.readouterr().out
    assert _run("review", "list", "M1.1", "--ref", "feature/rm-thing", "--repo-root", str(repo)) == 0
    assert "1/1 approvals, 0 block(s): met" in capsys.readouterr().out
    assert {p.relative_to(d): p.read_text() for p in d.rglob("*") if p.is_file()} == before


def test_no_claim_and_no_records_is_an_empty_directory(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews_dir(repo, "M1.1").mkdir(parents=True)
    _drop_claim(repo)
    capsys.readouterr()
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 2
    out = capsys.readouterr().out
    assert "no READY or REVIEW records; the directory can be deleted" in out
    assert "do-next-available-task" not in out


@pytest.mark.parametrize("case, line", [
    ("clean", None),
    ("bookkeeping", f"  trial merge with refs/heads/dev: conflicts on {NODE['planning_dir']} "
                    "(bookkeeping only, which does not block)"),
    ("code", "  trial merge with refs/heads/dev: conflicts on src/a.py"),
])
def test_status_reports_a_trial_merge_conflict(tmp_path: Path, capsys, case: str, line: str | None) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    path = diverge(repo, case)
    st = _status(repo, capsys)
    merge = [p for p in st["problems"] if "trial merge" in p]
    assert merge == (["refs/heads/dev is 1 commit(s) ahead and a trial merge conflicts on src/a.py: "
                      "merge it into this branch and resolve before review"] if case == "code" else [])
    assert st["trial_merge"] == (None if case == "clean" else {
        "ref": "refs/heads/dev", "behind": 1, "conflicts": [path], "blocking": [path] if case == "code" else []})
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    text = capsys.readouterr().out.splitlines()
    assert [t for t in text if t.startswith("  trial merge")] == ([line] if line else [])


def _record(repo: Path, verdict: str = "approve", **kw) -> None:
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", verdict,
                "--file", str(_notes(repo, verdict=verdict, **kw)), "--repo-root", str(repo)) == 0


def _rounds_lines(repo: Path, capsys) -> tuple[dict, list[str], list[str]]:
    """``review_rounds`` from ``handoff status --json``, and the rounds line of each text command."""
    capsys.readouterr()
    _run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    span = json.loads(capsys.readouterr().out)["nodes"][0]["review_rounds"]
    _run("handoff", "status", "M1.1", "--repo-root", str(repo))
    status = [t for t in capsys.readouterr().out.splitlines() if "rounds:" in t]
    _run("review", "list", "M1.1", "--repo-root", str(repo))
    listed = [t for t in capsys.readouterr().out.splitlines() if "rounds:" in t]
    return span, status, listed


def test_rounds_and_elapsed_time_count_distinct_reviewed_commits(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _record(repo, "block", a1="fail")
    commit_file(repo, "src/b.py", "x\n", "fix")
    _record(repo)
    d = reviews_dir(repo, "M1.1")
    first, latest = sorted((d / "history").glob("*.md"))
    now = time.time()
    os.utime(first, (now, now - (27 * 3600 + 5 * 60)))
    os.utime(latest, (now, now - 3600))
    os.utime(d / "REVIEW-opus.md", (now, now - 40 * 3600))   # the live copy of `latest`: not counted twice

    span, status, listed = _rounds_lines(repo, capsys)

    line = "rounds: 2, first to latest: 1d 2h 5m"
    assert span == {"rounds": 2, "elapsed_seconds": 26 * 3600 + 5 * 60, "line": line}
    assert status == [f"  {line}"]
    assert listed == [line]


def test_a_single_review_has_no_elapsed_time(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    span, status, listed = _rounds_lines(repo, capsys)
    assert (span["rounds"], status, listed) == (0, ["  rounds: 0, first to latest: n/a"],
                                                ["rounds: 0, first to latest: n/a"])
    _record(repo)

    span, status, listed = _rounds_lines(repo, capsys)

    assert span["rounds"] == 1 and span["elapsed_seconds"] is None
    assert status == ["  rounds: 1, first to latest: n/a"]
    assert listed == ["rounds: 1, first to latest: n/a"]


def test_a_review_with_no_history_copy_counts_and_a_short_sha_is_the_same_round(
    tmp_path: Path, capsys
) -> None:
    """``REVIEW-human.md`` is written without a ``history/`` copy; it quotes a short SHA here."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _record(repo)
    head = git(repo, "rev-parse", "HEAD")
    (reviews_dir(repo, "M1.1") / "REVIEW-human.md").write_text(review_text(head[:7]))

    span, status, _listed = _rounds_lines(repo, capsys)

    assert span["rounds"] == 1 and span["elapsed_seconds"] is not None
    assert status == ["  rounds: 1, first to latest: under 1m"]
