"""Shared fixtures for reviewer runs (M11.7, M8.3): a claimed leaf whose roster runs a fake reviewer harness.

The fake answers as a launched reviewer does since M8.3: a final JSON object specy-road files as the record.
:func:`fake_reviewer_run` replaces the process launch of ``prompt --channel cli`` instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.review_repo_helpers import git, make_review_repo, review_output

from specy_road import review_record_write
from specy_road.bundled_scripts import role_prompt, role_prompt_cli, role_prompt_stream
from specy_road.review_files import reviews_dir

# Each call takes the next step of the spec; the call's argv is appended to `calls`.
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
    w = step["write"]
    os.makedirs(os.path.dirname(w["path"]), exist_ok=True)       # a new directory too
    kept = os.stat(w["path"]) if w.get("keep_mtime") else None   # an overwrite that puts the times back
    open(w["path"], "w").write(w["text"])
    if kept:
        os.utime(w["path"], ns=(kept.st_atime_ns, kept.st_mtime_ns))
if step.get("transient"):   # a file created, written and deleted again: only its directory keeps a trace
    with open(step["transient"], "w") as f:
        f.write("scratch")
    os.unlink(step["transient"])
if step.get("relink"):  # the file swapped for a hard link to an identical copy outside: same mode, size, mtime, bytes
    import shutil
    r = step["relink"]
    shutil.copy2(r["path"], r["alias"])
    os.unlink(r["path"])
    os.link(r["alias"], r["path"])
if step.get("chmod"):   # a permission change alone: content, size and mtime stay as they were
    os.chmod(step["chmod"], os.stat(step["chmod"]).st_mode ^ 0o100)
if step.get("git"):   # a git command in the checkout the harness was started in (an index-only write)
    import subprocess
    subprocess.run(["git", *step["git"]], check=True, capture_output=True)
if step.get("say"):   # an assistant message before the result
    print(json.dumps({"type": "assistant", "session_id": sid,
                      "message": {"content": [{"type": "text", "text": step["say"]}]}}), flush=True)
answer = json.dumps(step["answer"]) if "answer" in step else step.get("raw", "filed")
if step.get("plain"):   # a harness that prints only its final message
    print(answer, flush=True)
elif step.get("error"):
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "result": step["error"], "session_id": sid}), flush=True)
else:
    print(json.dumps({"type": "result", "subtype": "success", "result": answer, "session_id": sid}), flush=True)
sys.exit(step.get("exit", 0))
'''

CAPACITY = 'API Error: 529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'


def delegate_roster(cli: str) -> str:
    return ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
            f"  - {{id: opus, family: anthropic, roles: [reviewer], harness: claude-code, channels: {{cli: '{cli}'}}}}\n"
            "  - {id: plain, family: openai, roles: [reviewer]}\n")


def delegate_repo(tmp_path: Path, roster: str | None = None) -> tuple[Path, Path]:
    """``(repo, spec)``: ``roster`` (default :func:`delegate_roster` on a claude-code entry) may name the fake's
    command as ``{fake}``; the fake runs the steps :func:`set_steps` writes to ``spec``."""
    script, spec = tmp_path / "fake.py", tmp_path / "spec.json"
    script.write_text(FAKE)
    fake = f"{sys.executable} {script} {spec}"
    roster = roster or delegate_roster(fake + " {prompt} {session_flag}")
    repo = make_review_repo(tmp_path, orchestration=roster.replace("{fake}", fake))
    (reviews_dir(repo, "M1.1")).mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    return repo, spec


def set_steps(repo: Path, spec: Path, *steps: dict) -> None:
    spec.write_text(json.dumps({"calls": str(spec.with_name("calls.json")), "steps": list(steps)}))


def fake_calls(spec: Path) -> list[list[str]]:
    return json.loads(spec.with_name("calls.json").read_text())


def verdict_step(repo: Path, verdict: str = "approve", model: str = "opus") -> dict:
    """A step whose final JSON specy-road files as a valid REVIEW-opus.md for the commit under review."""
    return {"answer": review_output(git(repo, "rev-parse", "HEAD"), model=model, verdict=verdict,
                                    a1="pass" if verdict == "approve" else "fail")}


def fake_reviewer_run(monkeypatch, answer: list[str] | None = None) -> list[dict]:
    """Record each ``prompt --channel cli`` launch instead of running it; a reviewer turn "prints" ``answer``'s lines.
    ``role_prompt``'s and ``role_prompt_cli``'s own ``subprocess.run`` and ``Popen`` (the streamed, transcribed
    path) are recorded too."""
    import subprocess as real_sp
    from types import SimpleNamespace

    calls: list[dict] = []

    def run(cmd, **kw):
        calls.append({"cmd": cmd, **kw})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def popen(cmd, **kw):
        rec = {"cmd": cmd, **kw, "input": ""}

        class Stdin:
            def write(self, s):
                rec["input"] += s
                return len(s)

            def close(self):
                pass

        stdin = Stdin() if kw.get("stdin") not in (None, real_sp.DEVNULL) else None
        calls.append(rec)
        return SimpleNamespace(stdin=stdin, stdout=iter(()), wait=lambda: 0)

    fake = SimpleNamespace(run=run, Popen=popen, PIPE=real_sp.PIPE, STDOUT=real_sp.STDOUT, DEVNULL=real_sp.DEVNULL)
    for module in (role_prompt, role_prompt_cli, role_prompt_stream):   # the preflight, the commands, the stream
        monkeypatch.setattr(module, "subprocess", fake)

    def logged(launch, adapter, cwd, log, transcript=None) -> int:
        calls.append({"cmd": launch.argv, "input": launch.stdin, "cwd": cwd})
        with log.open() as raw:   # through the RunLog, as the real turn writes
            log.write(raw, "[review prompt] now claude\n" + "\n".join(answer or []) + "\n")
        if transcript is not None:
            transcript.extend(answer or [])
        return 0
    monkeypatch.setattr(review_record_write, "run_logged", logged)
    return calls


def wrote_paths(reason: str) -> list[str]:
    """The paths a ``review_failure`` reason names (``review failure: the reviewer run wrote a, b; …``)."""
    head = "review failure: the reviewer run wrote "
    return reason[reason.index(head) + len(head):].split(";", 1)[0].split(", ")


def wrote_only(reason: str, path: str) -> bool:
    """``path`` is named, and every other named path is one of its directories (whose entries the write changed)."""
    named = wrote_paths(reason)
    return path in named and all(p == path or Path(p) in Path(path).parents for p in named)


def strict_problems(node: object, at: str = "") -> list[str]:
    """Where ``node`` breaks OpenAI strict structured output (Codex ``--output-schema``): an object must require
    every property and allow no others; ``propertyNames`` and ``patternProperties`` are refused."""
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in strict_problems(v, f"{at}/{i}")]
    if not isinstance(node, dict):
        return []
    out = [f"{at}: {k}" for k in ("propertyNames", "patternProperties") if k in node]
    if node.get("type") == "object" and (set(node.get("required", [])) != set(node.get("properties", {}))
                                         or node.get("additionalProperties") is not False):
        out.append(f"{at}: not every property required, or other keys allowed")
    return out + [p for k, v in node.items() for p in strict_problems(v, f"{at}/{k}")]


FAKE_CODEX = '''#!{python}
import json, os, sys
spec = json.loads(open(os.environ["FAKE_CODEX_SPEC"]).read())
open(spec["calls"], "w").write(json.dumps(sys.argv[1:]))
sys.stdin.read()
argv = sys.argv[1:]
print(json.dumps({{"type": "thread.started", "thread_id": "t-1"}}), flush=True)
print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": "see -o"}}}}), flush=True)
if "-o" in argv:
    open(argv[argv.index("-o") + 1], "w").write(json.dumps(spec["answer"]))
print(json.dumps({{"type": "turn.completed", "usage": {{}}}}), flush=True)
'''


FAKE_AGY = '''#!{python}
import json, os, sys
spec = json.loads(open(os.environ["FAKE_AGY_SPEC"]).read())
open(spec["calls"], "w").write(json.dumps(sys.argv[1:]))
envelope = {{"conversation_id": "c-1", "status": "SUCCESS", "response": json.dumps(spec["answer"]),
            "structured_output": spec["answer"], "num_turns": 1}}
print(json.dumps(envelope, indent=2), flush=True)   # one envelope, pretty-printed over many lines
'''
