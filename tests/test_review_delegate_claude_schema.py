"""``review delegate`` on a Claude Code reviewer (M21.24): the inline ``--json-schema`` carries no ``$schema``, and a
failed turn with no parsed error names the harness's own last log line."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.review_delegate_helpers import run_review_delegate
from tests.review_repo_helpers import git, make_review_repo, review_output

from specy_road.review_delegate import load_run
from specy_road.review_files import reviews_dir
from specy_road.review_write_check import OUTPUT_SCHEMA_NAME
from specy_road.worker_adapters import ClaudeCode

ROSTER = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
          "  - {id: opus, family: anthropic, roles: [reviewer], harness: claude-code}\n")

# A `claude` on PATH, so the launch is ClaudeCode.reviewer_launch's own argv: records it, prints `stderr` to stderr,
# answers `answer` (if any) as a result event and exits `exit`.
FAKE_CLAUDE = """#!{python}
import json, sys
spec = json.loads(open({spec!r}).read())
open({calls!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")
sys.stdin.read()
sys.stderr.write(spec.get("stderr", ""))
sys.stderr.flush()
if "answer" in spec:
    print(json.dumps({{"type": "result", "subtype": "success", "result": spec["answer"], "session_id": "s-1"}}))
sys.exit(spec.get("exit", 0))
"""

RC4 = ('Error: --json-schema is not a valid JSON Schema: no schema with key or ref '
       '"https://json-schema.org/draft/2020-12/schema"')
LONG = "E" * 250


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec: dict) -> tuple[Path, Path]:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    reviews_dir(repo, "M1.1").mkdir(parents=True, exist_ok=True)
    (reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n\n**Commit under review:** HEAD\n")
    bin_dir, calls, spec_path = tmp_path / "bin", tmp_path / "calls.jsonl", tmp_path / "spec.json"
    bin_dir.mkdir()
    spec_path.write_text(json.dumps(spec))
    (bin_dir / "claude").write_text(FAKE_CLAUDE.format(python=sys.executable, spec=str(spec_path), calls=str(calls)))
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return repo, calls


def test_the_inline_schema_is_the_file_less_its_dollar_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, calls = _repo(tmp_path, monkeypatch, {})
    (tmp_path / "spec.json").write_text(json.dumps(
        {"answer": json.dumps(review_output(git(repo, "rev-parse", "HEAD"), model="opus"))}))
    assert run_review_delegate(repo) == 0
    argv = json.loads(calls.read_text().splitlines()[0])
    inline = json.loads(argv[argv.index("--json-schema") + 1])
    on_disk = json.loads((reviews_dir(repo, "M1.1") / OUTPUT_SCHEMA_NAME).read_text())
    assert isinstance(inline, dict) and "$schema" not in inline
    assert "$schema" in on_disk   # the file keeps it, for Codex and agy
    assert inline == {k: v for k, v in on_disk.items() if k != "$schema"}


@pytest.mark.parametrize(("stderr", "expected"), [
    (RC4 + "\n", RC4),
    (RC4 + "\n" + "\n" * 25, RC4),   # more blank lines than the turn's 20-line tail
    (LONG + "\n", LONG[:200]),
    ("", "no error text"),
], ids=["rc4-error", "error-then-blank-lines", "long-line", "silent"])
def test_a_failed_turn_names_the_harness_error_in_reason_and_attempt(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        stderr: str, expected: str) -> None:
    repo, _calls = _repo(tmp_path, monkeypatch, {"stderr": stderr, "exit": 1})
    run_review_delegate(repo)
    out = capsys.readouterr()
    assert f"harness exited 1: {expected};" in out.out + out.err
    run = load_run(repo, "M1.1", "opus")
    assert f"harness exited 1: {expected};" in run["reason"]
    assert run["attempts"][-1]["error"] == expected


def test_the_executor_launch_passes_no_json_schema(tmp_path: Path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("x")
    assert "--json-schema" not in ClaudeCode().launch(prompt, tmp_path, "m", None).argv
    assert "--json-schema" not in ClaudeCode().resume("s-1", prompt, tmp_path, "m", None).argv
