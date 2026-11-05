"""M15.18: planned_test_changes is editable after pickup; an unplanned test removal is a required reviewer check."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.helpers import BUNDLED_SCRIPTS, script_subprocess_env
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_text
from tests.test_models_and_prompt import make_profile_repo

from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser
from specy_road.bundled_scripts.roadmap_edit_list_fields import planned_test_change_items
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.integrity_removals import REQUIRED_HEADING, unplanned_removals
from specy_road.registry_yaml import read_registry, registry_path

OLD = "removed-test: tests/test_leaf.py::test_old"
HEADING = f"## {REQUIRED_HEADING}"


def _crud(repo: Path, *argv: str) -> None:
    ns = build_parser().parse_args(["--repo-root", str(repo), *argv])
    ns.func(ns)


def _planned(repo: Path) -> list[str] | None:
    return next(n for n in load_roadmap(repo)["nodes"] if n["id"] == "M1.1").get("planned_test_changes")


def _validate(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BUNDLED_SCRIPTS / "validate_roadmap.py"), "--repo-root", str(repo)],
                          capture_output=True, text=True, env=script_subprocess_env())


def test_edit_node_sets_adds_and_removes_planned_test_changes_on_a_claimed_leaf(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert read_registry(registry_path(repo))["entries"][0]["node_id"] == "M1.1"   # claimed
    _crud(repo, "edit-node", "M1.1", "--set", f"planned_test_changes={OLD}",
          "--set", "planned_test_changes=new-skip: tests/test_leaf.py::test_slow")
    assert _planned(repo) == [OLD, "new-skip: tests/test_leaf.py::test_slow"]
    _crud(repo, "edit-node", "M1.1", "--add", "planned_test_changes=preserve: tests/test_leaf.py::test_keep",
          "--remove", "planned_test_changes=new-skip: tests/test_leaf.py::test_slow")
    assert _planned(repo) == [OLD, "preserve: tests/test_leaf.py::test_keep"]
    v = _validate(repo)
    assert v.returncode == 0, v.stderr + v.stdout
    _crud(repo, "edit-node", "M1.1", "--set", "planned_test_changes=")
    assert _planned(repo) is None


def test_add_node_takes_planned_test_change(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "add-node", "--id", "M1.2", "--type", "task", "--title", "Other", "--parent-id", "null",
          "--planned-test-change", OLD, "--planned-test-change", " new-skip: tests/test_leaf.py::test_slow ")
    node = next(n for n in load_roadmap(repo)["nodes"] if n["id"] == "M1.2")
    assert node["planned_test_changes"] == [OLD, "new-skip: tests/test_leaf.py::test_slow"]
    _crud(repo, "add-node", "--id", "M1.3", "--type", "task", "--title", "Third", "--parent-id", "null")
    assert "planned_test_changes" not in next(n for n in load_roadmap(repo)["nodes"] if n["id"] == "M1.3")
    v = _validate(repo)
    assert v.returncode == 0, v.stderr + v.stdout


def test_planned_test_change_items_are_stripped_and_blanks_dropped() -> None:
    assert planned_test_change_items(["  " + OLD + " ", "", "   "]) == [OLD]


def test_only_unlisted_removals_and_weakenings_are_unplanned() -> None:
    lines = [OLD, "assert-loss: tests/test_leaf.py::test_ok 2->1", "config-change: pytest.ini",
             "removed-test-file: tests/test_gone.py"]
    assert unplanned_removals(lines, {OLD}) == ["assert-loss: tests/test_leaf.py::test_ok 2->1",
                                                "removed-test-file: tests/test_gone.py"]


def _remove_old_test(repo: Path) -> None:
    """``tests/test_leaf.py`` with two tests lands on dev; the leaf branch deletes ``test_old``."""
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "tests/test_leaf.py", "def test_keep():\n    assert 1\n\n\ndef test_old():\n    assert 1\n",
                "baseline tests")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "--no-edit", "dev")
    commit_file(repo, "tests/test_leaf.py", "def test_keep():\n    assert 1\n", "drop test_old")


def _plan_on_branch(repo: Path) -> None:
    _crud(repo, "edit-node", "M1.1", "--add", f"planned_test_changes={OLD}")
    git(repo, "commit", "-qam", "authorize removing test_old")


def test_packet_puts_an_unlisted_removal_under_the_required_check(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _remove_old_test(repo)
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
    assert f"- `{OLD}`" in section and f'"{OLD}": pass' in section
    assert "policy.integrity_gate" in section   # integrity_gate is off here


def test_packet_has_no_required_check_for_a_listed_removal(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _remove_old_test(repo)
    _plan_on_branch(repo)
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert OLD in text.split("## Test integrity\n", 1)[1]   # still a finding
    assert HEADING not in text


def test_packet_reads_the_plan_from_the_integration_branch(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _remove_old_test(repo)
    git(repo, "checkout", "-q", "dev")
    _plan_on_branch(repo)
    git(repo, "checkout", "-q", "feature/rm-thing")
    assert HEADING not in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])


def _record(repo: Path, verdict: str, acceptance: dict[str, str]) -> int:
    data = yaml.safe_load(review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict=verdict).split("---")[1])
    data["acceptance"].update(acceptance)
    p = repo.parent / "notes-opus.md"
    p.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M1.1", "--model", "opus", "--verdict", verdict, "--file", str(p),
                         "--repo-root", str(repo)])
    return e.value.code


def test_record_refuses_an_approve_without_the_unplanned_removal_entry(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    _remove_old_test(repo)
    assert _record(repo, "approve", {}) == 1
    err = capsys.readouterr().err
    assert REQUIRED_HEADING in err and "tests/test_leaf.py::test_old" in err
    assert _record(repo, "approve", {OLD: "pass"}) == 0


def test_record_files_a_block_without_the_entry_and_refuses_a_fail_on_it(tmp_path: Path, capsys) -> None:
    repo = make_profile_repo(tmp_path)
    _remove_old_test(repo)
    assert _record(repo, "block", {}) == 0
    assert _record(repo, "block", {OLD: "fail"}) == 1   # an unjustified removal is a required_changes entry
    assert "'pass' was expected" in capsys.readouterr().err


def test_record_files_an_approve_when_the_removal_is_planned(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    _remove_old_test(repo)
    _plan_on_branch(repo)
    assert _record(repo, "approve", {}) == 0


def test_reviewer_prompt_requires_the_entry_whatever_integrity_gate_says(tmp_path: Path) -> None:
    from specy_road.bundled_scripts import role_prompt
    from specy_road.review_files import PACKET_NAME, reviews_dir

    repo = make_profile_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    (d / PACKET_NAME).write_text("# Review packet: `M1.1`\n")
    text, _prof, err = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")
    assert err is None
    assert f"`{HEADING}` section, your `acceptance` needs an entry for each line" in text
    assert "whatever `policy.integrity_gate` says" in text


def test_packet_with_an_explicit_base_still_reads_the_plan_from_the_integration_branch(tmp_path: Path) -> None:
    """``--base`` moves the diff range only; authorization made on dev after that base still counts (RC1)."""
    repo = make_profile_repo(tmp_path)
    _remove_old_test(repo)
    diff_base = git(repo, "merge-base", "dev", "feature/rm-thing")
    git(repo, "checkout", "-q", "dev")
    _plan_on_branch(repo)   # on dev only, after the diff base
    git(repo, "checkout", "-q", "feature/rm-thing")
    for base in (None, diff_base):
        text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[], base=base)
        assert OLD in text.split("## Test integrity\n", 1)[1] and HEADING not in text, base
    assert _record(repo, "approve", {}) == 0   # the record check agrees with the packet


def _milestone_with_a_removal(tmp_path: Path) -> Path:
    """Milestone ``M2``: leaf ``M2.1`` (alpha) deletes ``test_old`` from a test file dev had; both leaves landed."""
    from tests.test_milestone_full_review import _land_leaf, _merge_leaf, _set_status, make_milestone_repo

    from tests.test_models_and_prompt import ROSTER

    root = make_milestone_repo(tmp_path, orchestration=ROSTER, land=False)
    commit_file(root, "tests/test_ms.py", "def test_keep():\n    assert 1\n\n\ndef test_old():\n    assert 1\n",
                "baseline tests")
    git(root, "checkout", "-q", "-b", "feature/rm-alpha", "dev")
    commit_file(root, "roadmap/registry.yaml", "version: 1\nentries: []\n# alpha\n",
                "chore(rm-alpha): register as in-progress")
    commit_file(root, "tests/test_ms.py", "def test_keep():\n    assert 1\n", "drop test_old")
    _set_status(root, "M2.1", "Complete")
    git(root, "commit", "-qam", "chore(rm-alpha): complete, deregister")
    _merge_leaf(root, "M2.1")
    _land_leaf(root, "M2.2")
    return root


def _milestone_record(root: Path, tmp_path: Path, acceptance: dict[str, str]) -> int:
    data = {"node_id": "M2", "model": "sol", "date": "2026-11-04", "verdict": "approve",
            "commit": git(root, "rev-parse", "dev"), "acceptance": acceptance,
            "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
            "commands_rerun": [], "required_changes": [], "fresh_session": True, "authored_fix": False,
            "is_coordinator": False}
    notes = tmp_path / "notes-sol.md"
    notes.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "record", "M2", "--model", "sol", "--verdict", "approve", "--file", str(notes),
                         "--repo-root", str(root)])
    return e.value.code or 0


def test_milestone_review_gets_the_required_check_for_an_unplanned_removal(tmp_path: Path, capsys) -> None:
    """No milestone exception (RC2): the full review's packet and record enforce the check."""
    root = _milestone_with_a_removal(tmp_path)
    line = "removed-test: tests/test_ms.py::test_old"
    section = rp.build_packet(root, "M2", ref=None, verify_cmds=[]).split(HEADING, 1)[1].split("\n## ", 1)[0]
    assert f"- `{line}`" in section
    assert _milestone_record(root, tmp_path, {}) == 1
    assert REQUIRED_HEADING in capsys.readouterr().err
    assert _milestone_record(root, tmp_path, {line: "pass"}) == 0


def test_milestone_review_takes_a_leaf_plan_on_the_integration_branch(tmp_path: Path) -> None:
    root = _milestone_with_a_removal(tmp_path)
    _crud(root, "edit-node", "M2.1", "--add", "planned_test_changes=removed-test: tests/test_ms.py::test_old")
    git(root, "commit", "-qam", "authorize removing test_old")
    assert HEADING not in rp.build_packet(root, "M2", ref=None, verify_cmds=[])
    assert _milestone_record(root, tmp_path, {}) == 0
