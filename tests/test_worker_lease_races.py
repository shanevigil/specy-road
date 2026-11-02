"""Lease races in ``policy.max_workers`` across checkouts (M11.4): a failed turn's cleanup against a resume."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from tests.test_worker_cli import _repo, run_worker_cli, wait_for_worker
from tests.test_worker_max_workers_global import _idle, _leases, _remote_and_clone

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
