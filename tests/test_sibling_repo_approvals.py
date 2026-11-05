"""M14.1: approvals never carry across unreviewed changes in a sibling repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_cli import ONE_AI, _notes, _run, _status

from specy_road.bundled_scripts import validate_roadmap
from specy_road.review_bookkeeping import policy_line
from specy_road.review_files import load_ready, load_review, review_path, reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.sibling_repos import sibling_repos, warn_unconfigured_sibling_repos


def _sibling(repo: Path, rel: str = "app", ignore: bool = True) -> Path:
    """A separate git repository at ``rel`` under ``repo``, with one commit; ignored by ``repo`` by default."""
    sib = repo / rel
    sib.mkdir(parents=True)
    git(sib, "init", "-q", "-b", "main")
    git(sib, "config", "user.email", "t@e.com")
    git(sib, "config", "user.name", "T")
    commit_file(sib, "code.py", "x = 1\n", "sibling code")
    if ignore:
        with (repo / ".gitignore").open("a", encoding="utf-8") as f:
            f.write(f"{rel}/\n")
        commit_file(repo, ".gitignore", (repo / ".gitignore").read_text(), "ignore sibling")
    return sib


def _approve(repo: Path, model: str = "human", **extra) -> str:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = git(repo, "rev-parse", "HEAD")
    (d / f"REVIEW-{model}.md").write_text(review_text(commit, model=model, **extra))
    return commit


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))


def test_lists_siblings_with_head_and_dirty_and_skips_tracked_configured_and_deep(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    app = _sibling(repo, "app")
    lib = _sibling(repo, "libs/core", ignore=False)       # untracked, not ignored: still a sibling
    _sibling(repo, "a/b/too-deep")                       # three directories down: not searched
    _sibling(repo, "work/side")                          # runtime state: never searched
    _sibling(repo, "vendor/nested")                      # configured below: not a sibling
    commit_file(repo, "roadmap/git-workflow.yaml", (repo / "roadmap/git-workflow.yaml").read_text()
                + "nested_repos: [vendor/nested]\n", "configure nested")
    (lib / "code.py").write_text("x = 2\n")
    got = sibling_repos(repo)
    assert [(s.path, s.head, s.dirty) for s in got] == [
        ("app", git(app, "rev-parse", "HEAD"), False), ("libs/core", git(lib, "rev-parse", "HEAD"), True)]
    assert sibling_repos(tmp_path) == []                 # not a git checkout


def test_reported_case_sibling_code_and_root_summary_only_does_not_carry(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    sib = _sibling(repo)
    approved = _approve(repo)
    assert _gate(repo).passed
    commit_file(sib, "code.py", "x = 'unreviewed'\n", "rework in sibling only")
    commit_file(repo, "work/implementation-summary-M1.1.md", "# Summary\n\nReworked.\n", "summary only")
    g = _gate(repo)
    assert not g.passed and not g.bookkeeping_carry and len(g.stale) == 1
    st = _status(repo, capsys)
    assert not st["policy_met"]
    assert "still count" not in st["policy"]
    assert (f"human's approve at {approved[:12]} is stale: sibling repositories app are present and "
            "nested_repos does not configure them") in st["policy"]


def test_without_siblings_the_summary_only_carry_is_unchanged(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _approve(repo)
    commit_file(repo, "work/implementation-summary-M1.1.md", "# Summary\n", "summary only")
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry


def test_recorded_sibling_heads_must_still_hold_at_the_same_root_commit(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    sib = _sibling(repo)
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(_notes(repo)), "--repo-root", str(repo)) == 0
    rec = load_review(review_path(repo, "M1.1", "opus"))
    assert rec.ok, rec.errors
    assert rec.data["sibling_heads"] == {"app": git(sib, "rev-parse", "HEAD")}
    assert _gate(repo).passed
    (sib / "code.py").write_text("x = 'dirty'\n")
    assert not _gate(repo).passed                        # a sibling now dirty
    commit_file(sib, "code.py", "x = 'moved'\n", "sibling moves")
    g = _gate(repo)
    assert not g.passed and len(g.stale) == 1
    assert "sibling repositories changed since the review (app)" in policy_line(g)


def test_a_record_without_sibling_heads_counts_only_at_the_same_root_commit(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    sib = _sibling(repo)
    _approve(repo)
    commit_file(sib, "code.py", "x = 'moved'\n", "sibling moves")
    assert _gate(repo).passed                            # no recorded heads: same root commit counts, as before
    commit_file(repo, NODE["planning_dir"], "# M1.1 Thing\n\n## Intent\n\nNew.\n\n## References\n", "sheet")
    assert not _gate(repo).passed


def test_ready_writes_sibling_heads(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    sib = _sibling(repo)
    assert _run("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == 0
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["sibling_heads"] == {"app": git(sib, "rev-parse", "HEAD")}


def test_ready_without_siblings_writes_no_sibling_heads(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert _run("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == 0
    assert "sibling_heads" not in load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1").data


TWO_AI = """version: 1
policy: {reviewers_required: 1}
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: gpt, family: openai, roles: [reviewer]}
"""


def test_policy_line_lists_each_approval_and_marks_a_carried_one(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_AI)
    old = _approve(repo, "opus")
    commit_file(repo, "work/implementation-summary-M1.1.md", "# Summary\n", "summary only")
    new = _approve(repo, "gpt")
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry
    line = (f"2/1 approvals (gpt@{new[:12]}, opus@{old[:12]} carried from an older commit), 0 block(s): met; "
            "approvals still count")
    assert policy_line(g).startswith(line)
    assert _status(repo, capsys)["policy"].startswith(line)
    assert _run("handoff", "status", "M1.1", "--repo-root", str(repo)) == 0
    assert f"  policy: {line}" in capsys.readouterr().out


def test_review_record_prints_the_same_policy_line(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    capsys.readouterr()
    assert _run("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(_notes(repo)), "--repo-root", str(repo)) == 0
    head = git(repo, "rev-parse", "HEAD")
    assert f"policy: 1/1 approvals (opus@{head[:12]}), 0 block(s): met" in capsys.readouterr().out


@pytest.mark.parametrize("siblings", [0, 2])
def test_validate_warns_once_naming_the_siblings(tmp_path: Path, capsys, monkeypatch, siblings: int) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    for rel in ("app", "libs/core")[:siblings]:
        _sibling(repo, rel)
    calls = []
    monkeypatch.setattr(validate_roadmap, "warn_unconfigured_sibling_repos",
                        lambda root: calls.append(warn_unconfigured_sibling_repos(root)))
    validate_roadmap.validate_at(repo, auto_heal=False)
    err = capsys.readouterr().err
    lines = [ln for ln in err.splitlines() if "not configured in nested_repos" in ln]
    if siblings:
        assert calls == [["app", "libs/core"]] and len(lines) == 1
        assert "(app, libs/core)" in lines[0] and "docs/git-workflow.md" in lines[0] and "nested_repos" in lines[0]
    else:
        assert calls == [[]] and lines == []
