"""M22.16 (rc4 re-test): a whole refusal summary (D15c), no parse reason after a capacity failure (D17), and the
reviewer's process group ended when its run ends (D18).

The process cases run :data:`GROUP_FAKE` as ``claude`` on PATH, its prompt (a packet larger than a pipe buffer)
on stdin: a reviewer that starts a background child in its own process group, holding stdin unread and stdout,
and waits for the child's handshake before it goes on, so the prompt's delivery blocks. The child waits until it
is signalled (bounded at 60 s). No case sleeps.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.review_delegate_helpers import CAPACITY, delegate_repo, set_steps, verdict_step
from tests.test_models_and_prompt import run_main
from tests.test_review_record_write import GENERIC

from specy_road import review_files as rf
from specy_road.bundled_scripts import role_prompt
from specy_road.review_delegate import delegate, load_run

LONG = ("The change keeps every existing caller and its behaviour while it adds the summary helper for each "
        "refusal path, " * 6).strip()
MORE = [f"Line {n} reads as an observation of the change" for n in range(9)]
EXHAUSTED = "RetriableError: [resource_exhausted] Resource has been exhausted (e.g. check quota)."

GROUP_FAKE = '''#!{python}
import json, os, signal, subprocess, sys, threading
spec = json.loads(open(os.environ["FAKE_GROUP_SPEC"]).read())
child = "import os, sys, threading; open(sys.argv[1], 'w').write(str(os.getpid())); os.write(int(sys.argv[2]), b'k'); threading.Event().wait(60)"
r, w = os.pipe()
subprocess.Popen([sys.executable, "-c", child, spec["pidfile"], str(w)], pass_fds=(w,))   # holds stdin and stdout
os.close(w)
os.read(r, 1)   # the handshake: the child is running and its pid is written
print("reviewing", flush=True)   # the prompt on stdin is never read: its delivery blocks
if spec.get("interrupt"):
    os.kill(spec["caller"], signal.SIGINT)   # Ctrl-C reaches the caller only: the reviewer has a session of its own
    threading.Event().wait(60)
'''

#: A packet larger than any pipe buffer, so the prompt (which inlines it) cannot be delivered to a reviewer that
#: does not read it.
BIG_PACKET = "# Review packet\n\n**Commit under review:** HEAD\n\n" + "Packet line kept for its size.\n" * 20000
GROUP_ROSTER = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
                "  - {id: opus, family: anthropic, roles: [reviewer], harness: claude-code}\n")


def _refused(repo: Path, model: str = "opus") -> dict:
    step = verdict_step(repo, model=model)
    return {**step, "answer": {**step["answer"], "notes": "## Findings\n\n" + "\n".join([LONG, *MORE])}}


def _delegate(repo: Path, model: str = "opus", **kw) -> dict:
    return delegate(repo, "M1.1", model, backoff=0, sleep=lambda _s: None, **kw)


def _summary(model: str = "opus") -> str:
    return (f"rerun requested: review record refused the output: notes line 4 is an observation: {LONG} (9 more; "
            f"full text in work/reviews/M1.1/REJECTED-{model}.md)")


@pytest.mark.parametrize("path", ["immediate", "resumed"])
def test_a_refusal_summary_names_the_first_line_whole_and_counts_the_rest(tmp_path: Path, path: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, _refused(repo))
    run = _delegate(repo)   # the initial refusal, then the immediate repair turn's
    if path == "resumed":
        run = _delegate(repo, resume=True)   # the stored refusal, then the resumed repair turn's
    assert run["state"] == "incomplete"
    assert run["reason"] == f"{_summary()}; after the repair turn, {_summary()}"


def test_the_initial_refusal_summary_through_prompt_run(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {**_refused(repo, "gem"), "plain": True})
    assert run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 1
    assert f"rerun: {_summary('gem')}" in capsys.readouterr().err.splitlines()


@pytest.mark.parametrize("turn", ["initial", "repair"])
def test_a_capacity_failure_has_no_parse_reason(tmp_path: Path, turn: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    exhausted = {"error": EXHAUSTED, "after": EXHAUSTED, "exit": 1}   # the harness's own error line, after the stream
    set_steps(repo, spec, *([_refused(repo)] if turn == "repair" else []), exhausted)
    run = _delegate(repo, retries=3)
    assert [a["capacity"] for a in run["attempts"]][-4:] == [True] * 4
    assert run["state"] == "incomplete" and run["reason"].startswith("capacity error after 4 attempt(s): ")
    assert "not one JSON object" not in run["reason"] and "review record refused" not in run["reason"]
    assert CAPACITY not in run["reason"]   # the shared fake's other capacity text: this one is the run's own


def _group_repo(tmp_path: Path, monkeypatch, interrupt: bool = False) -> tuple[Path, Path]:
    """A repo whose ``opus`` reviewer is :data:`GROUP_FAKE` as ``claude`` on PATH: its prompt goes on stdin."""
    repo, _spec = delegate_repo(tmp_path, GROUP_ROSTER)
    (rf.reviews_dir(repo, "M1.1") / "PACKET.md").write_text(BIG_PACKET)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text(GROUP_FAKE.format(python=sys.executable))
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    pidfile, spec = tmp_path / "child.pid", tmp_path / "group.json"
    spec.write_text(json.dumps({"pidfile": str(pidfile), "interrupt": interrupt, "caller": os.getpid()}))
    monkeypatch.setenv("FAKE_GROUP_SPEC", str(spec))
    return repo, pidfile


def _run(runner: str, repo: Path) -> None:
    if runner == "delegate":
        _delegate(repo, retries=0)
    else:
        run_main(role_prompt, "M1.1", "--model", "opus", "--role", "reviewer", "--channel", "cli", "--run",
                 "--repo-root", str(repo))


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


@pytest.mark.parametrize("runner", ["delegate", "prompt-run"])
def test_a_reviewer_exiting_while_its_prompt_is_undelivered_ends_its_group_and_the_run(
        tmp_path: Path, monkeypatch, runner: str) -> None:
    """The reviewer exits; its background child holds stdout and stdin unread, so the prompt's delivery blocks."""
    repo, pidfile = _group_repo(tmp_path, monkeypatch)
    start = time.monotonic()
    _run(runner, repo)
    assert time.monotonic() - start < 30   # ended by the run, not after the child's own 60 s
    assert _gone(int(pidfile.read_text()))
    assert load_run(repo, "M1.1", "opus")["state"] == "incomplete"


@pytest.mark.parametrize("runner", ["delegate", "prompt-run"])
def test_an_interrupt_while_the_prompt_is_undelivered_ends_the_reviewers_group_and_closes_the_run(
        tmp_path: Path, monkeypatch, runner: str) -> None:
    repo, pidfile = _group_repo(tmp_path, monkeypatch, interrupt=True)
    old = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        with pytest.raises(KeyboardInterrupt):
            _run(runner, repo)
    finally:
        signal.signal(signal.SIGINT, old)
    assert _gone(int(pidfile.read_text()))
    run = load_run(repo, "M1.1", "opus")
    assert run["state"] == "incomplete" and run["reason"].startswith("interrupted")


def test_a_reviewer_that_leaves_nothing_gets_no_signal(tmp_path: Path, monkeypatch) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    sent: list[tuple[int, int]] = []
    real = os.killpg
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)) or real(pgid, sig))
    mine = subprocess.Popen([sys.executable, "-c", "import threading; threading.Event().wait(60)"])   # caller's group
    try:
        run = _delegate(repo)
        assert run["outcome"] == "recorded" and rf.review_path(repo, "M1.1", "opus").is_file()
        assert sent == [] and mine.poll() is None
    finally:
        mine.kill()
        mine.wait()
