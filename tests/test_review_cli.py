"""Tests for `specy-road handoff status` and `specy-road review record`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

# One AI reviewer beside the default human: `review record` refuses `human`.
ONE_AI = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
"""

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import load_review, review_path, reviews_dir


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
    assert _run("review", "record", "M1.1", "--model", "sol", "--verdict", "approve",
                "--file", str(_notes(repo, "sol")), "--repo-root", str(repo)) == 1
    assert "not in the roster" in capsys.readouterr().err
    assert _run("review", "record", "M1.1", "--model", "human", "--verdict", "approve",
                "--file", str(_notes(repo, "human")), "--repo-root", str(repo)) == 1
    assert "interactive approve" in capsys.readouterr().err
    assert not reviews_dir(repo, "M1.1").exists()


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
