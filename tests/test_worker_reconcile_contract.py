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

from tests.review_repo_helpers import NODE, commit_file, git
from tests.test_worker_cli import wait_for_worker
from tests.test_worker_m310_reconcile_status import worker_repo

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts.roadmap_crud_ops import cmd_edit


def _edit(repo: Path, *sets: str) -> None:
    cmd_edit(SimpleNamespace(repo_root=str(repo), node_id="M1.1", set=list(sets), sync_codename=False))


def _linked(tmp_path: Path) -> tuple[Path, ws.WorkerRecord, Path]:
    """A coordinator on ``dev`` and a checkpointed worker in a linked worktree of the claim's branch."""
    repo = worker_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    rec = wait_for_worker(repo, rec.worker_id)
    ws.take_checkpoint(repo, rec)
    return repo, rec, Path(rec.worktree)


def test_reconcile_reads_the_zones_edit_node_widened_after_delegation(tmp_path: Path) -> None:
    repo, rec, wt = _linked(tmp_path)
    commit_file(wt, "docs/new.md", "# new\n", "worker writes docs")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == ["docs/new.md"]
    _edit(repo, "touch_zones=src", "touch_zones=docs")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == []
    assert delta["contract_changed"]   # the zones are the leaf's own contract


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


def test_the_integration_branch_moving_is_not_a_contract_change(tmp_path: Path) -> None:
    repo, rec, _wt = _linked(tmp_path)
    commit_file(repo, "shared/README.md", "# Shared\n\nA new contract index.\n", "dev moves on")
    _edit(repo, "status=Blocked")   # progress, not contract
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert not delta["contract_changed"] and not delta["needs_reconcile"], delta


@pytest.mark.parametrize("change", ["acceptance", "touch_zones", "sheet"])
def test_a_change_to_the_leafs_own_contract_is_reported(tmp_path: Path, change: str) -> None:
    repo, rec, _wt = _linked(tmp_path)
    if change == "sheet":
        sheet = repo / NODE["planning_dir"]
        sheet.write_text(sheet.read_text(encoding="utf-8") + "\nAlso do the other thing.\n", encoding="utf-8")
    elif change == "acceptance":
        _edit(repo, "acceptance=a.py exists", "acceptance=b.py exists")
    else:
        _edit(repo, "touch_zones=src", "touch_zones=lib")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["contract_changed"] and delta["needs_reconcile"]
