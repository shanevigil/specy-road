"""M11.40: ``worker reconcile`` on a leaf whose claim is gone, ``--dismiss``, and untracked files.

A merged leaf has no registry claim: reconcile judges the worker against the
roadmap node's touch zones instead of refusing. ``--dismiss '<reason>'``
clears ``needs_reconcile`` and records the reason. Untracked files are
reported apart from the worker's changes, and outside the zones they are a
warning, not a breach.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.review_repo_helpers import commit_file, git
from tests.test_worker_cli import run_worker_cli, wait_for_worker
from tests.test_worker_m310_reconcile_status import worker_repo

from specy_road import worker_ops as ops
from specy_road import worker_state as ws


def _checkpointed(tmp_path: Path) -> tuple[Path, ws.WorkerRecord]:
    repo = worker_repo(tmp_path)
    rec, _c = ops.delegate(repo, "M1.1", "opus")
    rec = wait_for_worker(repo, rec.worker_id)
    ws.take_checkpoint(repo, rec)
    return repo, rec


def _release_claim(repo: Path) -> None:
    """What finish leaves behind once the leaf merged: no registry row for it."""
    reg = repo / "roadmap" / "registry.yaml"
    reg.write_text(yaml.safe_dump({"version": 1, "entries": []}), encoding="utf-8")
    git(repo, "add", "roadmap/registry.yaml")
    git(repo, "commit", "-qm", "chore(rm-thing): complete, deregister")


def _json(capsys, *argv: str) -> dict:
    capsys.readouterr()
    assert run_worker_cli(*argv, "--json") == 0
    return json.loads(capsys.readouterr().out)


def test_reconcile_of_a_merged_leaf_uses_the_nodes_touch_zones(tmp_path: Path) -> None:
    repo, rec = _checkpointed(tmp_path)
    commit_file(repo, "docs/stray.md", "# stray\n", "worker strays")
    commit_file(repo, "src/b.py", "print('b')\n", "worker in zone")
    ops.terminate(repo, rec.worker_id)
    _release_claim(repo)
    _r, delta = ops.reconcile(repo, rec.worker_id)   # refused with "no registry claim" before M11.40
    assert delta["claimed"] is False
    assert "src/b.py" in delta["changed"] and "docs/stray.md" in delta["changed"]
    assert delta["outside_touch_zones"] == ["docs/stray.md"]   # the node's zones: src
    assert delta["needs_reconcile"]


def test_reconcile_of_a_merged_leaf_with_only_in_zone_work_clears_the_flag(tmp_path: Path) -> None:
    repo, rec = _checkpointed(tmp_path)
    commit_file(repo, "src/b.py", "print('b')\n", "worker in zone")
    ws.add_flag(repo, rec, ws.FLAG_RECONCILE)
    _release_claim(repo)
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == [] and not delta["contract_changed"]
    assert not delta["needs_reconcile"]
    assert ws.FLAG_RECONCILE not in ws.load_record(repo, rec.worker_id).flags


def test_reconcile_still_refuses_an_unknown_node(tmp_path: Path) -> None:
    repo, rec = _checkpointed(tmp_path)
    ws.mutate(repo, rec, lambda r: setattr(r, "node_id", "M9.9"))
    with pytest.raises(ws.WorkerError, match="unknown node id: M9.9"):
        ops.reconcile(repo, rec.worker_id)


def test_dismiss_clears_the_flag_records_the_reason_and_list_and_sync_stop_showing_it(
    tmp_path: Path, capsys
) -> None:
    repo, rec = _checkpointed(tmp_path)
    commit_file(repo, "docs/stray.md", "# stray\n", "worker strays")
    ops.terminate(repo, rec.worker_id)
    _release_claim(repo)
    root = ("--repo-root", str(repo))
    assert _json(capsys, "worker", "reconcile", rec.worker_id, *root)["delta"]["needs_reconcile"]
    listed = _json(capsys, "worker", "list", "--all", *root)["workers"]
    assert ws.FLAG_RECONCILE in next(w for w in listed if w["worker_id"] == rec.worker_id)["flags"]

    out = _json(capsys, "worker", "reconcile", rec.worker_id, "--dismiss", "stray doc landed with the leaf", *root)
    assert out["delta"] == {"dismissed": "stray doc landed with the leaf", "was_flagged": True, "needs_reconcile": False}
    assert ws.FLAG_RECONCILE not in ws.load_record(repo, rec.worker_id).flags
    last = ws.events_since(repo, rec.worker_id)[-1]
    assert last.type == "reconcile" and last.detail["dismissed"] == "stray doc landed with the leaf"
    assert "stray doc landed with the leaf" in last.summary

    listed = _json(capsys, "worker", "list", "--all", *root)["workers"]
    assert ws.FLAG_RECONCILE not in next(w for w in listed if w["worker_id"] == rec.worker_id)["flags"]
    synced = _json(capsys, "worker", "sync", *root)["workers"]
    assert all(ws.FLAG_RECONCILE not in w["flags"] for w in synced)
    capsys.readouterr()
    assert run_worker_cli("worker", "list", "--all", *root) == 0
    assert ws.FLAG_RECONCILE not in capsys.readouterr().out


def test_dismiss_needs_a_reason(tmp_path: Path, capsys) -> None:
    repo, rec = _checkpointed(tmp_path)
    ws.add_flag(repo, rec, ws.FLAG_RECONCILE)
    assert run_worker_cli("worker", "reconcile", rec.worker_id, "--dismiss", " ", "--repo-root", str(repo)) == 1
    assert "needs a reason" in capsys.readouterr().err
    assert ws.FLAG_RECONCILE in ws.load_record(repo, rec.worker_id).flags


def test_an_untracked_file_outside_the_zones_is_a_warning_not_a_breach(tmp_path: Path, capsys) -> None:
    repo, rec = _checkpointed(tmp_path)
    commit_file(repo, "src/b.py", "print('b')\n", "worker in zone")
    (repo / "reports").mkdir()
    (repo / "reports" / "junit.xml").write_text("<testsuite/>\n")   # written by the project's own test run
    (repo / "src" / "scratch.py").write_text("x\n")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["changed"] == ["src/b.py"]
    assert delta["untracked"] == ["reports/junit.xml", "src/scratch.py"]
    assert delta["outside_touch_zones"] == []
    assert delta["untracked_outside_touch_zones"] == ["reports/junit.xml"]
    assert not delta["needs_reconcile"]
    capsys.readouterr()
    assert run_worker_cli("worker", "reconcile", rec.worker_id, "--repo-root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "warning: untracked, outside touch zones: reports/junit.xml" in out
    assert "OUTSIDE touch zones" not in out and "needs_reconcile=False" in out
    # The same file committed is the worker's change, and a breach.
    git(repo, "add", "reports/junit.xml")
    _r, delta = ops.reconcile(repo, rec.worker_id)
    assert delta["outside_touch_zones"] == ["reports/junit.xml"] and delta["needs_reconcile"]
