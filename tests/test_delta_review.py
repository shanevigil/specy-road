"""Delta review (policy.delta_review): a small fix round after an approval, reviewed from the change since."""

from __future__ import annotations

from pathlib import Path

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts.role_prompt import reviewer_packet
from specy_road.review_files import PACKET_NAME, archive_review, reviews_dir
from specy_road.review_gate import delta_basis, evaluate_gate, is_doc_or_test
from specy_road.review_target import resolve_target

ROSTER = """version: 1
roster:
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
policy: {reviewers_required: 2, reviewers_distinct_families: true%s}
"""
TEST_FILE = "src/tests/test_a.py"
TEST_SRC = "def test_a():\n    assert 1\n"


def _repo(tmp_path: Path, policy: str = "") -> tuple[Path, str]:
    """A claimed leaf whose tip ``P`` (returned) has ``src/tests/test_a.py``; opus approved ``P``."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER % policy)
    approved = commit_file(repo, TEST_FILE, TEST_SRC, "first round")
    _file(repo, "opus", approved)
    return repo, approved


def _file(repo: Path, model: str, commit: str, verdict: str = "approve", delta_from: str | None = None) -> None:
    """File a record as `review record` does: the live REVIEW-<model>.md plus a copy under history/."""
    text = review_text(commit, model=model, verdict=verdict, a1="pass" if verdict == "approve" else "fail")
    text = text.replace("notes\n", f"{model} notes on {commit[:7]}\n")
    if delta_from:
        text = text.replace("---\n", f"---\ndelta_from: '{delta_from}'\n", 1)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(text)
    archive_review(repo, "M1.1", model, text)


def _fix(repo: Path, files: dict[str, str]) -> str:
    for rel, text in files.items():
        commit_file(repo, rel, text, f"fix {rel}")
    return git(repo, "rev-parse", "HEAD")


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))


def _why(repo: Path, model: str) -> str:
    return " ".join(why for r, why in _gate(repo).ineligible if r.data["model"] == model)


def test_doc_and_test_paths() -> None:
    for p in ("docs/a.md", "README.rst", "src/tests/helpers.py", "pkg/x_test.go", "test_x.py", "web/a.spec.ts"):
        assert is_doc_or_test(p), p
    for p in ("src/a.py", "docs/conf.py", "src/testing.py", "roadmap/orchestration.yaml"):
        assert not is_doc_or_test(p), p


def test_an_eligible_delta_counts_for_the_approving_reviewer_and_both_families_are_still_needed(
        tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, {TEST_FILE: TEST_SRC + "\n\ndef test_b():\n    assert 2\n", "src/NOTES.md": "# n\n"})
    assert delta_basis(repo, NODE, "opus", head)[0].data["commit"] == approved
    _file(repo, "opus", head, delta_from=approved)
    g = _gate(repo)
    assert [a.model for a in g.approvals] == ["opus"] and not g.passed   # anthropic only
    _file(repo, "sol", head)   # a full review from the other family
    assert _gate(repo).passed


def test_a_delta_with_a_source_file_needs_a_full_review(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, {"src/b.py": "x = 1\n"})
    assert delta_basis(repo, NODE, "opus", head) == (None, "src/b.py is not a documentation or test file")
    _file(repo, "opus", head, delta_from=approved)
    assert "src/b.py is not a documentation or test file; a full review is needed" in _why(repo, "opus")
    assert not _gate(repo).approvals


def test_a_delta_over_three_files_needs_a_full_review(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, {f"src/docs/{i}.md": f"# {i}\n" for i in range(4)})
    assert delta_basis(repo, NODE, "opus", head) == (None, "the delta touches 4 files (at most 3)")
    _file(repo, "opus", head, delta_from=approved)
    assert "touches 4 files" in _why(repo, "opus")


def test_a_delta_with_an_integrity_finding_needs_a_full_review(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, {TEST_FILE: "def test_a():\n    pass\n"})   # the assert is gone
    prior, why = delta_basis(repo, NODE, "opus", head)
    assert prior is None and why.startswith("the delta's integrity report has findings (assert-loss:")
    _file(repo, "opus", head, delta_from=approved)
    assert "integrity report has findings" in _why(repo, "opus")


def test_a_reviewer_that_did_not_approve_the_earlier_commit_gets_no_delta(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    _file(repo, "sol", approved, verdict="block")
    head = _fix(repo, {"src/NOTES.md": "# n\n"})
    assert delta_basis(repo, NODE, "sol", head) == (None, "no earlier approval")
    _file(repo, "sol", head, delta_from=approved)
    assert f"a delta review from {approved}, which sol did not approve" in _why(repo, "sol")
    _file(repo, "sol", head)   # the same verdict from a full review counts
    assert [a.model for a in _gate(repo).approvals] == ["sol"]


def test_policy_off_forces_full_review(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path, ", delta_review: false")
    head = _fix(repo, {"src/NOTES.md": "# n\n"})
    assert delta_basis(repo, NODE, "opus", head) == (None, "policy.delta_review is off")
    _file(repo, "opus", head, delta_from=approved)
    assert "policy.delta_review is off" in _why(repo, "opus")
    rp.main(["M1.1", "--repo-root", str(repo)])
    t = resolve_target(repo, "M1.1")
    assert reviewer_packet(repo, "M1.1", "opus", t)[0] == (reviews_dir(repo, "M1.1") / PACKET_NAME).read_text()


def test_the_prompt_hands_each_reviewer_its_own_packet(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, {"src/NOTES.md": "# n\n"})
    rp.main(["M1.1", "--repo-root", str(repo)])
    t = resolve_target(repo, "M1.1")
    full = (reviews_dir(repo, "M1.1") / PACKET_NAME).read_text()
    delta, _ = reviewer_packet(repo, "M1.1", "opus", t)
    assert delta == (reviews_dir(repo, "M1.1") / "PACKET-opus.md").read_text()
    assert f"**Commit under review:** `{head}`" in delta and f"**Base:** `{approved}`" in delta
    assert f'`delta_from: "{approved}"`' in delta and f"opus notes on {approved[:7]}" in delta
    assert "- `src/NOTES.md`\n" in delta and "+print('a')" not in delta   # only the change since
    assert "+print('a')" in full and "## Delta review" not in full
    assert reviewer_packet(repo, "M1.1", "sol", t)[0] == full   # sol approved nothing
    assert not (reviews_dir(repo, "M1.1") / "PACKET-sol.md").exists()


def test_review_packet_full_stops_delta_packets(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    _fix(repo, {"src/NOTES.md": "# n\n"})
    (reviews_dir(repo, "M1.1") / "PACKET-opus.md").write_text("stale")
    rp.main(["M1.1", "--full", "--repo-root", str(repo)])
    full = (reviews_dir(repo, "M1.1") / PACKET_NAME).read_text()
    assert rp.FULL_MARK in full
    assert reviewer_packet(repo, "M1.1", "opus", resolve_target(repo, "M1.1"))[0] == full
    assert not (reviews_dir(repo, "M1.1") / "PACKET-opus.md").exists()
