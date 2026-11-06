"""A leaf's review policy is pinned at claim (M21.30, CR1): the CR1 sequence as a table.

The claim is pickup's registration commit on ``dev`` carrying the ``Review-policy:`` trailer; the feature branch
is rebased onto it, as pickup branches from it. Policy changes are then committed on ``dev`` (the integration
branch the gate reads), as the CR1 executor did.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

from specy_road.bundled_scripts import finish_task, mark_implementation_reviewed, review_cli
from specy_road.bundled_scripts.registration_pickup_commit import registration_commit_message
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_policy_pin import ACCEPTANCE_NAME, pin_of, pinned_message, policy_digest

ORCH = "roadmap/orchestration.yaml"
WORKFLOW = "roadmap/git-workflow.yaml"
SUBJECT = registration_commit_message("thing", include_ci_skip=True)
#: CR1: an executor-only roster entry gains the reviewer role on the integration branch after the claim.
CR1_ROSTER = TWO_FAMILIES.replace("{id: composer, family: cursor, roles: [executor]}",
                                  "{id: composer, family: cursor, roles: [executor, reviewer]}")
KEYED = TWO_FAMILIES.replace("{id: opus, family: anthropic, roles: [reviewer]}",
                             "{id: opus, family: anthropic, roles: [reviewer], public_key: 'ssh-ed25519 AAAAone'}")
SWITCH_OFF = "version: 1\nintegration_branch: dev\nremote: origin\nrequire_implementation_review_before_finish: false\n"


def _claim(repo: Path, message: str | None = None) -> None:
    """Pickup's registration commit on ``dev`` (pinned by default), then the feature branch on top of it."""
    git(repo, "checkout", "-q", "dev")
    git(repo, "commit", "-q", "--allow-empty", "-m", message or pinned_message(repo, SUBJECT))
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "rebase", "-q", "dev")


def _on_dev(repo: Path, rel: str, text: str, *, merge: bool = False) -> None:
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, rel, text, f"chore: edit {rel}")
    git(repo, "checkout", "-q", "feature/rm-thing")
    if merge:
        git(repo, "rebase", "-q", "dev")


def _approve(repo: Path) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    for model in ("opus", "sol"):
        (d / f"REVIEW-{model}.md").write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model))


def _repo(tmp_path: Path, orchestration: str = TWO_FAMILIES, *, pin: str | None = None) -> Path:
    repo = make_review_repo(tmp_path, orchestration=orchestration)
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    _claim(repo, pin)
    return repo


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"))


def _exit(fn, argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        fn(argv)
        raise SystemExit(0)
    return e.value.code or 0


def _accept(repo: Path, monkeypatch, *, tty: bool, typed: str = "M1.1") -> int:
    monkeypatch.setattr("sys.stdin.isatty", lambda: tty)
    monkeypatch.setattr("builtins.input", lambda _prompt="": typed)
    return _exit(review_cli.main, ["review", "accept-policy", "M1.1", "--repo-root", str(repo)])


def _tree(repo: Path) -> tuple[str, str, str]:
    return (git(repo, "rev-parse", "HEAD"), (repo / "roadmap" / "registry.yaml").read_text(),
            (repo / "roadmap" / "phases" / "M1.json").read_text())


def test_claim_pins_the_policy_at_head_and_keeps_the_subject(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = git(repo, "rev-parse", "dev^")
    subject, _, rest = git(repo, "log", "-1", "--format=%B", "dev").partition("\n")
    assert subject == SUBJECT
    assert rest.strip() == f"Review-policy: sha256:{policy_digest(repo, head)[0]} at {head}"
    assert pin_of(repo, "thing", "HEAD") == (policy_digest(repo, head)[0], head)


# (case, orchestration at claim, edit on dev after the claim, expected problem text or None for a pass)
GATE_CASES = [
    ("unchanged", TWO_FAMILIES, None, None),
    ("cr1 roster gains reviewer", TWO_FAMILIES, (ORCH, CR1_ROSTER),
     'roster composer.roles ["executor"] -> ["executor","reviewer"]'),
    ("public_key changed", KEYED, (ORCH, KEYED.replace("AAAAone", "AAAAtwo")), "roster opus.public_key"),
    ("quoted dates hash equal", TWO_FAMILIES,
     (ORCH, TWO_FAMILIES.replace("2026-01-01", "'2026-01-01'").replace("2026-12-31", "'2026-12-31'")), None),
    ("policy file no longer parses", TWO_FAMILIES, (ORCH, "roster: [\n"), "cannot be checked"),
    ("policy is not a mapping", TWO_FAMILIES, (ORCH, "version: 1\npolicy: 1\n"), "policy is not a mapping"),
    ("roster is not a list of mappings", TWO_FAMILIES, (ORCH, "version: 1\nroster: [1]\n"),
     "roster is not a list of mappings"),
    ("one line per change", TWO_FAMILIES, (ORCH, CR1_ROSTER.replace("reviewers_required: 2", "reviewers_required: 1")),
     '-> ["executor","reviewer"]\n      policy.reviewers_required 2 -> 1\n'),
]


@pytest.mark.parametrize(("case", "orchestration", "edit", "problem"), GATE_CASES, ids=[c[0] for c in GATE_CASES])
def test_gate_judges_by_the_policy_pinned_at_claim(tmp_path: Path, case, orchestration, edit, problem) -> None:
    repo = _repo(tmp_path, orchestration)
    if edit:
        _on_dev(repo, *edit)
    _approve(repo)
    gate = _gate(repo)
    assert gate.passed is (problem is None), gate.problems()
    if problem:
        assert problem in gate.policy_pin and gate.policy_pin in gate.problems()


def test_cr1_change_refuses_mark_reviewed_and_finish_writing_nothing(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo, ORCH, CR1_ROSTER)
    _approve(repo)
    before = _tree(repo)
    assert _exit(mark_implementation_reviewed.main, ["--yes", "--repo-root", str(repo)]) == 1
    err = "".join(capsys.readouterr())   # the gate's problems print to stdout, the refusal to stderr
    assert "review policy changed on refs/heads/dev since M1.1 was claimed" in err
    assert "a human accepts it with `specy-road review accept-policy M1.1` in a terminal" in err
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    assert "roster composer.roles" in capsys.readouterr().err
    assert _tree(repo) == before


def test_review_switch_turned_off_after_claim_refuses_finish_before_bookkeeping(tmp_path: Path, capsys) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo, WORKFLOW, SWITCH_OFF, merge=True)   # off everywhere, so review_required alone would skip review
    before = _tree(repo)
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    assert "require_implementation_review_before_finish true -> false" in capsys.readouterr().err
    assert _tree(repo) == before


def test_accept_policy_needs_a_terminal_then_the_gate_passes(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo, ORCH, CR1_ROSTER)
    _approve(repo)
    acceptance = reviews_dir(repo, "M1.1") / ACCEPTANCE_NAME
    assert _accept(repo, monkeypatch, tty=False) == 1
    assert "a human accepts a review policy change in a terminal; nothing was written" in capsys.readouterr().err
    assert _accept(repo, monkeypatch, tty=True, typed="M9.9") == 1
    assert not acceptance.exists()
    assert _accept(repo, monkeypatch, tty=True) == 0
    assert "roster composer.roles" in capsys.readouterr().out
    assert yaml.safe_load(acceptance.read_text())["node_id"] == "M1.1"
    assert _gate(repo).passed


def _bad_digest(data: dict, key: str) -> dict:
    return {**data, key: "0" * 64}


_CHANGED = "review policy changed on refs/heads/dev since M1.1 was claimed"
_INVALID = "an invalid acceptance never counts"
# (case, policy changed after the claim, how the filed acceptance is changed or None for a second policy edit,
#  expected problem text). An invalid file is a problem whether or not the policy changed.
ACCEPTANCE_CASES = [
    ("malformed yaml", True, lambda d: "node_id: [\n", _INVALID),
    ("malformed yaml, policy unchanged", False, lambda d: "node_id: [\n", _INVALID),
    ("schema-invalid", True, lambda d: {**d, "extra": 1}, _INVALID),
    ("schema-invalid, policy unchanged", False, lambda d: {**d, "extra": 1}, _INVALID),
    ("another node", True, lambda d: {**d, "node_id": "M9.9"}, _INVALID),
    ("another node, policy unchanged", False, lambda d: {**d, "node_id": "M9.9"}, _INVALID),
    ("pinned digest mismatch", True, lambda d: _bad_digest(d, "pinned_sha256"), _CHANGED),
    ("accepted digest mismatch", True, lambda d: _bad_digest(d, "accepted_sha256"), _CHANGED),
    ("second edit after acceptance", True, None, _CHANGED),
]


@pytest.mark.parametrize(("case", "changed", "change", "problem"), ACCEPTANCE_CASES,
                         ids=[c[0] for c in ACCEPTANCE_CASES])
def test_an_acceptance_counts_only_for_its_node_and_digests(tmp_path: Path, monkeypatch, case, changed, change,
                                                            problem) -> None:
    repo = _repo(tmp_path)
    _on_dev(repo, ORCH, CR1_ROSTER)
    _approve(repo)
    assert _accept(repo, monkeypatch, tty=True) == 0
    acceptance = reviews_dir(repo, "M1.1") / ACCEPTANCE_NAME
    if not changed:   # the integration branch goes back to the pinned policy; the acceptance file stays
        _on_dev(repo, ORCH, TWO_FAMILIES)
    if change is None:
        _on_dev(repo, ORCH, CR1_ROSTER.replace("reviewers_required: 2", "reviewers_required: 1"))
    else:
        new = change(yaml.safe_load(acceptance.read_text()))
        acceptance.write_text(new if isinstance(new, str) else yaml.safe_dump(new))
    gate = _gate(repo)
    assert not gate.passed and problem in gate.policy_pin
    before = _tree(repo)
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    assert _tree(repo) == before


@pytest.mark.parametrize(("case", "message", "problem"), [
    ("unpinned claim is judged as today", SUBJECT, None),
    ("unparsable trailer", f"{SUBJECT}\n\nReview-policy: sha256:zz at nowhere", "trailer"),
])
def test_registration_commit_trailer(tmp_path: Path, case, message, problem) -> None:
    repo = _repo(tmp_path, pin=message)
    _on_dev(repo, ORCH, CR1_ROSTER)
    _approve(repo)
    gate = _gate(repo)
    assert gate.passed is (problem is None), gate.problems()
    if problem:
        assert problem in gate.policy_pin


def test_review_delegate_on_a_pinned_claim_is_unaffected(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    _claim(repo)
    set_steps(repo, spec, verdict_step(repo))
    assert _exit(review_cli.main, ["review", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)]) == 0
    assert _gate(repo).policy_pin is None
