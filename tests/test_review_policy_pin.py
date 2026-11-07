"""A leaf's review policy is pinned at claim (M21.30, CR1): the CR1 sequence as a table.

The claim is pickup's registration commit on ``dev`` carrying the ``Review-policy:`` trailer; the feature branch
is rebased onto it, as pickup branches from it. Policy changes are then committed on ``dev`` (the integration
branch the gate reads), as the CR1 executor did.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step
from tests.review_repo_helpers import NODE, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

from specy_road.bundled_scripts import finish_task, mark_implementation_reviewed, review_cli
from specy_road.bundled_scripts.registration_pickup_commit import registration_commit_message
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_policy_pin import ACCEPTANCE_NAME, pin_of, pin_problem, pinned_message, policy_digest

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


def _write(path: Path, content: str | bytes | None) -> None:
    """``content`` at ``path``; ``None`` puts a directory there instead (a file that cannot be read as one)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        path.unlink(missing_ok=True)
        path.mkdir()
        (path / "x").write_text("x")
    else:
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def _on_dev(repo: Path, rel: str, content: str | bytes | None, *, merge: bool = False) -> None:
    git(repo, "checkout", "-q", "dev")
    _write(repo / rel, content)
    git(repo, "add", "-A", "--", rel)
    git(repo, "commit", "-qm", f"chore: edit {rel}")
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
    assert "The review rules changed after this work started" in err
    assert "specy_road.review_policy_pin" in err
    assert err.index("The review rules changed after this work started") < err.index("roster composer.roles")
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
    out = capsys.readouterr().out
    assert "roster composer.roles" in out
    assert "The review rules changed after this work started" in out
    assert "specy_road.review_policy_pin" in out
    assert out.index("The review rules changed after this work started") < out.index("roster composer.roles")
    assert yaml.safe_load(acceptance.read_text())["node_id"] == "M1.1"
    assert _gate(repo).passed


def _bad_digest(data: dict, key: str) -> dict:
    return {**data, key: "0" * 64}


_CHANGED = "review policy changed on refs/heads/dev since M1.1 was claimed"
_INVALID = "an invalid acceptance never counts"
# (case, policy changed after the claim, how the filed acceptance is changed or None for a second policy edit,
#  expected problem text). An invalid file is a problem whether or not the policy changed.
ACCEPTANCE_CASES = [
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
        new = new if isinstance(new, (str, bytes)) else yaml.safe_dump(new)
        acceptance.write_bytes(new if isinstance(new, bytes) else new.encode("utf-8"))
    gate = _gate(repo)
    assert not gate.passed and problem in gate.policy_pin
    before = _tree(repo)
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    assert _tree(repo) == before


_DEEP = "[" * 5000 + "]" * 5000
# The module's one rule for unreadable input, as a table: (failure kind, as the committed policy, as the acceptance
# file). ``None`` puts a directory where the file should be. Every cell: a gate problem, and every command refuses
# with a clean non-zero exit, never a traceback.
UNREADABLE_KINDS = [
    ("impossible unquoted date", TWO_FAMILIES.replace("2026-12-31", "2026-99-99"), "at: 2026-99-99\n"),
    ("non-UTF-8 bytes", TWO_FAMILIES.encode("utf-8") + b"# \xff\xfe\n", b"node_id: M1.1\n\xff\xfe\n"),
    ("YAML syntax error", "roster: [\n", "node_id: [\n"),
    ("wrong top-level type", "- a\n- b\n", "- a\n- b\n"),
    ("wrong shape inside", "version: 1\nroster: [1]\npolicy: 1\n", "node_id: [1]\n"),
    ("mixed-type keys", "version: 1\npolicy: {1: a, b: c}\n", "{1: a, node_id: M1.1}\n"),
    ("deeply nested input", f"version: 1\nsubstitutions: {_DEEP}\n", _DEEP + "\n"),
    ("unreadable file", None, None),
]
UNREADABLE_CASES = [(kind, where, content) for kind, policy, acceptance in UNREADABLE_KINDS
                    for where, content in (("committed policy", policy), ("acceptance file", acceptance))]


@pytest.mark.parametrize(("kind", "where", "content"), UNREADABLE_CASES,
                         ids=[f"{k} in {w}" for k, w, _ in UNREADABLE_CASES])
def test_unreadable_input_is_a_problem_and_every_command_refuses_cleanly(tmp_path: Path, monkeypatch, capsys,
                                                                       kind, where, content) -> None:
    repo = _repo(tmp_path)
    if where == "committed policy":
        _on_dev(repo, ORCH, content)
    else:
        _write(reviews_dir(repo, "M1.1") / ACCEPTANCE_NAME, content)
    _approve(repo)
    gate = _gate(repo)
    expected = "review policy pin of M1.1 cannot be checked" if where == "committed policy" else _INVALID
    assert not gate.passed and expected in gate.policy_pin
    before = _tree(repo)
    assert _exit(mark_implementation_reviewed.main, ["--yes", "--repo-root", str(repo)]) == 1
    assert _exit(finish_task.main, ["--repo-root", str(repo)]) == 1
    if where == "committed policy":
        assert _accept(repo, monkeypatch, tty=True) == 1
        assert not (reviews_dir(repo, "M1.1") / ACCEPTANCE_NAME).exists()
        git(repo, "checkout", "-q", "dev")   # a claim on the unreadable policy is refused too
        with pytest.raises(SystemExit) as e:
            pinned_message(repo, SUBJECT)
        assert e.value.code == 1
        git(repo, "checkout", "-q", "feature/rm-thing")
    assert "Traceback" not in "".join(capsys.readouterr())
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


def _add_claimed_leaf(repo: Path, node_id: str, codename: str, node_key: str) -> None:
    """On ``dev``: add ``node_id``, pin the policy, then one commit on ``feature/rm-<codename>``."""
    git(repo, "checkout", "-q", "dev")
    chunk = repo / "roadmap" / "phases" / "M1.json"
    doc = json.loads(chunk.read_text())
    doc["nodes"].append({**NODE, "id": node_id, "codename": codename, "title": codename, "node_key": node_key,
                         "sibling_order": len(doc["nodes"]) + 1,
                         "planning_dir": f"planning/{node_id}_{codename}_{node_key}.md"})
    chunk.write_text(json.dumps(doc), encoding="utf-8")
    reg_path = repo / "roadmap" / "registry.yaml"
    reg = yaml.safe_load(reg_path.read_text())
    reg["entries"].append({"codename": codename, "node_id": node_id, "branch": f"feature/rm-{codename}",
                           "touch_zones": ["src"], "implementation_review": "pending"})
    reg_path.write_text(yaml.safe_dump(reg), encoding="utf-8")
    git(repo, "add", "-A", "--", "roadmap/phases/M1.json", "roadmap/registry.yaml")
    git(repo, "commit", "-qm", f"chore: add {node_id}")
    message = pinned_message(repo, registration_commit_message(codename, include_ci_skip=True))
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    git(repo, "checkout", "-q", "-b", f"feature/rm-{codename}")
    _write(repo / "src" / f"{codename}.py", "x\n")
    git(repo, "add", f"src/{codename}.py")
    git(repo, "commit", "-qm", f"impl {codename}")


def _leaves_at_three_policies(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """M1.1 pinned at the first policy, M1.2 and M1.4 at the second, M1.3 at the policy on ``dev`` now."""
    repo = _repo(tmp_path)
    _on_dev(repo, ORCH, CR1_ROSTER)
    _add_claimed_leaf(repo, "M1.2", "other", "22222222-2222-5222-8222-222222222222")
    _add_claimed_leaf(repo, "M1.4", "also", "44444444-4444-5444-8444-444444444444")
    git(repo, "checkout", "-q", "dev")
    _write(repo / ORCH, CR1_ROSTER.replace("reviewers_required: 2", "reviewers_required: 1"))
    git(repo, "add", "-A", "--", ORCH)
    git(repo, "commit", "-qm", "chore: edit orchestration")
    _add_claimed_leaf(repo, "M1.3", "same", "33333333-3333-5333-8333-333333333333")
    pins = {
        "M1.1": pin_of(repo, "thing", "feature/rm-thing")[0],
        "M1.2": pin_of(repo, "other", "feature/rm-other")[0],
        "M1.4": pin_of(repo, "also", "feature/rm-also")[0],
        "M1.3": pin_of(repo, "same", "feature/rm-same")[0],
    }
    return repo, pins


def _run_review(monkeypatch, argv: list[str], *, tty: bool, typed: str = "") -> int:
    monkeypatch.setattr("sys.stdin.isatty", lambda: tty)
    monkeypatch.setattr("builtins.input", lambda _prompt="": typed)
    return _exit(review_cli.main, argv)


def test_accept_policy_all_open_groups_each_change_once(tmp_path: Path, monkeypatch, capsys) -> None:
    repo, pins = _leaves_at_three_policies(tmp_path)
    current = policy_digest(repo, "dev")[0]
    assert pins["M1.1"] != pins["M1.2"] == pins["M1.4"] != current == pins["M1.3"]
    base = ["review", "accept-policy", "--repo-root", str(repo)]
    assert _run_review(monkeypatch, [*base, "--all-open"], tty=False) == 1
    assert "a human accepts a review policy change in a terminal; nothing was written" in capsys.readouterr().err
    assert _run_review(monkeypatch, [*base, "M1.1", "--all-open"], tty=True) == 1
    assert "not both and not neither" in capsys.readouterr().err
    assert _run_review(monkeypatch, base, tty=True) == 1
    assert "not both and not neither" in capsys.readouterr().err
    assert _run_review(monkeypatch, [*base, "--all-open", "--ref", "dev"], tty=True) == 1
    assert "--ref is for one node" in capsys.readouterr().err
    assert _run_review(monkeypatch, [*base, "--all-open"], tty=True, typed="no") == 1
    wrong = capsys.readouterr()
    out = wrong.out
    assert "The review rules changed after this work started" in out
    assert "specy_road.review_policy_pin" in out
    assert out.index("The review rules changed after this work started") < out.index("roster composer.roles")
    assert out.count("roster composer.roles") == 1
    assert out.count("policy.reviewers_required 2 -> 1") == 2
    assert "M1.2, M1.4:" in out and "M1.3" not in out
    assert "not accepted; nothing was written" in wrong.err
    for nid in ("M1.1", "M1.2", "M1.3", "M1.4"):
        assert not (reviews_dir(repo, nid) / ACCEPTANCE_NAME).exists()
    assert _run_review(monkeypatch, [*base, "--all-open"], tty=True, typed="M1.1 M1.2 M1.4") == 0
    for nid in ("M1.1", "M1.2", "M1.4"):
        data = yaml.safe_load((reviews_dir(repo, nid) / ACCEPTANCE_NAME).read_text())
        assert data["node_id"] == nid and data["pinned_sha256"] == pins[nid] and data["accepted_sha256"] == current
    assert not (reviews_dir(repo, "M1.3") / ACCEPTANCE_NAME).exists()
    nodes = {n["id"]: n for n in load_roadmap(repo)["nodes"]}
    assert pin_problem(repo, nodes["M1.1"], "feature/rm-thing") is None


def test_review_delegate_on_a_pinned_claim_is_unaffected(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    _claim(repo)
    set_steps(repo, spec, verdict_step(repo))
    assert _exit(review_cli.main, ["review", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)]) == 0
    assert _gate(repo).policy_pin is None
