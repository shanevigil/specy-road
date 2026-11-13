"""Delta review (policy.delta_review): a small fix round after an approval, reviewed from the change since."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest
import yaml

from tests.review_repo_helpers import NODE, advance_dev, commit_file, git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli, review_packet as rp
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


def _file(repo: Path, model: str, commit: str, verdict: str = "approve", delta_from: str | None = None,
          drop: str | None = None, findings: dict | None = None) -> None:
    """File a record as `review record` does: the live REVIEW-<model>.md plus a copy under history/.
    ``drop`` leaves out that acceptance id's result, so the record is incomplete for the brief."""
    found = {"correctness": [], "regression": [], "boundary": [], "test_integrity": [], **(findings or {})}
    text = review_text(commit, model=model, verdict=verdict, a1="pass" if verdict == "approve" else "fail",
                       findings=found)
    text = text.replace("notes\n", f"{model} notes on {commit[:7]}\n")
    if drop:
        text = text.replace(f"  {drop}: pass\n", "")
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


def test_an_ineligible_delta_approval_is_no_basis_for_a_later_delta(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)   # a full approval of P
    c1 = _fix(repo, {"src/b.py": "x = 1\n"})   # a source file: this delta approval never counted
    _file(repo, "opus", c1, delta_from=approved)
    c2 = _fix(repo, {"src/NOTES.md": "# n\n"})   # docs only
    # The basis is P, not C1: from C1 the docs-only change would qualify and hide src/b.py.
    assert delta_basis(repo, NODE, "opus", c2) == (None, "src/b.py is not a documentation or test file")
    _file(repo, "opus", c2, delta_from=c1)
    assert f"a delta review from {c1}, which opus did not approve" in _why(repo, "opus")
    assert not _gate(repo).approvals


def test_an_earlier_approval_missing_an_acceptance_result_is_no_delta_basis(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER % "")
    approved = commit_file(repo, TEST_FILE, TEST_SRC, "first round")
    _file(repo, "opus", approved, drop="A2")   # would not have counted at its own commit
    head = _fix(repo, {"src/NOTES.md": "# n\n"})
    assert delta_basis(repo, NODE, "opus", head) == (None, "no earlier approval")
    rp.main(["M1.1", "--repo-root", str(repo)])
    packet, _ = reviewer_packet(repo, "M1.1", "opus", resolve_target(repo, "M1.1"))
    assert packet == (reviews_dir(repo, "M1.1") / PACKET_NAME).read_text()   # no delta packet
    _file(repo, "opus", head, delta_from=approved)
    assert f"a delta review from {approved}, which opus did not approve" in _why(repo, "opus")
    assert not _gate(repo).approvals


def test_the_gate_refuses_a_delta_approval_while_review_packet_full_is_current(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)
    head = _fix(repo, {"src/NOTES.md": "# n\n"})
    _file(repo, "opus", head, delta_from=approved)
    assert [a.model for a in _gate(repo).approvals] == ["opus"]
    rp.main(["M1.1", "--full", "--repo-root", str(repo)])
    assert f"`review packet --full` forces a full review of {head}" in _why(repo, "opus")
    assert not _gate(repo).approvals
    rp.main(["M1.1", "--repo-root", str(repo)])   # the override is the current packet's, not sticky
    assert [a.model for a in _gate(repo).approvals] == ["opus"]


def test_a_later_block_rescinds_an_approval_as_delta_basis_and_a_later_approval_restores_it(
        tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)   # opus approves P ...
    _file(repo, "opus", approved, verdict="block")   # ... then blocks P
    head = _fix(repo, {"src/NOTES.md": "# n\n"})
    assert delta_basis(repo, NODE, "opus", head) == (None, "no earlier approval")
    _file(repo, "opus", head, delta_from=approved)
    assert f"a delta review from {approved}, which opus did not approve" in _why(repo, "opus")
    assert not _gate(repo).approvals
    _file(repo, "opus", approved)   # approves P again: the basis is back
    assert delta_basis(repo, NODE, "opus", head)[0].data["commit"] == approved
    _file(repo, "opus", head, delta_from=approved)
    assert [a.model for a in _gate(repo).approvals] == ["opus"]


def test_a_delta_approval_stops_counting_when_its_basis_does_and_comes_back_with_it(tmp_path: Path) -> None:
    repo, approved = _repo(tmp_path)   # opus approves P
    c1 = _fix(repo, {"src/NOTES.md": "# n\n"})
    _file(repo, "opus", c1, delta_from=approved)   # a delta approval of C1 from P
    _file(repo, "opus", approved, verdict="block")   # P no longer counts, so neither does C1
    c2 = _fix(repo, {"src/MORE.md": "# m\n"})
    assert delta_basis(repo, NODE, "opus", c2) == (None, "no earlier approval")   # C1 is no basis
    _file(repo, "opus", c2, delta_from=c1)
    assert f"a delta review from {c1}, which opus did not approve" in _why(repo, "opus")
    assert not _gate(repo).approvals
    _file(repo, "opus", approved)   # an eligible approval of P again restores the chain
    assert delta_basis(repo, NODE, "opus", c2)[0] is not None   # the latest filing, P, is the basis now
    _file(repo, "opus", c2, delta_from=c1)   # and C1 counts again, so a delta from it does too
    assert [a.model for a in _gate(repo).approvals] == ["opus"]


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


# --- fix check (M22.52): the blocker checks its findings, the other family's approval carries ----------------

FINDING = "src/b.py divides by zero"
SHEET = "# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## Tier\n\n%s: a small change.\n"


def _ready(repo: Path, fix_of: str | None) -> int:
    """composer's READY at HEAD via `specy-road ready`, naming ``fix_of`` when given."""
    with pytest.raises(SystemExit) as e:
        review_cli.main(["ready", "M1.1", "--model", "composer", "--verify", "true=0",
                         *(["--fix-of", fix_of] if fix_of else []), "--repo-root", str(repo)])
    return e.value.code


def fix_round(tmp_path: Path, *, fix: Callable[[Path], object] | None = None, fix_of: str | None = "sol",
              tier: str | None = "plain", branch_tier: str | None = None, policy: str = "",
              roster: str = ROSTER, delta: bool = False) -> tuple[Path, str, str]:
    """``(repo, P, F)``: opus (anthropic) approves ``P``, sol (openai) blocks it with :data:`FINDING`, and ``fix``
    (default: commit ``src/b.py``) makes the fix commit ``F``; composer's READY at ``F`` names ``<fix_of>@P``.
    The integration branch's sheet names ``tier`` (``None``: today's sheet, which has no ``## Tier``);
    ``branch_tier`` sets the branch's own copy before ``P``. ``delta``: opus approved ``P``'s parent in full and
    ``P`` (a test-only change) as a delta review from it."""
    repo = make_review_repo(tmp_path, orchestration=roster % policy)
    if branch_tier:
        commit_file(repo, NODE["planning_dir"], SHEET % branch_tier, "branch sheet")
    basis = git(repo, "rev-parse", "HEAD")
    if delta:
        _file(repo, "opus", basis)
    approved = commit_file(repo, TEST_FILE, TEST_SRC, "first round")
    _file(repo, "opus", approved, delta_from=basis if delta else None)
    _file(repo, "sol", approved, verdict="block", findings={"correctness": [FINDING]})
    if tier:
        advance_dev(repo, NODE["planning_dir"], SHEET % tier)
    (fix or (lambda r: commit_file(r, "src/b.py", "x = 1\n", "fix")))(repo)
    assert _ready(repo, fix_of and f"{fix_of}@{approved}") == 0
    return repo, approved, git(repo, "rev-parse", "HEAD")


def _carried(repo: Path) -> bool:
    """Whether opus's approval of ``P`` counts at HEAD."""
    return [a.model for a in _gate(repo).approvals if a.model == "opus"] == ["opus"]


def _refused(repo: Path) -> str:
    return " ".join(_gate(repo).carry_refused)


def _status(repo: Path, capsys) -> dict:
    capsys.readouterr()
    with pytest.raises(SystemExit):
        review_cli.main(["handoff", "status", "M1.1", "--json", "--repo-root", str(repo)])
    return json.loads(capsys.readouterr().out)["nodes"][0]


@pytest.mark.parametrize("roster", [ROSTER, ROSTER.replace("reviewers_required: 2, reviewers_distinct_families: true",
                                                           "reviewers_required: 1, reviewers_distinct_families: false")])
@pytest.mark.parametrize("then", [None, "approve", "block"])
@pytest.mark.parametrize("delta", [False, True])   # True: the carried approval is itself a delta review
def test_a_fix_of_the_only_block_carries_the_other_familys_approval_until_the_blocker_decides(
        tmp_path: Path, capsys, roster: str, then: str | None, delta: bool) -> None:
    repo, approved, head = fix_round(tmp_path, roster=roster, delta=delta)
    g = _gate(repo)
    assert [a.model for a in g.approvals] == ["opus"] and not g.blocks   # the old block no longer counts
    assert "sol" in [r.data["model"] for r in g.stale] and not g.passed   # carried alone: never met
    st = _status(repo, capsys)
    assert f"opus@{approved[:12]} carried from an older commit" in st["policy"] and not st["policy_met"]
    if then:
        _file(repo, "sol", head, verdict=then, findings={"correctness": [] if then == "approve" else ["still"]})
        assert _gate(repo).passed is (then == "approve")


def test_the_trust_tier_is_read_from_the_integration_branch_not_the_branch(tmp_path: Path) -> None:
    repo, _, _ = fix_round(tmp_path, tier="trust boundary", branch_tier="plain")
    assert not _carried(repo) and "names tier 'trust boundary'" in _refused(repo)


def _no_sheet_on_dev(repo: Path) -> None:
    git(repo, "checkout", "-q", "dev")
    git(repo, "rm", "-q", NODE["planning_dir"])
    git(repo, "commit", "-qm", "no sheet")
    git(repo, "checkout", "-q", "feature/rm-thing")


@pytest.mark.parametrize(("tier", "after", "why"), [
    (None, None, "has no ## Tier"),
    ("medium", None, "names tier 'medium'"),
    ("plain", _no_sheet_on_dev, "no planning sheet"),
    ("plain", lambda r: git(r, "branch", "-m", "dev", "trunk"), "integration branch could not be resolved"),
])
def test_an_unknown_tier_leaves_the_approval_stale_and_says_why(tmp_path: Path, capsys, tier, after, why) -> None:
    repo, _, _ = fix_round(tmp_path, tier=tier)
    if after:
        after(repo)
    assert not _carried(repo) and why in _refused(repo)
    if after is None:
        assert why in _status(repo, capsys)["policy"]


def _mv(src: str, dst: str) -> Callable[[Path], None]:
    def fix(repo: Path) -> None:
        git(repo, "mv", src, dst)
        git(repo, "commit", "-qm", f"mv {src}")
    return fix


@pytest.mark.parametrize("fix", [
    lambda r: commit_file(r, "docs/y.md", "# y\n", "outside"),
    _mv("src/a.py", "docs/a.py"),   # the destination is outside
    _mv("docs/x.md", "src/x.md"),   # the source is outside
])
def test_a_fix_touching_a_path_outside_the_zones_does_not_carry(tmp_path: Path, fix) -> None:
    repo, _, _ = fix_round(tmp_path, fix=fix)
    assert not _carried(repo) and "outside the touch zones" in _refused(repo)


def test_zones_widened_after_the_blocked_commit_do_not_cover_the_fix(tmp_path: Path) -> None:
    repo, _, _ = fix_round(tmp_path, fix=lambda r: commit_file(r, "lib/c.py", "y = 2\n", "new path"))
    reg = repo / "roadmap" / "registry.yaml"
    data = yaml.safe_load(reg.read_text())
    data["entries"][0]["touch_zones"] = ["src", "lib"]   # the claim now covers lib/, but not at P
    reg.write_text(yaml.safe_dump(data))
    assert not _carried(repo) and "lib/c.py is outside the touch zones" in _refused(repo)


def _malformed(repo: Path) -> None:
    ready = reviews_dir(repo, "M1.1") / "READY-composer.md"
    ready.write_text(ready.read_text().replace("fix_of: sol@", "fix_of: sol-"))


def _outcome(repo: Path) -> tuple:
    g = _gate(repo)
    return (g.passed, sorted(a.model for a in g.approvals), sorted(b.model for b in g.blocks),
            sorted(r.data["model"] for r in g.stale), g.problems())


def _summary_only(repo: Path) -> None:
    commit_file(repo, "work/implementation-summary-M1.1.md", "# s\n", "summary")


@pytest.mark.parametrize(("fix_of", "fix", "after", "carried"), [
    (None, None, None, False),                                                         # absent
    ("sol", None, _malformed, False),                                                  # not <model>@<sha>
    ("sol", None, lambda r: commit_file(r, "src/c.py", "z = 3\n", "later"), False),   # READY no longer at HEAD
    ("opus", None, None, False),                                                       # names an approver
    ("sonnet", _summary_only, lambda r: _file(r, "sol", git(r, "rev-parse", "HEAD")), True),   # bookkeeping carry
])
def test_a_missing_or_unusable_fix_of_gives_todays_result(tmp_path: Path, fix_of, fix, after, carried) -> None:
    repo, approved, _ = fix_round(
        tmp_path, fix_of=fix_of, fix=fix, branch_tier="plain" if fix is _summary_only else None)
    if after:
        after(repo)
    with_fix_of = _outcome(repo)
    ready = reviews_dir(repo, "M1.1") / "READY-composer.md"
    ready.write_text("".join(ln for ln in ready.read_text().splitlines(True) if not ln.startswith("fix_of:")))
    assert with_fix_of == _outcome(repo)   # the same gate as without fix_of
    assert with_fix_of[0] is carried and ("opus" in with_fix_of[1]) is carried


def test_ready_refuses_a_malformed_fix_of(tmp_path: Path) -> None:
    repo, _, _ = fix_round(tmp_path)
    assert _ready(repo, "sol") == 1


def _two_commits(repo: Path) -> None:
    commit_file(repo, "src/b.py", "x = 1\n", "fix 1")
    commit_file(repo, "src/c.py", "z = 3\n", "fix 2")


@pytest.mark.parametrize(("fix", "second_block", "why"), [
    (None, True, "has 2 blocks"),
    (_two_commits, False, "is not the sole parent"),
])
def test_two_blocks_or_two_fix_commits_do_not_carry(tmp_path: Path, fix, second_block: bool, why: str) -> None:
    repo, approved, _ = fix_round(tmp_path, fix=fix)
    if second_block:
        _file(repo, "sonnet", approved, verdict="block")
    assert not _carried(repo) and why in _refused(repo)


def _sibling(repo: Path) -> None:
    git(repo, "init", "-q", str(repo / "vendor"))


@pytest.mark.parametrize(("policy", "fix", "after", "why"), [
    (", delta_review: false", None, None, "policy.delta_review is off"),
    ("", None, lambda r: rp.main(["M1.1", "--full", "--repo-root", str(r)]), "`review packet --full` forces"),
    ("", lambda r: commit_file(r, TEST_FILE, "def test_a():\n    pass\n", "no assert"), None, "integrity report"),
    ("", None, _sibling, "sibling repositories"),
])
def test_policy_and_integrity_still_stop_the_carry(tmp_path: Path, policy, fix, after, why) -> None:
    repo, _, _ = fix_round(tmp_path, policy=policy, fix=fix)
    if after:
        after(repo)
    assert not _carried(repo) and why in _refused(repo)
