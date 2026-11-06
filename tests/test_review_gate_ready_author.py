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
