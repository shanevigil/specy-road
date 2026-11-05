"""M8.3 A1 with M15.18: the strict harness schema carries the unplanned test removals ``review record`` requires.

Sol-low's block at 0022a371: the schema Codex receives (``--output-schema``) named only the leaf's A# ids with no
other keys allowed, so no strict-schema reviewer could approve a leaf with an unplanned removal. Its acceptance keys
now come from the same source the packet and ``review record`` use (``target_unplanned_removals`` of the target).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.review_delegate_helpers import FAKE_CODEX, strict_problems
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_output

from specy_road import review_files as rf
from specy_road.integrity_removals import target_unplanned_removals
from specy_road.review_delegate import delegate
from specy_road.review_record_write import acceptance_keys
from specy_road.review_target import resolve_target

OLD = "removed-test: tests/test_leaf.py::test_old"


def _codex_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A leaf whose branch deletes ``test_old`` (unplanned), reviewed by a fake ``codex``; ``(repo, spec file)``."""
    repo = make_review_repo(tmp_path, orchestration=(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: sol, family: openai, roles: [reviewer], harness: codex}\n"))
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "tests/test_leaf.py", "def test_keep():\n    assert 1\n\n\ndef test_old():\n    assert 1\n",
                "baseline tests")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    commit_file(repo, "tests/test_leaf.py", "def test_keep():\n    assert 1\n", "drop test_old")
    reviews = rf.reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True)
    (reviews / "PACKET.md").write_text("# Review packet\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(FAKE_CODEX.format(python=sys.executable))
    (bin_dir / "codex").chmod(0o755)
    monkeypatch.setenv("FAKE_CODEX_SPEC", str(tmp_path / "codex-spec.json"))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return repo, tmp_path / "codex-spec.json"


def _strict(answer: dict, schema: dict) -> dict:
    """``answer`` as strict mode sends it: every property present, an unanswered one ``null``."""
    return {k: answer.get(k) for k in schema["properties"]}


@pytest.mark.parametrize("verdict,removal", [("approve", "pass"), ("block", None)])
def test_a_codex_reviewer_can_answer_every_required_removal_entry_and_review_record_files_it(
        tmp_path: Path, monkeypatch, verdict: str, removal: str | None) -> None:
    repo, spec = _codex_repo(tmp_path, monkeypatch)
    head = git(repo, "rev-parse", "HEAD")
    assert target_unplanned_removals(repo, resolve_target(repo, "M1.1")) == [OLD]   # what review record requires
    answer = review_output(head, model="sol", verdict=verdict, a1="pass" if verdict == "approve" else "fail")
    answer["acceptance"] = {**answer["acceptance"], OLD: removal}       # a blocking reviewer answers null
    calls = tmp_path / "codex-calls.json"
    spec.write_text(json.dumps({"calls": str(calls), "answer": answer}))
    run = delegate(repo, "M1.1", "sol", sleep=lambda s: None)
    argv = json.loads(calls.read_text())
    schema = json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text())   # the schema Codex was given
    acc = schema["properties"]["acceptance"]
    assert strict_problems(schema) == [] and acc["required"] == ["A1", "A2", OLD]
    assert Draft202012Validator(schema).is_valid(_strict(answer, schema))           # the answer it filed fits it
    assert not Draft202012Validator(acc).is_valid({"A1": "pass", "A2": "pass", OLD: "fail"})   # pass-only kept
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]
    rec = rf.load_review(rf.review_path(repo, "M1.1", "sol"), ["A1", "A2"])
    assert rec.ok and rec.data["verdict"] == verdict
    assert rec.data["acceptance"].get(OLD) == removal                                # null dropped, not filed


def test_an_approve_without_the_removal_entry_is_a_rerun_request(tmp_path: Path, monkeypatch) -> None:
    repo, spec = _codex_repo(tmp_path, monkeypatch)
    calls = tmp_path / "codex-calls.json"
    spec.write_text(json.dumps({"calls": str(calls), "answer": review_output(git(repo, "rev-parse", "HEAD"),
                                                                              model="sol")}))
    run = delegate(repo, "M1.1", "sol", sleep=lambda s: None)
    assert run["outcome"] == "rerun" and "review record refused the output" in run["reason"] and OLD in run["reason"]
    assert not rf.review_path(repo, "M1.1", "sol").exists()


def test_a_target_with_no_unplanned_removal_gets_the_leaf_ids_alone(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert acceptance_keys(repo, "M1.1", None) == (["A1", "A2"], [])   # no removal on the branch: the ids alone
