"""M22.51: ``review operator-decision`` and the gate's reading of the decision it records (the sheet's test table).

In-process CLI on a temporary repo (:func:`tests.review_repo_helpers.make_review_repo`); refusals assert exit 1
and unchanged ledger and marker bytes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import pytest
import yaml

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_policy_pin import SUBJECT

from specy_road.bundled_scripts import decisions_cli, mark_implementation_reviewed, review_cli
from specy_road.orchestration_role_env import ROLE_ENV
from specy_road.review_files import reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.review_override import block_item, shortfall_text
from specy_road.review_policy_pin import pinned_message

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
  - {id: haiku, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
  - {id: astra, family: openai, roles: [reviewer]}
  - {id: gem, family: google, roles: [reviewer]}
  - {id: grok, family: xai, roles: [reviewer]}
  - {id: composer, family: cursor, roles: [executor]}
policy: {reviewers_required: 1}
"""
LEDGER = Path("roadmap") / "decisions.yaml"
SHEET = NODE["planning_dir"]
PLAIN = "# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## Tier\n\nplain: a small change.\n"
FINDINGS = {"correctness": ["A1 regressed"], "boundary": ["CRLF input still warns"]}
LIMITS = ["A1 regressed: accepted for the release", "CRLF input still warns: a follow-up leaf"]


@pytest.fixture(autouse=True)
def manual_coordinator(monkeypatch):
    """Role unset (the manual coordinator) unless a test sets it."""
    monkeypatch.delenv(ROLE_ENV, raising=False)


def _cli(module, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        module.main(list(args))
    return e.value.code


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def _block(repo: Path, model: str = "opus", findings: dict | None = None) -> None:
    """``model`` files a block of HEAD on A1 with ``findings`` (default: one correctness finding)."""
    data = yaml.safe_load(review_text(_head(repo), model=model, verdict="block", a1="fail").split("---\n")[1])
    data["findings"].update(findings or {"correctness": ["A1 regressed"]})
    notes = repo.parent / f"notes-{model}.md"
    notes.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")
    assert _cli(review_cli, "review", "record", "M1.1", "--model", model, "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0


def _ready(repo: Path) -> None:
    """composer's hand-off at HEAD: composer is a party to the leaf."""
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-composer.md").write_text(
        f"---\nnode_id: M1.1\nagent: composer\nbranch: feature/rm-thing\ncommit: {_head(repo)}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n")


def _decide(repo: Path, *extra: str, quote: str | None = "approved", decision: str = "approve") -> int:
    return _cli(review_cli, "review", "operator-decision", "M1.1", "--decision", decision, "--session", "chat-7",
                *(("--quote", quote) if quote is not None else ()), *extra, "--repo-root", str(repo))


def _status(repo: Path, capsys) -> tuple[int, dict, str]:
    """``(exit, --json node, text of handoff status and review list)``."""
    capsys.readouterr()
    code = _cli(review_cli, "handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    _cli(review_cli, "handoff", "status", "M1.1", "--repo-root", str(repo))
    assert _cli(review_cli, "review", "list", "M1.1", "--repo-root", str(repo)) == 0
    return code, st, capsys.readouterr().out


def _ledger(repo: Path) -> list[dict]:
    return yaml.safe_load((repo / LEDGER).read_text())["entries"]


def _blockers(repo: Path) -> list[str]:
    return [b.model for b in evaluate_gate(repo, NODE, _head(repo)).blocks]


def _on_dev(repo: Path, rel: str, text: str) -> None:
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, rel, text, f"edit {rel}")
    git(repo, "checkout", "-q", "feature/rm-thing")


@pytest.mark.parametrize(("policy", "block", "role"), [
    ("{reviewers_required: 1}", True, None),            # block: a counted correctness block, role unset
    ("{reviewers_required: 2}", False, "coordinator"),  # shortfall: none approved
])
def test_the_operator_form_records_the_decision_and_the_gate_honours_it(tmp_path: Path, capsys, monkeypatch,
                                                                        policy: str, block: bool, role) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER.replace("{reviewers_required: 1}", policy))
    if block:
        _block(repo)
    if role:
        monkeypatch.setenv(ROLE_ENV, role)
    head = _head(repo)
    assert _decide(repo, quote="accept as-is") == 0
    (entry,) = _ledger(repo)
    assert (entry["kind"], entry["status"], entry["node"], entry["decided_by"]) == (
        "decision", "closed", "M1.1", "operator")
    need = 1 if block else 2
    for part in (f"for commit {head},", "T <t@e.com>", '"accept as-is"', shortfall_text(need, 0)):
        assert part in entry["answer"]
    assert (block_item("opus", head, {"correctness": ["A1 regressed"]}) in entry["answer"]) is block
    assert "chat-7" not in (repo / LEDGER).read_text()
    marker = yaml.safe_load((reviews_dir(repo, "M1.1") / f"OPERATOR-{head}.yaml").read_text())
    assert (marker["decision"], marker["session"], marker["commit"]) == (entry["id"], "chat-7", head)
    code, st, text = _status(repo, capsys)
    assert (code, st["state"]) == (0, "approved")
    assert f"0/{need} approvals" in st["policy"] and text.count(f"accepted by operator decision {entry['id']}") >= 2


@pytest.mark.parametrize("path", ["src/b.py", "roadmap/orchestration.yaml"])
def test_the_decision_holds_across_bookkeeping_only(tmp_path: Path, capsys, path: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block(repo)
    assert _decide(repo) == 0
    commit_file(repo, SHEET, PLAIN, "sheet only")   # bookkeeping: the decision still holds
    assert _status(repo, capsys)[1]["state"] == "approved"
    commit_file(repo, path, (repo / path).read_text() + "# more\n" if (repo / path).exists() else "b = 1\n", "code")
    assert _status(repo, capsys)[1]["state"] != "approved"
    _block(repo)   # the same block at the new commit counts
    assert _blockers(repo) == ["opus"]


def test_a_later_block_still_counts_until_a_new_decision_names_it(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block(repo)
    assert _decide(repo) == 0
    _block(repo, "sonnet", {"boundary": ["CRLF input still warns"]})
    assert _blockers(repo) == ["sonnet"]
    assert _decide(repo, quote="both are fine") == 0   # replaces the marker, so it names opus's block again
    code, st, _text = _status(repo, capsys)
    assert (code, st["state"]) == (0, "approved") and _blockers(repo) == []


def _drop_decided_by(repo: Path) -> None:
    doc = yaml.safe_load((repo / LEDGER).read_text())
    del doc["entries"][0]["decided_by"]
    (repo / LEDGER).write_text(yaml.safe_dump(doc))


def _marker_text(repo: Path, text: str) -> None:
    next(reviews_dir(repo, "M1.1").glob("OPERATOR-*.yaml")).write_text(text)


@pytest.mark.parametrize("undo", [
    lambda repo: (repo / LEDGER).unlink(),              # marker only: the entry is gone
    lambda repo: (repo / LEDGER).write_text("{"),        # the ledger cannot be read
    _drop_decided_by,                                    # another closed decision of the node, no decided_by
    lambda repo: _marker_text(repo, "{"),               # an unreadable marker
    lambda repo: _marker_text(repo, "- not a mapping\n"),
], ids=["marker_only", "unreadable_ledger", "no_decided_by", "unreadable_marker", "marker_not_a_mapping"])
def test_a_decision_settles_nothing_without_its_entry_and_marker(tmp_path: Path, undo: Callable) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block(repo)
    assert _decide(repo) == 0
    undo(repo)
    assert _blockers(repo) == ["opus"]


def _git_identity_unset(key: str) -> Callable:
    def setup(repo: Path, monkeypatch) -> None:
        empty = repo.parent / "empty.gitconfig"
        empty.write_text("")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        git(repo, "config", "--unset", f"user.{key}")
    return setup


def _with_child(repo: Path, _mp) -> None:
    child = {"id": "M1.1.1", "node_key": "22222222-2222-5222-8222-222222222222", "codename": "kid",
             "title": "Kid", "type": "task", "parent_id": "M1.1", "sibling_order": 1, "status": "Not Started",
             "dependencies": []}
    (repo / "roadmap" / "phases" / "M1.json").write_text(json.dumps({"nodes": [NODE, child]}))


def _branch_gone(repo: Path, _mp) -> None:
    reg = repo / "roadmap" / "registry.yaml"
    reg.write_text(reg.read_text().replace("feature/rm-thing", "feature/rm-gone"))


def _old_schema(repo: Path, _mp) -> None:
    shutil.copy(Path(__file__).parent / "parity" / "fixtures" / "rc3_consumer" / "schemas" / "decisions.schema.json",
                repo / "schemas" / "decisions.schema.json")


def _role(value: str) -> Callable:
    return lambda _repo, mp: mp.setenv(ROLE_ENV, value)


NONE = lambda _repo, _mp: None  # noqa: E731
REFUSED = {   # setup, operator-decision arguments
    "role_executor": (_role("executor"), {}),
    "role_reviewer": (_role("reviewer"), {}),
    "role_rca": (_role("rca"), {}),
    "role_unknown": (_role("planner"), {}),
    "role_empty": (_role(""), {}),
    "role_whitespace": (_role("  "), {}),
    "role_uppercase": (_role("COORDINATOR"), {}),
    "role_padded": (_role(" coordinator "), {}),
    "user_name_unset": (_git_identity_unset("name"), {}),
    "user_email_unset": (_git_identity_unset("email"), {}),
    "empty_quote": (NONE, {"quote": "  "}),
    "no_quote_or_rule": (NONE, {"quote": None}),
    "empty_session": (NONE, {"extra": ("--session", " ")}),
    "evidence_without_rule": (NONE, {"extra": ("--limit", "x")}),
    "rule_and_quote": (NONE, {"extra": ("--rule", "R1")}),
    "rule_with_approve": (NONE, {"quote": None, "extra": ("--rule", "R1")}),
    "node_with_children": (_with_child, {}),
    "commit_does_not_resolve": (_branch_gone, {}),
    "schema_copied_before_decided_by": (_old_schema, {}),
}


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_refusals_write_nothing(tmp_path: Path, monkeypatch, case: str) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block(repo)
    setup, kw = REFUSED[case]
    setup(repo, monkeypatch)
    before = sorted(p.name for p in reviews_dir(repo, "M1.1").iterdir())
    assert _decide(repo, *kw.get("extra", ()), quote=kw.get("quote", "approved")) == 1
    assert not (repo / LEDGER).exists()
    assert sorted(p.name for p in reviews_dir(repo, "M1.1").iterdir()) == before


# --- The coordinator form (--rule) ---

def _evidence(repo: Path, kind: str, model: str) -> str:
    p = repo / "evidence" / f"{kind}-{model}.md"
    p.parent.mkdir(exist_ok=True)
    p.write_text(f"{kind} by {model}\n")
    return f"{model}={p}"


def _add_rule(repo: Path, *extra: str) -> None:
    assert _cli(decisions_cli, "decisions", "add", "--kind", "standing-rule", "--summary", "accept with limits "
                "when two RCAs and two alignment reviews agree", "--why", '"accept those as limits" (2026-11-09)',
                *extra, "--repo-root", str(repo)) == 0


def _coordinator_repo(tmp_path: Path) -> Path:
    """opus blocks with two findings, composer handed off, R1 is a standing rule and both sheets say plain."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _on_dev(repo, SHEET, PLAIN)
    commit_file(repo, SHEET, PLAIN, "the branch copy says plain too")
    _ready(repo)
    _block(repo, findings=FINDINGS)
    _add_rule(repo)
    return repo


def _coordinate(repo: Path, rule: str = "R1", rcas=("sol", "gem"), aligns=("sonnet", "grok"),
                limits=tuple(LIMITS)) -> int:
    args = ["--rule", rule]
    args += [x for m in rcas for x in ("--rca", _evidence(repo, "rca", m))]
    args += [x for m in aligns for x in ("--alignment", _evidence(repo, "alignment", m))]
    args += [x for lim in limits for x in ("--limit", lim)]
    return _decide(repo, *args, quote=None, decision="accept-with-limits")


def test_the_coordinator_form_accepts_with_limits_under_a_standing_rule(tmp_path: Path, capsys) -> None:
    repo = _coordinator_repo(tmp_path)
    head = _head(repo)
    assert _coordinate(repo) == 0
    entry = next(e for e in _ledger(repo) if e["kind"] == "decision")
    assert entry["decided_by"] == "coordinator"
    for part in ("under rule R1 by coordinator", f"for commit {head},", block_item("opus", head, FINDINGS),
                 *LIMITS, "sol evidence/rca-sol.md sha256:", "grok evidence/alignment-grok.md sha256:"):
        assert part in entry["answer"]
    code, st, text = _status(repo, capsys)
    assert (code, st["state"]) == (0, "approved")
    assert f"accepted with limits under rule R1 by coordinator, decision {entry['id']}" in text


def test_a_standing_rule_is_no_question_nor_preference_and_closes_with_an_answer(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _add_rule(repo, "M1.1")
    for bad in (("--role", "executor"), ("--option", "a|b")):
        assert _cli(decisions_cli, "decisions", "add", "--kind", "standing-rule", "--summary", "s", "--why", "w",
                    *bad, "--repo-root", str(repo)) == 1
    assert _cli(decisions_cli, "decisions", "add", "--kind", "standing-rule", "--summary", "s",
                "--repo-root", str(repo)) == 1   # no --why: it must quote the operator
    capsys.readouterr()
    assert _cli(decisions_cli, "decisions", "list", "--json", "--repo-root", str(repo)) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert _cli(decisions_cli, "decisions", "close", "R1", "--answer", "withdrawn", "--repo-root", str(repo)) == 0
    assert [(e["id"], e["kind"], e["status"]) for e in _ledger(repo)] == [("R1", "standing-rule", "closed")]


def _tier_on_dev(text: str) -> Callable:
    return lambda repo: _on_dev(repo, SHEET, text)


COORDINATOR_REFUSED = {   # setup, _coordinate keyword arguments
    "tier_trust_boundary": (_tier_on_dev(PLAIN.replace("plain: a small change.", "trust boundary: the gate.")), {}),
    "no_tier_value": (_tier_on_dev(PLAIN.split("## Tier")[0]), {}),
    "rule_missing": (None, {"rule": "R9"}),
    "rule_expired": (lambda repo: _add_rule(repo, "--expires", "2020-01-01"), {"rule": "R2"}),
    "rule_is_a_preference": (lambda repo: _cli(decisions_cli, "decisions", "add", "--kind", "preference",
                                               "--summary", "use sol", "--repo-root", str(repo)), {"rule": "P1"}),
    "one_rca": (None, {"rcas": ("sol",)}),
    "two_rcas_of_one_family": (None, {"rcas": ("sol", "astra")}),
    "rca_by_a_party": (None, {"rcas": ("composer", "gem")}),
    "rca_by_the_blocking_reviewer": (None, {"rcas": ("opus", "gem")}),
    "rca_not_on_the_roster": (None, {"rcas": ("nobody", "gem")}),
    "alignment_by_an_analyst": (None, {"aligns": ("sol", "grok")}),
    "alignment_by_the_blocking_reviewer": (None, {"aligns": ("opus", "grok")}),
    "two_alignments_of_one_family": (None, {"aligns": ("sonnet", "haiku")}),
    "finding_without_a_limit": (None, {"limits": (LIMITS[0],)}),
    "finding_in_two_limits": (None, {"limits": (*LIMITS, "A1 regressed, again")}),
    "no_counted_block": (lambda repo: (reviews_dir(repo, "M1.1") / "REVIEW-opus.md").unlink(), {}),
}


@pytest.mark.parametrize("case", sorted(COORDINATOR_REFUSED))
def test_the_coordinator_form_refuses(tmp_path: Path, case: str) -> None:
    repo = _coordinator_repo(tmp_path)
    setup, kw = COORDINATOR_REFUSED[case]
    if setup:
        setup(repo)
    ledger, before = (repo / LEDGER).read_bytes(), sorted(p.name for p in reviews_dir(repo, "M1.1").iterdir())
    assert _coordinate(repo, **kw) == 1
    assert (repo / LEDGER).read_bytes() == ledger
    assert sorted(p.name for p in reviews_dir(repo, "M1.1").iterdir()) == before


@pytest.mark.parametrize("raw", ["sol", "sol=missing.md", "OUTSIDE"])
def test_cited_evidence_must_be_a_project_file(tmp_path: Path, raw: str) -> None:
    repo = _coordinator_repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("x\n")
    args = ["--rule", "R1", "--rca", raw.replace("OUTSIDE", f"sol={outside}"), "--rca", _evidence(repo, "rca", "gem")]
    args += [x for m in ("sonnet", "grok") for x in ("--alignment", _evidence(repo, "alignment", m))]
    args += [x for lim in LIMITS for x in ("--limit", lim)]
    assert _decide(repo, *args, quote=None, decision="accept-with-limits") == 1
    assert not any(e["kind"] == "decision" for e in _ledger(repo))


# --- What the decision does not settle ---

def _pin_then_change_policy(repo: Path) -> None:
    git(repo, "checkout", "-q", "dev")
    git(repo, "commit", "-q", "--allow-empty", "-m", pinned_message(repo, SUBJECT))
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "rebase", "-q", "dev")


OTHER_FAILURES = {   # roster, before the block, after the decision, the problem still named, whether opus blocks
    "policy_pin": (ROSTER, _pin_then_change_policy,
                   lambda repo: _on_dev(repo, "roadmap/orchestration.yaml", ROSTER.replace(
                       "policy:", "  - {id: llama, family: meta, roles: [reviewer]}\npolicy:")),
                   "review policy changed on", True),
    "strong_review": (ROSTER.replace("policy: {reviewers_required: 1}", "policy:\n  reviewers_required: 1\n"
                                     "  strong_review:\n    - {zones: [src], require_one_of: [sonnet]}"),
                      None, None, "strong_review[0]", True),
    "signed_reviews_shortfall": (ROSTER.replace("{reviewers_required: 1}",
                                                "{reviewers_required: 1, signed_reviews: true}"),
                                 None, None, "need 1 approvals at this commit, have 0", False),
}


@pytest.mark.parametrize("case", sorted(OTHER_FAILURES))
def test_other_gate_failures_still_fail(tmp_path: Path, capsys, case: str) -> None:
    roster, before, after, named, block = OTHER_FAILURES[case]
    repo = make_review_repo(tmp_path, orchestration=roster)
    if before:
        before(repo)
    if block:
        _block(repo)
    assert _decide(repo) == 0
    if after:
        after(repo)
    code, st, _text = _status(repo, capsys)
    assert code == 1 and st["state"] != "approved" and _blockers(repo) == []   # the named block is settled
    assert any(named in p for p in st["problems"]), st["problems"]


def test_mark_implementation_reviewed_stamps_the_registry(tmp_path: Path) -> None:
    """The coordinator records on the integration branch; the leaf branch's gate reads the committed entry."""
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    _block(repo)
    git(repo, "checkout", "-q", "dev")
    assert _decide(repo) == 0
    git(repo, "add", str(LEDGER))
    git(repo, "commit", "-qm", "roadmap: operator decision")
    git(repo, "checkout", "-q", "feature/rm-thing")
    assert not (repo / LEDGER).exists()
    mark_implementation_reviewed.main(["--yes", "--allow-missing-summary", "--repo-root", str(repo)])
    entry = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())["entries"][0]
    assert entry["implementation_review"] == "approved"
