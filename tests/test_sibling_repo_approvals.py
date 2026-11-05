"""M14.1: approvals never carry across unreviewed changes in a sibling repository."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.review_delegate_helpers import handoff_status_node, run_review_cli
from tests.test_review_cli import ONE_AI

from specy_road.bundled_scripts import validate_roadmap
from specy_road.review_bookkeeping import policy_line
from specy_road.review_files import load_ready, load_review, review_path, reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.sibling_repos import sibling_repos


def _glob_escaped(rel: str) -> str:
    """``rel`` as a ``.gitignore`` pattern that matches only itself."""
    return "".join(f"\\{c}" if c in "[]*?" else c for c in rel)


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
            f.write(f"{_glob_escaped(rel)}/\n")
        commit_file(repo, ".gitignore", (repo / ".gitignore").read_text(), "ignore sibling")
    return sib


def _approve(repo: Path, model: str = "human", **extra) -> str:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = git(repo, "rev-parse", "HEAD")
    (d / f"REVIEW-{model}.md").write_text(review_text(commit, model=model, **extra))
    return commit


def notes_file(repo: Path, model: str = "opus") -> Path:
    """Reviewer notes for ``model`` at ``HEAD``, outside the repository, for ``review record --file``."""
    p = repo.parent / f"notes-{model}.md"
    p.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model))
    return p


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
    st = handoff_status_node(repo, capsys)
    assert not st["policy_met"]
    assert run_review_cli("handoff", "status", "M1.1", "--repo-root", str(repo)) == 1
    assert "still count" not in st["policy"]
    assert (f"human's approve at {approved[:12]} is stale: sibling repositories app are present and "
            "nested_repos does not configure them") in st["policy"]


def test_recorded_sibling_heads_must_still_hold_at_the_same_root_commit(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    sib = _sibling(repo)
    assert run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes_file(repo)), "--repo-root", str(repo)) == 0
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


def _change_siblings(repo: Path, change: str) -> None:
    sib = repo / "app"
    if change == "added":
        _sibling(repo, "libs/new", ignore=False)
    elif change == "removed":
        shutil.rmtree(sib)
    elif change == "moved":
        commit_file(sib, "code.py", "x = 'moved'\n", "sibling moves")
    elif change == "renamed":
        sib.rename(repo / "app2")


@pytest.mark.parametrize("root", ["same", "summary-only"])
@pytest.mark.parametrize("change", ["unchanged", "added", "removed", "moved", "renamed"])
def test_an_approval_counts_only_while_the_recorded_sibling_map_holds(tmp_path: Path, change: str, root: str) -> None:
    """The full sibling map (which siblings, each HEAD) must equal the recorded one on every count and carry path;
    with siblings still present the summary-only carry never applies (A2), so only unchanged at the same commit counts."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _sibling(repo)
    assert run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                          "--file", str(notes_file(repo)), "--repo-root", str(repo)) == 0
    approved = git(repo, "rev-parse", "HEAD")
    assert _gate(repo).passed
    _change_siblings(repo, change)
    if root == "summary-only":
        commit_file(repo, "work/implementation-summary-M1.1.md", "# Summary\n", "summary only")
    g = _gate(repo)
    counts = change == "unchanged" and root == "same"
    assert g.passed is counts and len(g.stale) == (0 if counts else 1) and not g.bookkeeping_carry
    if change != "unchanged":
        assert f"opus's approve at {approved[:12]} is stale: sibling repositories changed since the review" \
            in policy_line(g)


def test_a_record_without_sibling_heads_carries_when_no_sibling_remains(tmp_path: Path) -> None:
    """The legacy rule: no recorded map is not checked, and with no siblings left the summary-only carry applies."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    _sibling(repo)
    _approve(repo)
    shutil.rmtree(repo / "app")
    commit_file(repo, "work/implementation-summary-M1.1.md", "# Summary\n", "summary only")
    g = _gate(repo)
    assert g.passed and g.bookkeeping_carry


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
    assert run_review_cli("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == 0
    r = load_ready(reviews_dir(repo, "M1.1") / "READY-opus.md", "M1.1", "feature/rm-thing")
    assert r.ok, r.errors
    assert r.data["sibling_heads"] == {"app": git(sib, "rev-parse", "HEAD")}


def test_ready_without_siblings_writes_no_sibling_heads(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    assert run_review_cli("ready", "M1.1", "--model", "opus", "--verify", "true=0", "--repo-root", str(repo)) == 0
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
    assert handoff_status_node(repo, capsys)["policy"].startswith(line)
    assert run_review_cli("handoff", "status", "M1.1", "--repo-root", str(repo)) == 0
    assert f"  policy: {line}" in capsys.readouterr().out


def test_review_record_prints_the_same_policy_line(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    capsys.readouterr()
    assert run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                "--file", str(notes_file(repo)), "--repo-root", str(repo)) == 0
    head = git(repo, "rev-parse", "HEAD")
    assert f"policy: 1/1 approvals (opus@{head[:12]}), 0 block(s): met" in capsys.readouterr().out


@pytest.mark.parametrize("siblings", [0, 2])
def test_validate_warns_once_naming_the_siblings(tmp_path: Path, capsys, siblings: int) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    for rel in ("app", "libs/core")[:siblings]:
        _sibling(repo, rel)
    capsys.readouterr()
    validate_roadmap.validate_at(repo, auto_heal=False)
    lines = [ln for ln in capsys.readouterr().err.splitlines() if "not configured in nested_repos" in ln]
    if siblings:
        assert len(lines) == 1
        assert "(app, libs/core)" in lines[0] and "docs/git-workflow.md" in lines[0] and "nested_repos" in lines[0]
    else:
        assert lines == []


@pytest.mark.parametrize("name, tracked", [("app[1]", "app1"), ("app*", "appx/kept.txt"), ("app?", "appz"),
                                           ("[ab]", "a")])
def test_a_sibling_named_with_glob_characters_beside_a_tracked_match(tmp_path: Path, capsys, name: str,
                                                                     tracked: str) -> None:
    """A tracked path the sibling's name would match as a glob does not hide the sibling (F1, fix round 3)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    commit_file(repo, tracked, "tracked\n", "a tracked path the name matches as a glob")
    sib = _sibling(repo, name)
    assert [(s.path, s.head) for s in sibling_repos(repo)] == [(name, git(sib, "rev-parse", "HEAD"))]
    assert run_review_cli("review", "record", "M1.1", "--model", "opus", "--verdict", "approve",
                          "--file", str(notes_file(repo)), "--repo-root", str(repo)) == 0
    assert load_review(review_path(repo, "M1.1", "opus")).data["sibling_heads"] == {name: git(sib, "rev-parse", "HEAD")}
    capsys.readouterr()
    validate_roadmap.validate_at(repo, auto_heal=False)
    lines = [ln for ln in capsys.readouterr().err.splitlines() if "not configured in nested_repos" in ln]
    assert len(lines) == 1 and f"({name})" in lines[0]
    commit_file(sib, "code.py", "x = 'unreviewed'\n", "rework in sibling only")
    commit_file(repo, "work/implementation-summary-M1.1.md", "# Summary\n", "summary only")
    g = _gate(repo)
    assert not g.passed and len(g.stale) == 1


def test_a_tracked_and_ignored_directory_repository_is_a_sibling(tmp_path: Path) -> None:
    """A1's 'ignores or does not track': a directory the root tracked, then made its own repository and ignored."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    commit_file(repo, "app/.keep", "", "tracked before it became a repository")
    git(repo / "app", "init", "-q", "-b", "main")
    commit_file(repo, ".gitignore", (repo / ".gitignore").read_text() + "app/\n", "ignore it")
    assert git(repo, "ls-files", "app")                  # the root still tracks a path there
    assert [s.path for s in sibling_repos(repo)] == ["app"]


def test_a_seven_character_legacy_commit_shows_twelve_characters(tmp_path: Path, capsys) -> None:
    """A counted record whose commit is abbreviated is resolved before the policy line shows it (F2, fix round 3)."""
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    full = git(repo, "rev-parse", "HEAD")
    _approve(repo, "opus")
    p = review_path(repo, "M1.1", "opus")
    p.write_text(p.read_text().replace(full, full[:7]))
    g = _gate(repo)
    assert g.passed
    assert policy_line(g).startswith(f"1/1 approvals (opus@{full[:12]}), 0 block(s): met")
    assert handoff_status_node(repo, capsys)["policy"].startswith(f"1/1 approvals (opus@{full[:12]})")


def test_a_record_whose_commit_does_not_resolve_says_so(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ONE_AI)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "REVIEW-opus.md").write_text(review_text("deadbee", model="opus"))
    g = _gate(repo)
    assert not g.passed and len(g.stale) == 1
    assert "opus's approve at deadbee (not a commit in this repository) is stale: re-review" in policy_line(g)
