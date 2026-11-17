"""M11.6: ``worker reconcile`` judges a worker against the leaf's current contract.

The zones are the claim row's at reconcile time (edit-node keeps it in step),
paths a merge of the integration branch brought onto the leaf branch are not
the worker's, and the brief counts as changed only when the leaf's own
contract (execution target, acceptance, touch zones, planning sheet) did.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.support.review import NODE, commit_file, git
from tests.support.harness import wait_for_worker
from tests.support.extracted.worker_repos import worker_repo

from specy_road.orchestration.workers import worker_ops as ops
from specy_road.orchestration.workers import worker_state as ws
from specy_road.roadmap_crud_ops import cmd_edit
from tests.support.same.edit_70b56ec19282 import edit
from tests.support.review import make_review_repo
import shutil
from specy_road.orchestration.workers import worker_reconcile as wr
from specy_road.bundled_scripts import review_packet as rp
from specy_road.finish_implementation_check import changed_paths
from specy_road.git_changed_paths import diff_paths, parse_name_status
from specy_road.review_target import resolve_target
from tests.support.extracted.folded_review_evidence import _roster
from tests.support.same.git_84c8ad8f55f9 import git as git_folded
from tests.support.harness import make_worker_repo
from tests.support.cli import run_worker_cli




def _linked(tmp_path: Path) -> tuple[Path, ws.WorkerRecord, Path]:
    """A coordinator on ``dev`` and a checkpointed worker in a linked worktree of the claim's branch."""
    repo = worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    rec = wait_for_worker(repo, rec.worker_id)
    ws.take_checkpoint(repo, rec)
    return repo, rec, Path(rec.worktree)


@pytest.mark.slow
def test_reconcile_reads_the_zones_edit_node_widened_after_delegation(tmp_path: Path) -> None:
    repo, rec, wt = _linked(tmp_path)
    commit_file(wt, "docs/new.md", "# new\n", "worker writes docs")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == ["docs/new.md"]
    edit(repo, "touch_zones=src", "touch_zones=docs")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == []
    assert delta["contract_changed"]   # the zones are the leaf's own contract


@pytest.mark.slow
@pytest.mark.parametrize("remote", ["stale", "diverged"])
def test_paths_merged_in_from_the_integration_branch_are_not_the_workers(tmp_path: Path, remote: str) -> None:
    repo, rec, wt = _linked(tmp_path)
    before = git(repo, "rev-parse", "dev")
    commit_file(wt, "docs/own.md", "# own\n", "worker strays")
    commit_file(repo, "other/merged.txt", "dev\n", "dev moves on")
    git(wt, "merge", "-q", "--no-edit", "dev")
    # A remote-tracking ref behind the local branch that was merged: the local one still counts.
    git(repo, "update-ref", "refs/remotes/origin/dev", before)
    if remote == "diverged":   # the remote went its own way too, and that was merged as well
        git(repo, "checkout", "-q", "--detach", before)
        commit_file(repo, "other/remote.txt", "remote\n", "the remote moves on")
        git(repo, "update-ref", "refs/remotes/origin/dev", "HEAD")
        git(repo, "checkout", "-q", "dev")
        git(wt, "merge", "-q", "--no-edit", "origin/dev")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert not {"other/merged.txt", "other/remote.txt"} & set(delta["changed"])
    assert delta["outside_touch_zones"] == ["docs/own.md"]
    # Past a checkpoint after the merge, deleting the merged file is the worker's
    # own change: the stale remote base, which never had the file, must not hide it.
    ws.take_checkpoint(repo, ws.load_record(repo, rec.worker_id))
    git(wt, "rm", "-q", "other/merged.txt")
    git(wt, "commit", "-qm", "worker deletes the merged file")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["changed"] == ["other/merged.txt"]
    assert delta["outside_touch_zones"] == ["docs/own.md", "other/merged.txt"] and delta["needs_reconcile"]


def test_an_edit_folded_into_a_merge_commit_is_the_workers(tmp_path: Path) -> None:
    repo, rec, wt = _linked(tmp_path)
    commit_file(repo, "other/merged.txt", "dev\n", "dev moves on")
    git(wt, "merge", "-q", "--no-commit", "dev")
    commit_file(wt, "docs/folded.md", "# folded\n", "merge dev, with an edit of its own")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["changed"] == ["docs/folded.md"]
    assert delta["outside_touch_zones"] == ["docs/folded.md"]


@pytest.mark.slow
def test_a_rename_folded_into_a_merge_counts_on_both_sides(tmp_path: Path) -> None:
    repo, rec, wt = _linked(tmp_path)
    commit_file(repo, "outside/source.txt", "same line\n" * 20, "dev adds a file")
    git(wt, "merge", "-q", "--no-edit", "dev")   # the source is on both parents
    ws.take_checkpoint(repo, ws.load_record(repo, rec.worker_id))
    commit_file(wt, "src/own.txt", "own\n", "worker commits in zone")
    commit_file(repo, "other/integration.txt", "dev\n", "dev moves on")
    git(wt, "merge", "-q", "--no-commit", "dev")
    git(wt, "mv", "outside/source.txt", "src/dest.txt")
    commit_file(wt, "zoutside/extra.txt", "extra\n", "merge dev, renaming and adding outside the zone")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["changed"] == ["outside/source.txt", "src/dest.txt", "src/own.txt", "zoutside/extra.txt"]
    assert delta["outside_touch_zones"] == ["outside/source.txt", "zoutside/extra.txt"]
    assert delta["needs_reconcile"]


@pytest.mark.slow
def test_the_integration_branch_moving_is_not_a_contract_change(tmp_path: Path) -> None:
    repo, rec, _wt = _linked(tmp_path)
    commit_file(repo, "shared/README.md", "# Shared\n\nA new contract index.\n", "dev moves on")
    edit(repo, "status=Blocked")   # progress, not contract
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert not delta["contract_changed"] and not delta["needs_reconcile"], delta


@pytest.mark.slow
@pytest.mark.parametrize("change", ["acceptance", "touch_zones", "sheet"])
def test_a_change_to_the_leafs_own_contract_is_reported(tmp_path: Path, change: str) -> None:
    repo, rec, _wt = _linked(tmp_path)
    if change == "sheet":
        sheet = repo / NODE["planning_dir"]
        sheet.write_text(sheet.read_text(encoding="utf-8") + "\nAlso do the other thing.\n", encoding="utf-8")
    elif change == "acceptance":
        edit(repo, "acceptance=a.py exists", "acceptance=b.py exists")
    else:
        edit(repo, "touch_zones=src", "touch_zones=lib")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["contract_changed"] and delta["needs_reconcile"]



# --- Gemini B1 / Sol F2 ---------------------------------------------------------

def test_reconcile_remembers_a_breach_from_before_the_handoff(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sid-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    (repo / "outside.txt").write_text("breach\n")
    git(repo, "add", "outside.txt")
    git(repo, "commit", "-qm", "worker touched outside")
    _r, d1 = ops.reconcile(repo, rec.worker_id)
    assert "outside.txt" in d1["outside_touch_zones"] and d1["needs_reconcile"]
    ops.handoff(repo, rec.worker_id)
    ops.reclaim(repo, rec.worker_id)
    _r, d2 = ops.reconcile(repo, rec.worker_id)
    assert "outside.txt" in d2["outside_touch_zones"] and d2["needs_reconcile"]



# --- B2 -------------------------------------------------------------------

def _rename_into_zone(tmp_path: Path, src: str, dst: str) -> Path:
    """A repo whose base holds ``src`` and whose feature branch renames it to ``dst``."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, src, "# old\n" * 20, "base doc")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "dev")
    git(repo, "mv", src, dst)
    git(repo, "commit", "-qm", "rename")
    return repo



def test_parse_name_status_returns_both_sides_of_renames_and_copies() -> None:
    out = "M\0a.py\0R100\0docs/old name.md\0src/old name.md\0C75\0src/a.py\0src/b.py\0D\0gone\ttab\0"
    assert parse_name_status(out) == {"a.py", "docs/old name.md", "src/old name.md", "src/a.py", "src/b.py", "gone\ttab"}
    assert parse_name_status("") == set()



def test_committed_rename_into_the_zone_is_reported_on_both_sides(tmp_path: Path) -> None:
    repo = _rename_into_zone(tmp_path, "docs/old name.md", "src/old name.md")
    assert "R100" in git(repo, "diff", "--name-status", "dev...HEAD")   # git does see the rename
    t = resolve_target(repo, "M1.1")
    paths, lines = rp.changed_paths_section(repo, t)
    assert "docs/old name.md" in paths and "src/old name.md" in paths
    assert any("docs/old name.md" in ln and "outside touch zones" in ln for ln in lines)
    assert "docs/old name.md" in wr._changed_since(repo, t.base)
    assert "docs/old name.md" in changed_paths(repo, "refs/heads/dev")



def test_rename_out_of_the_zone_keeps_the_source_inside_it(tmp_path: Path) -> None:
    repo = _rename_into_zone(tmp_path, "src/keep me.py", "docs/keep me.py")
    t = resolve_target(repo, "M1.1")
    paths, lines = rp.changed_paths_section(repo, t)
    assert "src/keep me.py" in paths and "docs/keep me.py" in paths
    assert any("docs/keep me.py" in ln and "outside touch zones" in ln for ln in lines)
    assert not any("src/keep me.py" in ln and "outside" in ln for ln in lines)



def test_uncommitted_rename_is_seen_by_reconcile(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "mv", "src/a.py", "docs/a.py")                      # staged
    assert wr._changed_since(repo, "HEAD") == ["docs/a.py", "src/a.py"]
    git(repo, "mv", "docs/a.py", "src/a.py")
    (repo / "src" / "a.py").rename(repo / "docs" / "a moved.py")   # unstaged delete + untracked file
    assert wr._changed_since(repo, "HEAD") == ["src/a.py"]   # the untracked side is reported on its own (M11.40)



def test_copy_is_reported_on_both_sides(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    commit_file(repo, "docs/big.md", "line\n" * 40, "base doc")
    git(repo, "checkout", "-q", "feature/rm-thing")
    git(repo, "merge", "-q", "dev")
    shutil.copy(repo / "docs" / "big.md", repo / "src" / "big.md")
    (repo / "docs" / "big.md").write_text("line\n" * 40 + "more\n")   # a touched source lets git find the copy
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "copy")
    assert "C" in git(repo, "diff", "--name-status", "--find-copies", "dev...HEAD").split()[-3][0]
    assert {"docs/big.md", "src/big.md"} <= set(diff_paths(repo, "dev...HEAD"))



def test_diff_paths_is_none_outside_git(tmp_path: Path) -> None:
    assert diff_paths(tmp_path, "HEAD") is None



def test_reconcile_flags_a_tree_off_the_workers_branch(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo, branch="feature/rm-thing")
    ws.set_state(repo, rec, "idle")
    git_folded(repo, "checkout", "-q", "dev")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["needs_reconcile"] and "has dev checked out" in delta["branch_mismatch"]



@pytest.mark.slow
def test_reconcile_treats_a_directory_touch_zone_as_covering_files(tmp_path: Path) -> None:
    repo = worker_repo(tmp_path)
    reg = repo / "roadmap" / "registry.yaml"
    reg.write_text(reg.read_text(encoding="utf-8").replace("- src", "- schemas/"))
    git(repo, "add", "roadmap/registry.yaml")
    git(repo, "commit", "-qm", "zones")
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.take_checkpoint(repo, rec)
    (repo / "schemas" / "node.json").parent.mkdir(parents=True, exist_ok=True)
    (repo / "schemas" / "node.json").write_text("{}\n")
    git(repo, "add", "schemas/node.json")
    git(repo, "commit", "-qm", "schema")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert "schemas/node.json" in delta["changed"]
    assert delta["outside_touch_zones"] == [] and not delta["needs_reconcile"]



def test_reconcile_ignores_prompt_hash_drift_when_brief_is_byte_identical(tmp_path: Path) -> None:
    repo = worker_repo(tmp_path)
    run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(repo))
    rec = wait_for_worker(repo, "w-0001")
    ws.take_checkpoint(repo, rec)
    (repo / "src" / "touch.py").write_text("x\n")
    git(repo, "add", "src/touch.py")
    git(repo, "commit", "-qm", "impl progress")
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert not delta["contract_changed"] and not delta["needs_reconcile"]



def test_reconcile_counts_an_unbuildable_prompt_as_a_contract_change(tmp_path: Path) -> None:
    repo, _ = make_worker_repo(tmp_path)
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    wait_for_worker(repo, rec.worker_id)
    orch = repo / "roadmap" / "orchestration.yaml"
    orch.write_text(orch.read_text().replace("roles: [executor, reviewer], harness", "roles: [reviewer], harness"))
    git(repo, "commit", "-qm", "roster change", "--", "roadmap/orchestration.yaml")
    git(repo, "update-ref", "refs/heads/dev", "HEAD")     # routing reads the roster from the integration branch
    _rec, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["contract_changed"] and delta["needs_reconcile"]
