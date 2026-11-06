"""M15.33: a refused ``review record`` leaves ``REJECTED-<model>.md`` until a record is filed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_delegate_helpers import delegate_repo, run_review_cli, set_steps, verdict_step
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_output, review_text
from tests.test_review_cli import ONE_AI

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import list_reviews, reviews_dir
from specy_road.review_rejected import rejected_path, write_rejected


def _record(repo: Path, verdict: str = "approve", findings: dict | None = None, notes: str = "notes\n",
            model: str = "opus") -> int:
    text = review_text(git(repo, "rev-parse", "HEAD"), model=model, verdict=verdict)
    data = yaml.safe_load(text.split("---")[1])
    data["findings"].update(findings or {})
    p = repo.parent / f"notes-{model}.md"
    p.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n" + notes)
    return run_review_cli("review", "record", "M1.1", "--model", model, "--verdict", verdict, "--file", str(p),
                          "--repo-root", str(repo))


def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    run_review_cli("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)["nodes"][0]


def _list_json(repo: Path, capsys) -> dict:
    capsys.readouterr()
    run_review_cli("review", "list", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)


def test_list_reviews_ignores_a_rejected_marker(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    head = git(repo, "rev-parse", "HEAD")
    write_rejected(reviews, "opus", head, "error: notes line 3 says \"Advisory\"")
    assert list_reviews(repo, "M1.1") == []


def test_record_refusal_writes_marker_and_success_clears_it(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    assert _record(repo, findings={"correctness": ["Advisory: x drops y"]}) == 1
    marker = rejected_path(reviews, "opus")
    assert marker.is_file()
    data, body = marker.read_text(encoding="utf-8").split("---\n", 2)[1:]
    front = yaml.safe_load(data)
    assert front["commit"] == git(repo, "rev-parse", "HEAD") and front.get("refused_at")
    assert "Advisory" in body
    assert _record(repo) == 0
    assert not marker.exists()


def test_roster_miss_does_not_write_a_marker(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    p = repo.parent / "notes.md"
    p.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="not-on-roster"))
    assert run_review_cli("review", "record", "M1.1", "--model", "not-on-roster", "--verdict", "approve",
                          "--file", str(p), "--repo-root", str(repo)) == 1
    assert not rejected_path(reviews, "not-on-roster").exists()


def test_unrostered_model_with_missing_notes_writes_no_marker(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    missing = repo / "no-such-notes.md"
    assert run_review_cli("review", "record", "M1.1", "--model", "ghost", "--verdict", "approve",
                          "--file", str(missing), "--repo-root", str(repo)) == 1
    assert not rejected_path(reviews, "ghost").exists()
    assert not list(reviews.glob("REVIEW-*"))   # the leaf's review lock file (M21.27) may be there; no record is


def test_handoff_status_and_list_show_refused_text_and_json(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    stale = review_text(git(repo, "rev-parse", "HEAD~1"), model="opus")
    p = repo.parent / "notes-opus.md"
    p.write_text(stale)
    assert run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve", "--file", str(p),
                          "--repo-root", str(repo)) == 1
    st = _status(repo, capsys)
    assert "Re-review the current commit" in st["refused"]["opus"]["reason"]
    assert "age" in st["refused"]["opus"]
    listed = _list_json(repo, capsys)
    assert listed["refused"]["opus"]["reason"] == st["refused"]["opus"]["reason"]
    run_review_cli("handoff", "status", "M1.1", "--repo-root", str(repo))
    text = capsys.readouterr().out
    assert "record refused" in text and "Re-review the current commit" in text
    capsys.readouterr()
    run_review_cli("review", "list", "M1.1", "--repo-root", str(repo))
    assert "REJECTED-opus.md: record refused" in capsys.readouterr().out


def test_marker_at_another_commit_is_not_shown(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _record(repo, notes="A1 pass.\n\nNon-blocking nit: one.\n") == 1
    commit_file(repo, "src/a.py", (repo / "src" / "a.py").read_text() + "\n", "bump")
    st = _status(repo, capsys)
    assert not st.get("refused")


def test_delegated_refusal_writes_the_same_marker(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    stale = review_output(git(repo, "rev-parse", "HEAD~1"), model="opus")
    set_steps(repo, spec, {"answer": stale})
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--retries", "0",
                         "--repo-root", str(repo)])
    assert e.value.code == 1
    assert rejected_path(reviews_dir(repo, "M1.1"), "opus").is_file()


def test_malformed_rejected_marker_is_reported_without_breaking_list(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    bad = reviews / "REJECTED-opus.md"
    bad.write_text("---\n[one, two]\n---\nstill here\n")
    run_review_cli("review", "list", "M1.1", "--repo-root", str(repo))
    assert f"marker unreadable: {bad}" in capsys.readouterr().out
    capsys.readouterr()
    run_review_cli("handoff", "status", "M1.1", "--repo-root", str(repo))
    assert f"marker unreadable: {bad}" in capsys.readouterr().out


def test_review_list_json_exits_nonzero_on_target_resolution_errors(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    capsys.readouterr()
    assert run_review_cli("review", "list", "M9.9", "--json", "--repo-root", str(repo)) == 1
    out = capsys.readouterr()
    assert "unknown node" in out.err.lower()
    assert json.loads(out.out)["error"]
    capsys.readouterr()
    assert run_review_cli("review", "list", "M1.1", "--ref", "not-a-valid-ref", "--json",
                          "--repo-root", str(repo)) == 1
    out = capsys.readouterr()
    assert out.err.startswith("error:")
    assert json.loads(out.out)["error"]


def test_a_lowercase_review_record_suppresses_the_refusal(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    head = git(repo, "rev-parse", "HEAD")
    write_rejected(reviews, "opus", head, "error: still blocked")
    (reviews / "review-opus.md").write_text(review_text(head, model="opus"), encoding="utf-8")
    st = _status(repo, capsys)
    assert not st.get("refused")
    listed = _list_json(repo, capsys)
    assert not listed.get("refused")


def test_invalid_utf8_rejected_marker_is_unreadable_in_status_interfaces(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    reviews = reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    bad = reviews / "REJECTED-opus.md"
    bad.write_bytes(b"---\ncommit: abc\nrefused_at: 2026-01-01T00:00:00+00:00\n---\n\xff\xfe\n")
    line = f"marker unreadable: {bad}"
    run_review_cli("review", "list", "M1.1", "--repo-root", str(repo))
    assert line in capsys.readouterr().out
    capsys.readouterr()
    run_review_cli("handoff", "status", "M1.1", "--repo-root", str(repo))
    assert line in capsys.readouterr().out
    listed = _list_json(repo, capsys)
    assert line in listed["refused_unreadable"]
