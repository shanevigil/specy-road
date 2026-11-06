"""M21.27: a filing into ``work/reviews/<ID>/`` takes the leaf's review lock, so it never voids a running reviewer.

``review record`` and the human approval of ``mark-implementation-reviewed`` wait up to ``FILING_WAIT`` for the lock,
then refuse, writing nothing, while ``review delegate`` (or ``prompt --channel cli --run``, the same lock) holds it.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, delegate_roster, run_review_cli, set_steps, verdict_step
from tests.review_repo_helpers import git, review_text

from specy_road import review_lock
from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.review_delegate import load_run
from specy_road.review_files import review_path, reviews_dir
from specy_road.review_lock import ReviewRunBusy, review_run_lock

# The reviewer harness: say it started, wait for the test to release it, then run the usual fake.
GATE = '''
import os, sys, time
ready, release = sys.argv[1], sys.argv[2]
open(ready, "w").write("started")
deadline = time.monotonic() + 60
while not os.path.exists(release) and time.monotonic() < deadline:
    time.sleep(0.05)
os.execv(sys.argv[3], sys.argv[3:])
'''

BUSY = "a reviewer run on M1.1 holds work/reviews/M1.1/; nothing was written"


def _wait_for(path: Path, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


def _snapshot(d: Path) -> dict[str, bytes]:
    return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def _record(repo: Path, model: str) -> int:
    notes = repo.parent / f"notes-{model}.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model))
    return run_review_cli("review", "record", "M1.1", "--model", model, "--verdict", "approve", "--file", str(notes),
                          "--repo-root", str(repo))


def test_filings_wait_for_and_refuse_during_a_reviewer_run(tmp_path: Path, monkeypatch, capsys) -> None:
    gate, ready, release = tmp_path / "gate.py", tmp_path / "ready", tmp_path / "release"
    gate.write_text(GATE)
    cli = f"{sys.executable} {gate} {ready} {release} {{fake}} {{prompt}} {{session_flag}}"
    repo, spec = delegate_repo(tmp_path, delegate_roster(cli))
    set_steps(repo, spec, verdict_step(repo))
    (repo / "work" / "implementation-summary-M1.1.md").write_text("## Summary\nDid it.\n")   # before the run starts
    rc: list[int] = []
    run = threading.Thread(target=lambda: rc.append(run_review_cli(
        "review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--repo-root", str(repo))))
    run.start()
    try:
        _wait_for(ready)
        handoff = reviews_dir(repo, "M1.1")
        before = _snapshot(handoff)
        monkeypatch.setattr(review_lock, "FILING_WAIT", 0)
        capsys.readouterr()
        assert _record(repo, "plain") == 1
        err = capsys.readouterr().err
        assert BUSY in err and "Traceback" not in err
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt="": "a")
        with pytest.raises(SystemExit) as e:
            mir.main(["--repo-root", str(repo)])
        assert e.value.code == 1
        err = capsys.readouterr().err
        assert BUSY in err and "Traceback" not in err
        assert _snapshot(handoff) == before
    finally:
        release.write_text("go")
        run.join(120)
    assert rc == [0]
    assert load_run(repo, "M1.1", "opus")["state"] == "complete"
    assert review_path(repo, "M1.1", "opus").is_file()   # the run's own filing still files
    assert _record(repo, "plain") == 0
    assert review_path(repo, "M1.1", "plain").is_file()


HOLDER = '''
import sys, time
from pathlib import Path
from specy_road.review_lock import review_run_lock
with review_run_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text("held")
    time.sleep(float(sys.argv[3]))
'''


@pytest.mark.parametrize(("hold", "wait", "acquires"), [(0.5, 10, True), (10, 0.3, False)])
def test_lock_wait_against_another_process(tmp_path: Path, hold: float, wait: float, acquires: bool) -> None:
    reviews, held = tmp_path / "reviews" / "M1.1", tmp_path / "held"
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(reviews), str(held), str(hold)])
    try:
        _wait_for(held)
        if acquires:
            with review_run_lock(reviews, wait=wait):
                pass
        else:
            with pytest.raises(ReviewRunBusy), review_run_lock(reviews, wait=wait):
                pass
    finally:
        proc.kill()
        proc.wait()


def test_two_filings_started_together_both_file(tmp_path: Path) -> None:
    repo, _spec = delegate_repo(tmp_path)
    notes = {}
    for model in ("opus", "plain"):
        notes[model] = repo.parent / f"notes-{model}.md"
        notes[model].write_text(review_text(git(repo, "rev-parse", "HEAD"), model=model))
    procs = [subprocess.Popen([sys.executable, "-c", "from specy_road.cli import main; main()", "review", "record", "M1.1", "--model", m,
                               "--verdict", "approve", "--file", str(notes[m]), "--repo-root", str(repo)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for m in notes]
    outs = [p.communicate(timeout=120) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    assert all(review_path(repo, "M1.1", m).is_file() for m in notes)


@pytest.mark.parametrize("node_id", ["/abs-node", "../escape", "M9.9"])
def test_unknown_absolute_or_dotdot_id_creates_nothing(tmp_path: Path, node_id: str, capsys) -> None:
    repo, _spec = delegate_repo(tmp_path)
    notes = repo.parent / "notes.md"
    notes.write_text(review_text(git(repo, "rev-parse", "HEAD"), model="plain"))
    before = sorted(tmp_path.rglob("*"))
    capsys.readouterr()
    assert run_review_cli("review", "record", node_id, "--model", "plain", "--verdict", "approve",
                          "--file", str(notes), "--repo-root", str(repo)) == 1
    assert f"unknown node id: {node_id}" in capsys.readouterr().err
    assert sorted(tmp_path.rglob("*")) == before
    assert not Path(node_id).is_absolute() or not Path(node_id).exists()
