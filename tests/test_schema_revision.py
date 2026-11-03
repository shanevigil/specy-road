"""A leaf that adds a key to a bundled schema can be gated and finished by the installed specy-road.

Each repo here is a specy-road checkout (``specy_road/`` at its git root) whose
feature commit changes one schema the way such a leaf would; the installed copy
under test is the unchanged one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo, review_text

from specy_road.git_workflow_config import load_git_workflow_config, require_implementation_review_before_finish
from specy_road.orchestration_config import effective_config, load_orchestration_config, validate_orchestration_dict
from specy_road.review_files import latest_ready, load_review, render_front_matter, reviews_dir
from specy_road.review_gate import evaluate_gate, gate_holds_at_head_or_exit
from specy_road.runtime_paths import specy_road_package_dir
from specy_road.schema_revision import revision_text
from specy_road.worker_state import WorkerError, create_record, list_records, load_record, record_path, set_state

ORCHESTRATION = "templates/project/schemas/orchestration.schema.json"
GIT_WORKFLOW = "templates/project/schemas/git-workflow.schema.json"
REVIEW_RECORD = "schemas/review-record.schema.json"
HANDOFF = "schemas/handoff.schema.json"
WORKER_RECORD = "schemas/worker-record.schema.json"

POLICY_KEY = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
policy: {reviewers_required: 1, new_gate: true}
"""


def _leaf_changes(repo: Path, sub: str, edit: Callable[[dict[str, Any]], None]) -> str:
    """Commit ``specy_road/<sub>`` as the installed copy with ``edit`` applied; return the commit."""
    schema = json.loads((specy_road_package_dir() / sub).read_text(encoding="utf-8"))
    edit(schema)
    (repo / "specy_road").mkdir(exist_ok=True)
    (repo / "specy_road" / "__init__.py").write_text("", encoding="utf-8")
    git(repo, "add", "specy_road/__init__.py")
    return commit_file(repo, f"specy_road/{sub}", json.dumps(schema, indent=2) + "\n", f"leaf changes {sub}")


def _add_property(where: str, name: str, spec: dict[str, Any]) -> Callable[[dict[str, Any]], None]:
    def edit(schema: dict[str, Any]) -> None:
        (schema["$defs"][where] if where else schema)["properties"][name] = spec
    return edit


def _review_with(repo: Path, commit: str, extra: str) -> Path:
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    path = d / "REVIEW-human.md"
    path.write_text(review_text(commit).replace("is_coordinator: false\n", f"is_coordinator: false\n{extra}\n"))
    return path


def test_a_policy_key_the_leaf_adds_validates_where_the_file_is_read(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _leaf_changes(repo, ORCHESTRATION, _add_property("policy", "new_gate", {"type": "boolean"}))
    commit_file(repo, "roadmap/orchestration.yaml", POLICY_KEY, "turn the new gate on")
    assert "new_gate" in validate_orchestration_dict(yaml.safe_load(POLICY_KEY))   # the installed copy rejects it
    data, err = load_orchestration_config(repo)   # the working tree, as finish's validate reads it
    assert err is None and data["policy"]["new_gate"] is True
    assert effective_config(repo, "HEAD") == (effective_config(repo)[0], None)


def test_the_gate_and_finish_pass_once_the_integration_branch_has_the_key(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _leaf_changes(repo, ORCHESTRATION, _add_property("policy", "new_gate", {"type": "boolean"}))
    head = commit_file(repo, "roadmap/orchestration.yaml", POLICY_KEY, "turn the new gate on")
    git(repo, "checkout", "-q", "dev")
    git(repo, "merge", "-q", "--ff-only", "feature/rm-thing")   # the gate reads policy from here
    git(repo, "checkout", "-q", "feature/rm-thing")
    _review_with(repo, head, "")
    gate = evaluate_gate(repo, NODE, head)
    assert gate.config_error is None and gate.passed, gate.problems()
    gate_holds_at_head_or_exit(repo, NODE)   # finish-this-task's check; raises SystemExit when unmet


def test_a_review_field_the_leaf_adds_counts_at_that_commit_only(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    before = git(repo, "rev-parse", "HEAD")
    head = _leaf_changes(repo, REVIEW_RECORD, _add_property("", "effort", {"type": "string"}))
    _review_with(repo, head, "effort: high")
    assert evaluate_gate(repo, NODE, head).passed
    older = load_review(_review_with(repo, before, "effort: high"))   # that commit has no such schema
    assert not older.ok and "effort" in " ".join(older.errors)


def test_a_handoff_key_the_leaf_adds_keeps_its_ready_file(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = _leaf_changes(repo, HANDOFF, _add_property("", "lane", {"type": "string"}))
    data = {"node_id": "M1.1", "agent": "opus", "branch": "feature/rm-thing", "commit": head,
            "base": git(repo, "rev-parse", "dev"), "changed_paths": ["src/a.py"], "lane": "worktree"}
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "READY-opus.md").write_text(render_front_matter(data, "done\n"), encoding="utf-8")
    ready = latest_ready(repo, "M1.1", "feature/rm-thing", ["A1", "A2"])   # what handoff status reads
    assert ready is not None and ready.data["lane"] == "worktree"


def test_a_git_workflow_key_the_leaf_adds_keeps_the_review_switch_readable(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _leaf_changes(repo, GIT_WORKFLOW, _add_property("", "new_flag", {"type": "boolean"}))
    wf = repo / "roadmap" / "git-workflow.yaml"
    wf.write_text(wf.read_text(encoding="utf-8") + "new_flag: true\n", encoding="utf-8")
    assert load_git_workflow_config(repo)[1] is None
    assert require_implementation_review_before_finish(repo)


def test_outside_a_specy_road_checkout_only_the_installed_schema_counts(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD")
    r = load_review(_review_with(repo, head, "effort: high"))
    assert not r.ok and "effort" in " ".join(r.errors)
    commit_file(repo, "roadmap/orchestration.yaml", POLICY_KEY, "an unknown key")
    assert "new_gate" in load_orchestration_config(repo)[1]


def test_a_checkout_copy_equal_to_the_installed_one_changes_nothing(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    head = _leaf_changes(repo, REVIEW_RECORD, lambda schema: None)
    r = load_review(_review_with(repo, head, "effort: high"))
    assert not r.ok and "effort" in " ".join(r.errors)


def test_a_record_value_never_reaches_git_as_an_option(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _leaf_changes(repo, REVIEW_RECORD, _add_property("", "effort", {"type": "string"}))
    out = tmp_path / "written"
    assert revision_text(repo, REVIEW_RECORD, f"--output={out}") is None
    assert not out.exists()


def _worker_with(repo: Path, branch: str, extra: dict[str, Any]) -> str:
    """A worker record as a leaf's own code would write it: ``extra`` beside the installed fields."""
    rec = create_record(repo, "M1.1", "generic", "opus", repo, branch=branch)
    path = record_path(repo, rec.worker_id)
    path.write_text(yaml.safe_dump({**yaml.safe_load(path.read_text(encoding="utf-8")), **extra}), encoding="utf-8")
    return rec.worker_id


def test_a_worker_record_field_the_leaf_adds_is_read_and_kept(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _leaf_changes(repo, WORKER_RECORD, _add_property("", "lane", {"type": "string"}))
    wid = _worker_with(repo, "feature/rm-thing", {"lane": "worktree"})
    assert [r.worker_id for r in list_records(repo)] == [wid]   # what handoff status and the coordinator read
    set_state(repo, load_record(repo, wid), "running")   # the installed code saves the record
    saved = yaml.safe_load(record_path(repo, wid).read_text(encoding="utf-8"))
    assert saved["state"] == "running" and saved["lane"] == "worktree"


def test_a_worker_record_field_is_checked_against_the_record_s_own_branch(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _leaf_changes(repo, WORKER_RECORD, _add_property("", "lane", {"type": "string"}))
    wid = _worker_with(repo, "dev", {"lane": "worktree"})   # dev has no such schema
    with pytest.raises(WorkerError, match="lane"):
        load_record(repo, wid)
    assert list_records(repo) == []
