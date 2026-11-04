"""M11.35: a roster entry's harness_model reaches the harness on launch and resume, and an early exit says why."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road import worker_adapters as wa
from specy_road import worker_ops as ops
from specy_road import worker_runner as wr
from specy_road import worker_state as ws
from specy_road.bundled_scripts.validate_roadmap import validate_orchestration_contract
from specy_road.orchestration_config import harness_model, harness_model_warnings, parse_orchestration_text
from specy_road.review_delegate import delegate as review_delegate
from specy_road.review_files import reviews_dir

DOTTED = {"id": "claude-opus-5.5", "family": "anthropic", "harness": "claude-code"}
MAPPED = {**DOTTED, "harness_model": "claude-opus-5-5"}


def test_harness_model_wins_then_the_profile_then_the_roster_id() -> None:
    assert harness_model(MAPPED) == "claude-opus-5-5"
    assert harness_model(MAPPED, "claude-opus-5") == "claude-opus-5-5"
    assert harness_model(DOTTED) == "claude-opus-5.5"   # fallback: the roster id, as before
    assert harness_model(DOTTED, "claude-opus-5-5") == "claude-opus-5-5"
    assert harness_model(DOTTED, "unknown") is None and harness_model(DOTTED, "") is None   # the harness's default


def test_schema_takes_harness_model_and_validate_warns_on_a_dotted_claude_id(tmp_path: Path, capsys) -> None:
    roster = ("version: 1\nroster:\n"
              "  - {id: claude-opus-5.5, family: anthropic, harness: claude-code}\n"
              "  - {id: claude-fable-5.1, family: anthropic, harness: claude-code, harness_model: claude-fable-5-1}\n"
              "  - {id: gpt-6.1-sol, family: openai, harness: codex}\n")
    data, err = parse_orchestration_text(roster)
    assert err is None and data["roster"][1]["harness_model"] == "claude-fable-5-1"
    warnings = harness_model_warnings(data)
    assert len(warnings) == 1 and "'claude-opus-5.5'" in warnings[0] and "harness_model" in warnings[0]
    repo = make_review_repo(tmp_path)
    (repo / "roadmap" / "orchestration.yaml").write_text(roster)
    validate_orchestration_contract(repo)
    err_out = capsys.readouterr().err
    assert "warning: roster entry 'claude-opus-5.5' runs on claude-code" in err_out and "claude-fable-5.1" not in err_out


FAKE_CLAUDE = """#!{python}
import json, sys
open({calls!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "s-1", "model": "fake"}}), flush=True)
print(json.dumps({{"type": "result", "subtype": "success", "result": "done", "session_id": "s-1"}}), flush=True)
"""


def _roster(entry: dict) -> str:
    fields = ", ".join(f"{k}: {v}" for k, v in entry.items())
    return ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - {{{fields}, roles: [executor, reviewer]}}\n")


@pytest.mark.parametrize(("entry", "want"), [(MAPPED, "claude-opus-5-5"), (DOTTED, "claude-opus-5.5")])
def test_delegate_and_message_tell_claude_the_harness_model(tmp_path: Path, monkeypatch, entry, want) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster(entry))
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    launches: list[wa.Launch] = []
    monkeypatch.setattr(ops, "spawn", lambda root, rec, launch, **kw: launches.append(launch))
    rec, _ = ops.delegate(repo, "M1.1", "claude-opus-5.5", offline=True)
    ws.mutate(repo, rec, lambda r: setattr(r, "provider_session_id", "sess-1"))
    ws.set_state(repo, rec, "idle", pid=None)
    ops.message(repo, rec.worker_id, "go on", offline=True)
    for launch in launches:   # launch, then the resume
        assert launch.argv[launch.argv.index("--model") + 1] == want
    assert "--resume" in launches[1].argv


def test_review_delegate_tells_claude_the_harness_model(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=_roster(MAPPED))
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    bin_dir, calls = tmp_path / "bin", tmp_path / "calls.jsonl"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text(FAKE_CLAUDE.format(python=sys.executable, calls=str(calls)))
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    review_delegate(repo, "M1.1", "claude-opus-5.5", retries=0, backoff=0)
    argv = json.loads(calls.read_text().splitlines()[0])
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"


@pytest.mark.parametrize(("harness", "flag"), [("claude-code", "--model"), ("codex", "-m"), ("cursor", "--model")])
def test_resume_passes_the_same_model_flag_as_the_launch(tmp_path: Path, harness: str, flag: str) -> None:
    p = tmp_path / "p.md"
    p.write_text("do the thing")
    a = wa.adapter_for(harness)
    for model in (harness_model(MAPPED), harness_model(DOTTED)):   # with and without harness_model
        launch, resume = a.launch(p, tmp_path, model, None), a.resume("sid", p, tmp_path, model, None)
        for argv in (launch.argv, resume.argv):
            assert argv[argv.index(flag) + 1] == model
    assert flag not in a.resume("sid", p, tmp_path, None, None).argv   # no model: the harness's own default


def _early_exit(repo: Path, node: str, script: str) -> ws.WorkerEvent:
    rec = ws.create_record(repo, node, "claude-code", "claude-opus-5.5", repo)
    assert wr.run(repo, rec.worker_id, wa.Launch(["sh", "-c", script])) == 1
    assert ws.load_record(repo, rec.worker_id).state == "failed"
    return ws.events_since(repo, rec.worker_id)[-1]


def test_an_exit_before_the_first_stream_event_quotes_the_harness_error(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    last = _early_exit(repo, "M1.1", "echo 'starting' >&2; echo 'API Error: 404 model: claude-opus-5.5 not found' >&2; "
                                     "echo 'bye' >&2; exit 1")
    assert last.type == "error" and last.detail["exit"] == 1
    assert "before any stream event: API Error: 404 model: claude-opus-5.5 not found" in last.summary
    assert last.summary.endswith(".log") and last.detail["harness_error"].startswith("API Error: 404")


def test_an_exit_after_a_stream_event_keeps_the_plain_summary(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    init = '{"type":"system","subtype":"init","session_id":"s-1","model":"m"}'
    last = _early_exit(repo, "M1.1", f"echo '{init}'; echo 'Error: later failure' >&2; exit 1")
    assert last.summary.startswith("exit 1; see ") and "harness_error" not in last.detail


def test_only_this_turns_part_of_the_log_is_quoted(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "claude-opus-5.5", repo)
    log = wr.log_path(repo, rec.worker_id)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("Error: an earlier turn's failure\n")
    assert wr.run(repo, rec.worker_id, wa.Launch(["sh", "-c", "exit 1"])) == 1
    last = ws.events_since(repo, rec.worker_id)[-1]
    assert last.summary.startswith("exit 1; see ") and "earlier" not in last.summary
