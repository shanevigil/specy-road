"""M15.36: a claude-code worker never relies on ``claude -p``'s default mode, and forced bare needs a key."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.worker_adapters import Launch
from tests.review_repo_helpers import claude_code_reviewer_repo
from tests.test_models_and_prompt import commit_profile

KEY = "sk-ant-m15-36-do-not-print"
EXPLICIT = ["--setting-sources", "user,project,local"]


@pytest.fixture
def account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No key and an empty Claude account: nothing from the developer's own login is read."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty-claude-config"))


def _repo(tmp_path: Path, *, bare: bool, channels: str = "") -> Path:
    repo = claude_code_reviewer_repo(tmp_path, channels)
    if bare:   # the profile's access.launch_mode forces bare (a roster entry takes no launch_mode)
        prof = repo / "model-profiles" / "anthropic-claude" / "claude-opus-5-5.md"
        prof.write_text(prof.read_text().replace("launch_mode: full", "launch_mode: bare", 1))
        commit_profile(repo)
    return repo


def _files(repo: Path) -> tuple[dict[Path, bytes], str]:
    """Every file under ``work/.workers`` (records, events, mailbox) byte for byte, and every lease ref, local and remote."""
    d = ws.workers_dir(repo)
    files = {p: p.read_bytes() for p in d.rglob("*") if p.is_file()} if d.exists() else {}
    git = ["git", "-C", str(repo)]
    refs = subprocess.run([*git, "for-each-ref", "refs/specy-road"], capture_output=True, text=True).stdout
    for remote in subprocess.run([*git, "remote"], capture_output=True, text=True).stdout.split():
        refs += subprocess.run([*git, "ls-remote", remote, "refs/specy-road/*"], capture_output=True, text=True).stdout
    return files, refs


def _launch_and_resume(repo: Path, monkeypatch: pytest.MonkeyPatch) -> list[Launch]:
    launches: list[Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    rec, _ = ops.delegate(repo, "M1.1", "opus")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "6f1c1b7e-0000-4000-8000-000000000001"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.message(repo, rec.worker_id, "go on")
    return launches


@pytest.mark.parametrize("bare,key,mode_flags,absent", [
    (False, None, EXPLICIT, "--bare"),             # subscription entry: every source named, never --bare
    (False, KEY, EXPLICIT, "--bare"),              # a key alone does not move a worker to bare
    (True, KEY, ["--bare"], "--setting-sources"),  # API-key entry: bare allowed
])
def test_launch_and_resume_name_their_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: None,
                                           bare: bool, key: str | None, mode_flags: list[str], absent: str) -> None:
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    repo = _repo(tmp_path, bare=bare)
    launches = _launch_and_resume(repo, monkeypatch)
    assert len(launches) == 2
    for launch in launches:
        assert launch.argv[1] == "-p" and launch.argv[2:2 + len(mode_flags)] == mode_flags
        assert absent not in launch.argv and KEY not in " ".join(launch.argv)
    assert "--resume" in launches[1].argv


def test_forced_bare_without_a_key_is_refused_before_any_worker_state(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: None) -> None:
    repo = _repo(tmp_path, bare=True)
    monkeypatch.setattr(ops, "spawn", lambda *a, **k: pytest.fail("the worker was spawned"))
    before = _files(repo)
    with pytest.raises(ws.WorkerError) as e:
        ops.delegate(repo, "M1.1", "opus")
    msg = str(e.value)
    assert "\n" not in msg and msg.startswith("worker auth: opus forces bare mode")
    assert "export ANTHROPIC_API_KEY" in msg and "subscription login" in msg
    assert _files(repo) == before and not ws.list_records(repo)


def _channels(**commands: str) -> str:
    """Roster YAML for ``channels``, as :func:`claude_code_reviewer_repo` inserts it."""
    return "    channels:\n" + "".join(f"      {k}: '{v}'\n" for k, v in commands.items()) if commands else ""


def _delegated(repo: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ws.WorkerRecord, list[Launch]]:
    """An idle worker with a session, launched with a key that is then gone: the next turn has no credentials."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    launches: list[Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    rec, _ = ops.delegate(repo, "M1.1", "opus")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "6f1c1b7e-0000-4000-8000-000000000001"))
    ws.set_state(repo, rec, "idle", pid=None)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    return rec, launches


@pytest.mark.parametrize("channels", [
    {},                                                              # the default command throughout
    {"cli": "wrapper {prompt}"},                                     # no session placeholder: a resume runs the default
])
def test_resume_follows_the_same_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: None,
                                      channels: dict[str, str]) -> None:
    repo = _repo(tmp_path, bare=True, channels=_channels(**channels))
    rec, launches = _delegated(repo, monkeypatch)
    before = _files(repo)
    for send in (lambda: ops.message(repo, rec.worker_id, "go on"), lambda: ops.resume(repo, rec.worker_id)):
        with pytest.raises(ws.WorkerError, match=r"^worker auth: opus forces bare mode"):
            send()
    assert len(launches) == 1 and _files(repo) == before
    assert ws.load_record(repo, rec.worker_id).state == "idle"
    # Its wrapper died mid-turn: the refusal comes before the dead wrapper is reconciled, so nothing changes.
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    ws.set_state(repo, rec, "running", pid=dead.pid)
    before = _files(repo)
    for send in (lambda: ops.message(repo, rec.worker_id, "go on"), lambda: ops.resume(repo, rec.worker_id)):
        with pytest.raises(ws.WorkerError, match=r"^worker auth: opus forces bare mode"):
            send()
    assert _files(repo) == before and ws.load_record(repo, rec.worker_id).state == "running"
    assert len(launches) == 1
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)   # the key is back: the command that was refused is what runs
    ops.message(repo, rec.worker_id, "go on")
    assert launches[-1].argv[1:3] == ["-p", "--bare"] and "--resume" in launches[-1].argv


@pytest.mark.parametrize("channels", [
    {"cli": "wrapper {session_flag} {prompt}"},                      # the launch command resumes
    {"cli": "wrapper {prompt}", "cli_resume": "wrapper {session_flag} {prompt}"},
    {"cli_resume": "wrapper {session_flag} {prompt}"},               # only the resume is a roster command
])
def test_a_resume_on_a_roster_command_is_run_as_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: None,
                                                        channels: dict[str, str]) -> None:
    repo = _repo(tmp_path, bare=True, channels=_channels(**channels))
    rec, launches = _delegated(repo, monkeypatch)
    ops.message(repo, rec.worker_id, "go on")
    assert launches[-1].argv[:2] == ["sh", "-c"] and launches[-1].argv[2].startswith("wrapper --resume ")


def test_a_launch_is_checked_on_its_own_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: None) -> None:
    """A ``cli_resume`` says nothing about the launch, which runs the default command; a ``cli`` launch runs as written."""
    repo = _repo(tmp_path / "resume-only", bare=True, channels=_channels(cli_resume="wrapper {session_flag} {prompt}"))
    with pytest.raises(ws.WorkerError, match=r"^worker auth: opus forces bare mode"):
        ops.delegate(repo, "M1.1", "opus")
    repo = _repo(tmp_path / "custom", bare=True, channels=_channels(cli="wrapper {prompt}"))
    launches: list[Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    ops.delegate(repo, "M1.1", "opus")
    assert launches[0].argv[:2] == ["sh", "-c"]


def test_a_refused_rework_leaves_the_completed_worker_as_it_was(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: None) -> None:
    """``--rework`` terminates the completed worker only after every refusal: here the roster preflight fails."""
    repo = _repo(tmp_path, bare=False)
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: None)
    rec, _ = ops.delegate(repo, "M1.1", "opus")
    ws.set_state(repo, rec, "completed", pid=None)
    roster = repo / "roadmap" / "orchestration.yaml"
    roster.write_text(roster.read_text().replace("    harness: claude-code\n", "    harness: claude-code\n    preflight: 'exit 3'\n"))
    commit_profile(repo)
    before = _files(repo)
    with pytest.raises(ws.WorkerError, match=r"^preflight failed \(exit 3\)"):
        ops.delegate(repo, "M1.1", "opus", rework=True)
    assert _files(repo) == before and ws.load_record(repo, rec.worker_id).state == "completed"
