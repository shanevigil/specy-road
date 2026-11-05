"""Fake harness and CLI helpers for ``review delegate`` tests (M11.7 and dependents)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo, review_text

from specy_road.bundled_scripts import review_cli
from specy_road.review_files import reviews_dir

# Each call takes the next step of the spec; the call's argv is appended to ``calls``.
FAKE = '''
import json, os, sys
spec = json.loads(open(sys.argv[1]).read())
calls = json.loads(open(spec["calls"]).read()) if os.path.exists(spec["calls"]) else []
calls.append(sys.argv[2:])
open(spec["calls"], "w").write(json.dumps(calls))
step = spec["steps"][min(len(calls), len(spec["steps"])) - 1]
sid = sys.argv[-1]
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid, "model": "fake"}), flush=True)
if step.get("write"):
    open(step["write"]["path"], "w").write(step["write"]["text"])
if step.get("say"):
    print(json.dumps({"type": "assistant", "session_id": sid,
                      "message": {"content": [{"type": "text", "text": step["say"]}]}}), flush=True)
if step.get("error"):
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "result": step["error"], "session_id": sid}), flush=True)
else:
    print(json.dumps({"type": "result", "subtype": "success", "result": "filed", "session_id": sid}), flush=True)
sys.exit(step.get("exit", 0))
'''

CAPACITY = 'API Error: 529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'


def roster(cli: str) -> str:
    return ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - {{id: opus, family: anthropic, roles: [reviewer], harness: claude-code, channels: {{cli: '{cli}'}}}}\n"
            "  - {id: plain, family: openai, roles: [reviewer]}\n")


def make_delegate_repo(tmp_path: Path) -> tuple[Path, Path]:
    script, spec = tmp_path / "fake.py", tmp_path / "spec.json"
    script.write_text(FAKE)
    repo = make_review_repo(tmp_path, orchestration=roster(f"{sys.executable} {script} {spec} {{prompt}} {{session_flag}}"))
    (reviews_dir(repo, "M1.1")).mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    return repo, spec


def set_delegate_steps(repo: Path, spec: Path, *steps: dict) -> None:
    spec.write_text(json.dumps({"calls": str(spec.with_name("calls.json")), "steps": list(steps)}))


def read_delegate_calls(spec: Path) -> list[list[str]]:
    return json.loads(spec.with_name("calls.json").read_text())


def files_record_step(repo: Path, verdict: str = "approve") -> dict:
    """A step that files a valid REVIEW-opus.md for the commit under review."""
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict=verdict,
                       a1="pass" if verdict == "approve" else "fail")
    return {"write": {"path": str(reviews_dir(repo, "M1.1") / "REVIEW-opus.md"), "text": text}}


def run_review_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(list(args))
    return e.value.code


def run_review_delegate(repo: Path, *extra: str) -> int:
    return run_review_cli("review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", *extra,
                          "--repo-root", str(repo))


def handoff_status_node(repo: Path, capsys) -> dict:
    capsys.readouterr()
    run_review_cli("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return json.loads(capsys.readouterr().out)["nodes"][0]
