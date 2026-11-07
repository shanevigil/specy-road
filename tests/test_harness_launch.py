"""M15.9: harness launches survive a large prompt (A1, A2) and a harness binary off PATH (A3)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests.review_repo_helpers import make_review_repo

from specy_road import harness_binary as hb
from specy_road import worker_ops as ops
from specy_road import worker_state as ws
from specy_road.bundled_scripts import role_prompt_cli
from specy_road import review_delegate
from specy_road.review_files import reviews_dir
from specy_road.review_record_write import strict_schema
from specy_road.worker_adapter_base import (ARG_LIMIT, CODEX_REVIEW_POLICY, checked, file_instruction,
                                         oversized_arg)
from specy_road.worker_adapter_codex import CODEX_MEMORY_OFF, profile_home
from specy_road.worker_adapters import ADAPTERS, Launch, Unsupported

REAL_RESOLVE = hb.resolve   # taken at import, before conftest's autouse stub replaces it for each test

BIG = 200 * 1024    # an RCA prompt reached 197 KB; review packets are 134-139 KB
CAP = 32 * 1024     # A1: no argv element above this
#: The command each harness runs for a role with no default command (rca, a generic entry): the prompt by file.
CLIS = {"claude-code": "claude -p --model m < {prompt}", "codex": "codex exec -m m - < {prompt}",
        "cursor": "agent -p --model m < {prompt}", "generic": "my-harness --model m < {prompt}"}


@pytest.fixture
def prompt(tmp_path: Path) -> Path:
    p = tmp_path / "prompt.md"
    p.write_text("x" * BIG, encoding="utf-8")
    return p


def _role_argvs(harness: str, role: str, prompt: Path, tmp_path: Path, monkeypatch) -> list[list[str]]:
    """Every argv a ``role`` turn on ``harness`` can exec: launch and resume, a fresh and a resumed reviewer."""
    a = ADAPTERS[harness]
    if role == "rca" or harness == "generic":   # always the roster's command (run_plain_cli; generic launch)
        run: list[str] = []
        monkeypatch.setattr(role_prompt_cli.subprocess, "run",
                            lambda cmd, **_k: run.append(cmd) or subprocess.CompletedProcess(cmd, 0))
        assert role_prompt_cli.run_plain_cli(CLIS[harness], prompt, tmp_path, []) == 0
        return [["sh", "-c", run[0]], a.launch(prompt, tmp_path, "m", CLIS[harness]).argv]
    if role == "executor":
        return [a.launch(prompt, tmp_path, "m", None).argv, a.resume("s-1", prompt, tmp_path, "m", None).argv]
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(strict_schema(["A1", "A2", "A3"])), encoding="utf-8")
    return [a.reviewer_launch(prompt, "m", tmp_path, schema=schema, output=tmp_path / "out.json").argv,
            a.reviewer_launch(prompt, "m", tmp_path, session=("s-1", False), schema=schema).argv,
            a.reviewer_launch(prompt, "m", tmp_path, session=("s-1", True), schema=schema).argv]


@pytest.mark.parametrize("role", ["executor", "reviewer", "rca"])
@pytest.mark.parametrize("harness", ["claude-code", "codex", "cursor", "generic"])
def test_a_200_kib_prompt_never_puts_an_argument_over_32_kib(harness: str, role: str, prompt: Path, tmp_path: Path,
                                                              monkeypatch) -> None:
    argvs = _role_argvs(harness, role, prompt, tmp_path, monkeypatch)
    assert argvs
    for argv in argvs:
        assert max(len(a.encode("utf-8")) for a in argv) <= CAP, (harness, role, argv[:3])
        assert "x" * 1024 not in " ".join(argv)


def test_cursor_names_the_prompt_file_on_every_launch(prompt: Path, tmp_path: Path) -> None:
    told = file_instruction(prompt.resolve())
    cursor = ADAPTERS["cursor"]
    assert cursor.launch(prompt, tmp_path, "m", None).argv[-1] == told
    assert cursor.resume("s-1", prompt, tmp_path, "m", None).argv[-1] == told
    ask = cursor.reviewer_launch(prompt, "m", tmp_path)
    assert ask.argv[-1] == told and ask.argv[ask.argv.index("--mode") + 1] == "ask" and ask.stdin is None


# --- M22.33: a reviewer resume, the format-repair retry's included, runs on the model it was asked for -----------

#: A reviewer harness that appends its argv to $FAKE_CALLS and ends a clean turn with an empty final message, in
#: $FAKE_HARNESS's stream format, on the session it was given (--session-id, --resume, exec resume) or $FAKE_SID.
FAKE_REVIEWER = '''#!{python}
import json, os, sys
argv = sys.argv[1:]
open(os.environ["FAKE_CALLS"], "a").write(json.dumps(argv) + "\\n")
sys.stdin.read()
named = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("--session-id", "--resume")]
sid = named[0] if named else (argv[-2] if argv[:2] == ["exec", "resume"] else os.environ["FAKE_SID"])
if os.environ["FAKE_HARNESS"] == "codex":
    lines = [{{"type": "thread.started", "thread_id": sid}},
             {{"type": "item.completed", "item": {{"type": "agent_message", "text": ""}}}}, {{"type": "turn.completed"}}]
else:
    lines = [{{"type": "system", "subtype": "init", "session_id": sid, "model": "fake"}},
             {{"type": "result", "subtype": "success", "result": "", "session_id": sid}}]
for line in lines:
    print(json.dumps(line), flush=True)
'''


def _resumes(argv: list[str]) -> bool:
    return "--resume" in argv or argv[:2] == ["exec", "resume"]


@pytest.mark.parametrize(("harness", "flag"), [("claude-code", "--model"), ("codex", "-m"), ("cursor", "--model")])
def test_a_reviewer_resume_passes_the_requested_model(harness: str, flag: str, prompt: Path, tmp_path: Path,
                                                      monkeypatch) -> None:
    a = ADAPTERS[harness]
    resumed = a.reviewer_launch(prompt, "m", tmp_path, session=("s-1", True)).argv
    assert "s-1" in resumed and resumed[resumed.index(flag) + 1] == "m"
    fake, calls, sid = tmp_path / "tools" / "fake-reviewer", tmp_path / "calls.jsonl", str(uuid.uuid4())
    _exe(fake).write_text(FAKE_REVIEWER.format(python=sys.executable))
    for k, v in {"FAKE_CALLS": str(calls), "FAKE_HARNESS": harness, "FAKE_SID": sid}.items():
        monkeypatch.setenv(k, v)
    roster = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
              f"  - {{id: rev, family: other, roles: [reviewer], harness: {harness}, harness_bin: {fake}}}\n")
    repo = make_review_repo(tmp_path / "repo", orchestration=roster)
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n")
    # a clean turn with an empty final message: one format-repair turn, which resumes the reported session
    run = review_delegate.delegate(repo, "M1.1", "rev", retries=0, sleep=lambda _s: None)
    assert [at.get("repair", False) for at in run["attempts"]] == [False, True]
    argvs = [json.loads(line) for line in calls.read_text().splitlines()]
    (fresh,), (repair,) = [c for c in argvs if not _resumes(c)], [c for c in argvs if _resumes(c)]
    assert run["session_id"] in repair   # the repair resumes the session the fresh turn reported
    assert fresh[fresh.index(flag) + 1] == repair[repair.index(flag) + 1] == "rev"


def test_codex_reviewer_runs_memory_off_in_an_isolated_home(tmp_path: Path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("review it")
    schema, out = tmp_path / "s.json", tmp_path / "out.json"
    a = ADAPTERS["codex"]
    fresh = a.reviewer_launch(prompt, "m", tmp_path, schema=schema, output=out)
    assert fresh.argv == ["codex", "exec", "--json", "-m", "m", *CODEX_REVIEW_POLICY, *CODEX_MEMORY_OFF,
                          "--output-schema", str(schema), "-o", str(out), "-"]
    assert fresh.env == {"CODEX_HOME": str(profile_home("m"))}
    resumed = a.reviewer_launch(prompt, "m", tmp_path, session=("s-1", True))
    assert resumed.argv == ["codex", "exec", "resume", "--json", "-m", "m", *CODEX_REVIEW_POLICY, *CODEX_MEMORY_OFF,
                            "s-1", "-"]
    assert resumed.env == {"CODEX_HOME": str(profile_home("m"))}   # no rollout yet: the profile home
    home = profile_home("other")
    rollout = home / "sessions" / "2026" / "11" / "rollout-s-1.jsonl"
    rollout.parent.mkdir(parents=True)
    rollout.write_text("{}\n")
    found = a.reviewer_launch(prompt, "m", tmp_path, session=("s-1", True))
    assert found.argv == resumed.argv and found.env == {"CODEX_HOME": str(home)}


# --- A2: an argument over the OS limit is refused before exec --------------------------------------------------------

def test_a_prompt_text_command_over_the_limit_is_refused_by_every_adapter(prompt: Path, tmp_path: Path) -> None:
    for harness in ("claude-code", "codex", "cursor", "generic"):
        with pytest.raises(Unsupported, match=r"200 KiB argument, over the OS limit of 128 KiB.*use \{prompt\}"):
            ADAPTERS[harness].launch(prompt, tmp_path, "m", 'tool -p "<prompt>"')
    small = tmp_path / "small.md"
    small.write_text("short")
    assert ADAPTERS["generic"].launch(small, tmp_path, "m", 'tool -p "<prompt>"').argv[0] == "sh"


def test_the_limit_is_one_argument_not_the_whole_command() -> None:
    assert oversized_arg(["a" * (ARG_LIMIT - 1)] * 3) is None
    assert "128 KiB" in str(oversized_arg(["sh", "-c", "a" * ARG_LIMIT]))
    with pytest.raises(Unsupported):
        checked(Launch(["sh", "-c", "a" * ARG_LIMIT]))


def test_a_custom_reviewer_with_prompt_text_is_a_rerun_request_and_nothing_runs(prompt: Path, tmp_path: Path,
                                                                                monkeypatch, capsys) -> None:
    monkeypatch.setattr(role_prompt_cli, "run_and_file", lambda *a, **k: pytest.fail("the reviewer was launched"))
    monkeypatch.setattr(role_prompt_cli, "write_schema", lambda *a, **k: tmp_path / "s.json")
    out = role_prompt_cli.run_custom_reviewer(None, 'tool -p "<prompt>"', prompt, tmp_path, "m", tmp_path, None,
                                              "generic", [], transcript := [])
    assert out.state == "rerun" and out.exit == 1 and "use {prompt}" in out.reason
    assert "over the OS limit" in capsys.readouterr().err and transcript


# --- A3: the harness binary --------------------------------------------------------------------------------------

def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def no_path(tmp_path: Path, monkeypatch) -> Path:
    """A PATH with only git and a fresh HOME: no harness anywhere the resolver looks."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    (empty / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_resolution_order_harness_bin_then_path_then_install_dirs(no_path: Path, tmp_path: Path, monkeypatch) -> None:
    local = _exe(no_path / ".local" / "bin" / "agent")
    assert REAL_RESOLVE("cursor") == str(local)                    # off PATH: the documented install dir
    on_path = _exe(tmp_path / "empty-bin" / "agent")
    assert REAL_RESOLVE("cursor") == str(on_path)                  # PATH wins over the install dir
    pinned = _exe(tmp_path / "opt" / "agent-2026")
    assert REAL_RESOLVE("cursor", str(pinned)) == str(pinned)      # the roster's harness_bin wins over both
    _exe(no_path / ".claude" / "local" / "claude")
    assert REAL_RESOLVE("claude-code") == str(no_path / ".claude" / "local" / "claude")


def test_not_found_is_a_refusal_naming_the_dirs_searched_and_harness_bin(no_path: Path, tmp_path: Path) -> None:
    with pytest.raises(hb.HarnessNotFound) as e:
        REAL_RESOLVE("cursor")
    assert f"`agent` is not on PATH or in {no_path / '.local' / 'bin'}" in str(e.value) and "harness_bin" in str(e.value)
    with pytest.raises(hb.HarnessNotFound, match=r"harness_bin '/nowhere/agent' is not an executable file"):
        REAL_RESOLVE("cursor", "/nowhere/agent")
    assert isinstance(e.value, Unsupported)   # every launch path already refuses an Unsupported before exec


ROSTER = """version: 1
roster:
  - {{id: human, family: human, roles: [coordinator, reviewer]}}
  - {{id: comp, family: cursor, roles: [executor, reviewer], harness: cursor{extra}}}
"""


def test_worker_and_reviewer_launches_run_the_resolved_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(hb, "resolve", REAL_RESOLVE)
    agent = _exe(tmp_path / "tools" / "agent")
    repo = make_review_repo(tmp_path, orchestration=ROSTER.format(extra=f", harness_bin: {agent}"))
    chats: list[str] = []
    import specy_road.worker_adapter_cursor as cursor   # noqa: PLC0415
    monkeypatch.setattr(cursor, "create_chat", lambda wt, program="agent": chats.append(program) or "chat-1")
    launches: list[Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    rec, _ = ops.delegate(repo, "M1.1", "comp")
    assert launches[0].argv[0] == str(agent) and chats == [str(agent)]
    entry = {"id": "comp", "family": "cursor", "harness": "cursor", "harness_bin": str(agent)}
    seen: list[Launch] = []
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n")
    monkeypatch.setattr(review_delegate, "delegate_turn", lambda _a, _h, _log, _cwd, launch: seen.append(launch) or {
        "session_id": None, "exit": 1, "errors": ["stopped by the test"], "tail": [], "log_start": 0, "log_end": 0,
        "log_sha256": ""})
    review_delegate.delegate(repo, "M1.1", "comp", retries=0, sleep=lambda _s: None)
    assert seen[0].argv[0] == str(agent)   # review delegate
    seen.clear()
    monkeypatch.setattr(role_prompt_cli, "run_and_file", lambda launch, *a, **k: seen.append(launch))
    role_prompt_cli.run_reviewer_channel(None, tmp_path / "p.md", repo, entry, "comp", reviews_dir(repo, "M1.1"),
                                         None, [])
    assert seen[0].argv[0] == str(agent)   # prompt --channel cli
    assert ws.load_record(repo, rec.worker_id).harness == "cursor"


def test_a_missing_binary_refuses_every_launch_before_anything_runs(tmp_path: Path, no_path: Path,
                                                                    monkeypatch) -> None:
    monkeypatch.setattr(hb, "resolve", REAL_RESOLVE)
    repo = make_review_repo(tmp_path, orchestration=ROSTER.format(extra=""))
    monkeypatch.setattr(ops, "spawn", lambda *a, **k: pytest.fail("the worker was spawned"))
    with pytest.raises(Unsupported, match=r"`agent` is not on PATH or in .*harness_bin"):
        ops.delegate(repo, "M1.1", "comp")
    assert not ws.list_records(repo)
    entry = {"id": "comp", "family": "cursor", "harness": "cursor"}
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n")
    monkeypatch.setattr(review_delegate, "delegate_turn", lambda *a, **k: pytest.fail("the reviewer was launched"))
    with pytest.raises(hb.HarnessNotFound):
        review_delegate.delegate(repo, "M1.1", "comp", retries=0, sleep=lambda _s: None)
    monkeypatch.setattr(role_prompt_cli, "run_and_file", lambda *a, **k: pytest.fail("the reviewer was launched"))
    out = role_prompt_cli.run_reviewer_channel(None, tmp_path / "p.md", repo, entry, "comp",
                                               reviews_dir(repo, "M1.1"), None, [])
    assert out.state == "rerun" and "not on PATH" in out.reason


def test_worker_message_resumes_with_a_binary_only_harness_bin_reaches(tmp_path: Path, no_path: Path,
                                                                       monkeypatch) -> None:
    """R1: `agent` is on neither PATH nor ~/.local/bin; the roster's harness_bin is the only way to it, on the
    launch and on `worker message`'s resume alike."""
    monkeypatch.setattr(hb, "resolve", REAL_RESOLVE)
    agent = _exe(tmp_path / "tools" / "agent")
    repo = make_review_repo(tmp_path, orchestration=ROSTER.format(extra=f", harness_bin: {agent}"))
    launches: list[Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    rec, _ = ops.delegate(repo, "M1.1", "comp")
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "chat-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.message(repo, rec.worker_id, "go on")
    assert [la.argv[0] for la in launches] == [str(agent), str(agent)]
    assert launches[1].argv[1:4] == ["-p", "--resume", "chat-1"]
    # A custom command without {session} resumes with the default command: the same binary, not the bare name.
    (tmp_path / "p.md").write_text("continue")
    fallback = ADAPTERS["claude-code"].resume("s-1", tmp_path / "p.md", tmp_path, "m", "wrapper {prompt}",
                                              harness_bin=str(agent))
    assert fallback.argv[:2] == [str(agent), "-p"]
