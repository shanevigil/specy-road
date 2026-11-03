"""Lease races in ``policy.max_workers`` across checkouts (M11.4): a failed turn's cleanup against a resume."""

from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path

import pytest

from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker
from tests.test_worker_max_workers_global import _id_file, _idle, _leases, _remote_and_clone

from specy_road import worker_lease as lease
from specy_road import worker_ops as ops
from specy_road import worker_runner as runner


@pytest.mark.parametrize("argv", [[sys.executable, "-c", "import sys; sys.exit(1)"], ["/nonexistent/harness"]],
                         ids=["nonzero-exit", "harness-start-failure"])
def test_a_failed_turns_cleanup_cannot_delete_the_lease_of_a_resume_that_overlaps_it(tmp_path: Path, monkeypatch,
                                                                                    capsys, argv: list[str]) -> None:
    """The wrapper publishes failed and deletes its lease as one step under the workers lock; a resume started in
    between waits for both, so the lease it pushes survives and a second clone still refuses at the limit."""
    repo, _ = _repo(tmp_path, max_workers=1)
    remote, clone = _remote_and_clone(tmp_path, repo)
    cid = lease.checkout_id(repo)
    rec = _idle(repo, "M1.1")
    lease.acquire_lease(repo, rec, new=True)
    real, resumes, errors = runner.release_lease, [], []

    def resume():
        try:
            ops.resume(repo, rec.worker_id)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def release(repo_root, *ids):
        if not resumes:   # the old turn's cleanup: start a resume right now, while it runs
            resumes.append(threading.Thread(target=resume))
            resumes[0].start()
            resumes[0].join(1.0)   # blocked on the workers lock until this cleanup is done
        return real(repo_root, *ids)

    monkeypatch.setattr(runner, "release_lease", release)
    assert runner.run(repo, rec.worker_id, runner.Launch(argv=argv)) != 0
    resumes[0].join(30)
    assert errors == [] and wait_for_worker(repo, rec.worker_id).state == "idle"
    assert _leases(remote) == [f"{cid}/{rec.worker_id}"]   # the resumed turn's lease, not deleted by the old cleanup
    capsys.readouterr()
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--repo-root", str(clone)) == 1
    assert "0 workers active (and 1 leased by other checkouts" in capsys.readouterr().err


def test_three_callers_initialising_an_empty_id_agree_and_a_leased_worker_resumes_in_its_slot(
        tmp_path: Path, monkeypatch) -> None:
    """B reads the empty id file, then stalls while A initialises it and returns A's id; a third caller C runs in
    any gap B opens. All three must get A's id (a valid file is never set aside or rewritten), and a worker leased
    under it resumes in its own slot at max_workers 1."""
    repo, _ = _repo(tmp_path, max_workers=1)
    remote, _clone = _remote_and_clone(tmp_path, repo)
    _id_file(repo).write_text("", encoding="utf-8")
    ids: dict[str, str] = {}
    b_read, a_done = threading.Event(), threading.Event()
    real_read, real_rename = Path.read_text, os.rename

    def call(name: str) -> None:
        ids[name] = lease.checkout_id(repo)

    c = threading.Thread(target=call, args=("C",), name="C")

    def read_text(self, *args, **kwargs):
        text = real_read(self, *args, **kwargs)
        if self.name == "specy-road-checkout-id" and threading.current_thread().name == "B" and not b_read.is_set():
            b_read.set()
            a_done.wait(10)   # B saw it empty; A initialises and returns before B goes on
        return text

    def rename(src, dst):   # had B set A's valid file aside, C would initialise in the gap
        real_rename(src, dst)
        moved = real_read(Path(dst), encoding="utf-8").strip() if Path(dst).is_file() else ""
        valid = re.fullmatch(r"[0-9a-f]{32}", moved)
        if Path(src).name == "specy-road-checkout-id" and valid and not c.is_alive() and "C" not in ids:
            c.start()
            c.join(10)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(os, "rename", rename)
    b = threading.Thread(target=call, args=("B",), name="B")
    b.start()
    assert b_read.wait(10)
    ids["A"] = lease.checkout_id(repo)
    inode = _id_file(repo).stat().st_ino
    a_done.set()
    b.join(10)
    if "C" not in ids:   # no gap was opened: C simply arrives last
        c.start()
        c.join(10)
    first = ids["A"]
    assert ids == {"A": first, "B": first, "C": first}
    assert _id_file(repo).read_text(encoding="utf-8").strip() == first and _id_file(repo).stat().st_ino == inode
    rec = _idle(repo, "M1.1")
    lease.acquire_lease(repo, rec, new=True)
    ops.resume(repo, rec.worker_id)   # its own lease is not counted as another checkout's
    assert wait_for_worker(repo, rec.worker_id).state == "idle"
    assert _leases(remote) == [f"{first}/{rec.worker_id}"]
