"""M21.26: the gate never counts a record from a model that filed a READY on the leaf, and ``review delegate``
refuses that model (rc4 defect D3: the executor's own fresh session approved its leaf and the gate counted it)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.review_delegate_helpers import delegate_repo
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text
from tests.test_review_gate import TWO_FAMILIES

from specy_road import review_signing as rs
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli
from specy_road.review_eligible import eligibility_lines, reviewer_eligibility
from specy_road.review_files import load_review, render_front_matter, reviews_dir
from specy_road.review_gate import evaluate_gate
from specy_road.toolkit_version import stamp_review_toolkit_version


def _sentence(model: str) -> str:
    return f"{model} wrote READY-{model}.md on this leaf; the executor never reviews its own leaf"


def _ready(repo: Path, agent: str) -> None:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"READY-{agent}.md").write_text(
        f"---\nnode_id: M1.1\nagent: {agent}\nbranch: feature/rm-thing\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n"
    )


def _review(repo: Path, model: str, **kw) -> Path:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"REVIEW-{model}.md"
    p.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model, **kw))
    return p


def _gate(repo: Path):
    return evaluate_gate(repo, NODE, git(repo, "rev-parse", "HEAD"), branch="feature/rm-thing")


def _why(gate, model: str) -> list[str]:
    return [why for r, why in gate.ineligible if r.data.get("model") == model]


def test_rc4_shape_executor_approval_does_not_count_and_gets_no_trailer(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    (repo / "work").mkdir()
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")
    _ready(repo, "opus")   # opus executed the leaf
    _review(repo, "opus")  # then a fresh opus session approved it
    _review(repo, "sol")
    g = _gate(repo)
    assert not g.passed and g.approval_count == 1
    assert [a.model for a in g.approvals] == ["sol"]
    assert _why(g, "opus") == [_sentence("opus")]
    head = git(repo, "rev-parse", "HEAD")
    with pytest.raises(SystemExit) as e:
        mir.main(["--yes", "--repo-root", str(repo)])
    assert e.value.code == 1
    assert "review gate is not met" in capsys.readouterr().err
    assert git(repo, "rev-parse", "HEAD") == head
    assert "Reviewed-by: opus" not in git(repo, "log", "--format=%B")
    reg = yaml.safe_load((repo / "roadmap" / "registry.yaml").read_text())
    assert reg["entries"][0]["implementation_review"] == "pending"


def test_executor_block_is_ineligible_and_does_not_hold_the_gate(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _ready(repo, "opus")
    _review(repo, "opus", verdict="block", a1="fail")
    g = _gate(repo)
    assert _why(g, "opus") == [_sentence("opus")]
    assert not any(b.model == "opus" for b in g.blocks)


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs OpenSSH ssh-keygen")
def test_executor_signed_approval_is_ineligible(tmp_path: Path) -> None:
    key = tmp_path / "opus_key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "opus", "-f", str(key)], check=True)
    pub = (tmp_path / "opus_key.pub").read_text(encoding="utf-8").strip()
    roster = TWO_FAMILIES.replace("{id: opus, family: anthropic, roles: [reviewer]}",
                                  f'{{id: opus, family: anthropic, roles: [reviewer], public_key: "{pub}"}}')
    repo = make_review_repo(tmp_path, orchestration=roster)
    p = _review(repo, "opus")
    data = stamp_review_toolkit_version({**load_review(p).data, "notes_sha256": rs.notes_digest("notes\n")})
    data["signature"] = rs.sign(data, key)
    p.write_text(render_front_matter(data, "notes\n"))
    assert [a.model for a in _gate(repo).approvals] == ["opus"]   # the signature verifies: it counts without a READY
    _ready(repo, "opus")
    g = _gate(repo)
    assert not g.approvals and _why(g, "opus") == [_sentence("opus")]


@pytest.mark.parametrize("distinct", [False, True])
def test_another_model_of_the_executors_family_counts(tmp_path: Path, distinct: bool) -> None:
    roster = TWO_FAMILIES if distinct else TWO_FAMILIES.replace("reviewers_distinct_families: true",
                                                                "reviewers_distinct_families: false")
    repo = make_review_repo(tmp_path, orchestration=roster)
    _ready(repo, "opus")
    _review(repo, "sonnet")
    _review(repo, "sol")
    g = _gate(repo)
    assert g.passed and g.summary().startswith("2/2")
    assert {(a.model, a.family) for a in g.approvals} == {("sonnet", "anthropic"), ("sol", "openai")}


def test_a_fix_author_is_excluded(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _ready(repo, "opus")
    notes = repo.parent / "notes-sol.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="sol", verdict="block", a1="fail"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "sol", "--verdict", "block",
                         "--file", str(notes), "--repo-root", str(repo)])
    assert e.value.code == 0
    commit_file(repo, "src/b.py", "x\n", "fix")
    _ready(repo, "sol")   # sol, having reviewed, wrote the fix
    _review(repo, "sol")
    _review(repo, "sonnet")
    g = _gate(repo)
    assert not g.passed and [a.model for a in g.approvals] == ["sonnet"]
    assert _why(g, "sol") == [_sentence("sol")]


def test_no_ready_leaves_the_gate_unchanged(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=TWO_FAMILIES)
    _review(repo, "opus")
    _review(repo, "sol")
    g = _gate(repo)
    assert g.passed and not g.ineligible and {a.model for a in g.approvals} == {"opus", "sol"}


def test_delegate_refuses_a_ready_author_and_writes_nothing(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path)
    _ready(repo, "opus")
    before = sorted(p.name for p in reviews_dir(repo, "M1.1").rglob("*"))
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo)])
    assert e.value.code != 0
    assert "opus wrote READY-opus.md on M1.1" in capsys.readouterr().err
    assert sorted(p.name for p in reviews_dir(repo, "M1.1").rglob("*")) == before
    assert not spec.with_name("calls.json").exists()   # no harness started


ALIASED = TWO_FAMILIES.replace("{id: opus, family: anthropic, roles: [reviewer]}",
                               "{id: opus, family: anthropic, roles: [reviewer], harness_model: claude-opus-x}")
#: opus pins a profile whose file name (custom-model), declared api_id (vendor-model) and alias (opus) all differ.
CUSTOM = "model-profiles/custom/custom-model.md"
PROFILED = TWO_FAMILIES.replace("{id: opus, family: anthropic, roles: [reviewer]}",
                                f"{{id: opus, family: anthropic, roles: [reviewer], profile: {CUSTOM}}}")
_TEMPLATE = Path(__file__).resolve().parent.parent / "specy_road/templates/project/model-profiles/anthropic-claude"


def _profiled_repo(tmp_path: Path, roster: str) -> Path:
    """A review repo on ``roster``; under PROFILED, the custom profile committed on the integration branch only."""
    repo = make_review_repo(tmp_path, orchestration=roster)
    if roster == PROFILED:
        text = (_TEMPLATE / "claude-opus-5-5.md").read_text(encoding="utf-8")
        head, rest = text.split("aliases:\n", 1)
        text = head.replace("api_id: claude-opus-5-5", "api_id: vendor-model") + "aliases:\n  - opus\n" + \
            rest[rest.index("checkpoint:"):]
        git(repo, "checkout", "-q", "dev")
        (repo / CUSTOM).parent.mkdir(parents=True)
        (repo / CUSTOM).write_text(text, encoding="utf-8")
        git(repo, "add", CUSTOM)
        git(repo, "commit", "-qm", "profile")
        git(repo, "checkout", "-q", "feature/rm-thing")
    return repo


@pytest.mark.parametrize(("roster", "agent", "model"), [
    (ALIASED, "Opus", "opus"), (ALIASED, "opus", "OPUS"),                 # case variants
    (ALIASED, "claude-opus-x", "opus"), (ALIASED, "opus", "Claude-Opus-X"),   # harness_model
    (PROFILED, "vendor-model", "opus"), (PROFILED, "opus", "custom-model"),   # declared api_id, file name
])
def test_ready_author_and_record_model_are_compared_after_case_folding_and_roster_aliases(
        tmp_path: Path, roster: str, agent: str, model: str) -> None:
    """M22.19: a case variant or an entry's name on either side still excludes the executor; others still count."""
    repo = _profiled_repo(tmp_path, roster)
    _ready(repo, agent)
    _review(repo, model)
    _review(repo, "sonnet")
    _review(repo, "sol")
    g = _gate(repo)
    assert _why(g, model) == [f"{model} wrote READY-{agent}.md on this leaf; the executor never reviews its own leaf"]
    assert g.passed and {a.model for a in g.approvals} == {"sonnet", "sol"}


SHARED = ALIASED.replace("{id: sonnet, family: anthropic, roles: [reviewer]}",
                         "{id: sonnet, family: anthropic, roles: [reviewer], harness_model: claude-opus-x}")
#: One entry's exact id is another entry's harness_model: an exact id has no precedence.
COLLIDE = TWO_FAMILIES.replace("{id: sonnet, family: anthropic, roles: [reviewer]}",
                               "{id: sonnet, family: anthropic, roles: [reviewer], harness_model: opus}")
#: The reviewer id sol is also an openai executor row's harness_model (as Sol effort aliases in one shared profile).
SOL_ALIAS = TWO_FAMILIES.replace("{id: astra, family: openai, roles: [executor]}",
                                 "{id: astra, family: openai, roles: [executor], harness_model: sol}")
#: The reviewer id sol is also a cursor executor row's harness_model: the name spans two families.
CROSS = TWO_FAMILIES.replace("{id: composer, family: cursor, roles: [executor]}",
                             "{id: composer, family: cursor, roles: [executor], harness_model: sol}")
_EXEC = "executor of the leaf"
_WROTE = "wrote READY-{}.md on this leaf"


@pytest.mark.parametrize(("roster", "agent", "problem", "counted", "excluded"), [
    (SOL_ALIAS, None, None, ["opus", "sol"], {}),                          # (1) one family, nobody wrote: counts
    (SOL_ALIAS, "astra", None, ["opus"], {"astra": _EXEC, "sol": _WROTE.format("astra")}),   # (2) its writer wrote
    (SOL_ALIAS, "composer", None, ["opus", "sol"], {}),                    # (3) another model wrote: counts
    (CROSS, "astra", "'sol' names more than one roster entry (composer, sol)", ["opus", "sol"], {}),   # (4) closes
    (SHARED, "claude-opus-x", None, ["sol"], {"opus": _EXEC, "sonnet": _EXEC}),   # (5) READY: an alias two share
    (COLLIDE, "opus", None, ["sol"], {"opus": _EXEC, "sonnet": _EXEC}),   # READY: one entry's id, the other's alias
    (COLLIDE, "sonnet", None, ["sol"], {"sonnet": _EXEC, "opus": _WROTE.format("sonnet")}),   # record may be writer
    (COLLIDE, "astra", None, ["opus", "sol"], {}),                         # record: one family, nobody wrote
    (PROFILED, "vendor-model", "roster entry 'opus': its profile's names cannot be known", ["opus", "sol"], {}),
])
def test_a_shared_name_closes_the_gate_only_when_it_could_be_the_writer(
        tmp_path: Path, roster: str, agent: str | None, problem: str | None, counted: list[str],
        excluded: dict[str, str]) -> None:
    """M22.48 (narrowing M22.19): a READY author is excluded under every entry it may be and a record that may be a
    writer is not counted, without closing the gate; a record name whose entries wrote nothing closes it only when
    they span families. ``handoff status`` gives each excluded entry its reason."""
    repo = _profiled_repo(tmp_path, roster)
    if roster == PROFILED:   # a working-tree edit: dispatch refuses the profile, so its names are unknown
        (repo / CUSTOM).parent.mkdir(parents=True)
        (repo / CUSTOM).write_text("---\napi_id: something-else\n---\n", encoding="utf-8")
    if agent:
        _ready(repo, agent)
    _review(repo, "opus")
    _review(repo, "sol")
    g = _gate(repo)
    assert sorted(a.model for a in g.approvals) == counted
    assert g.passed == (problem is None and counted == ["opus", "sol"])
    if problem:
        assert any(problem in p for p in g.problems())
    else:
        assert not any("names more than one roster entry" in p for p in g.problems())
    rows = {r["model"]: r for r in reviewer_eligibility(repo, NODE, g, "feature/rm-thing")}
    lines = "\n".join(eligibility_lines({"reviewer_eligibility": list(rows.values())}))
    for model, why in excluded.items():
        assert not rows[model]["eligible"] and why in rows[model]["reason"]
        assert f"{model} ({rows[model]['family']}): excluded — {rows[model]['reason']}" in lines
