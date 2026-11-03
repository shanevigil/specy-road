"""M8.3: reviewer runs are read-only and specy-road files the review record from their final JSON."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, fake_reviewer_run, set_steps, verdict_step
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_output
from tests.test_models_and_prompt import run_main

from specy_road import review_files as rf
from specy_road.bundled_scripts import role_prompt
from specy_road.model_profiles import load_profile
from specy_road.review_delegate import DelegateError, delegate
from specy_road.review_record_write import (json_object, output_schema, review_run_lock, reviewer_env, snapshot,
                                            written)
from specy_road.worker_adapters import Codex, Cursor, Unsupported, reviewer_cli

M87_NOTE = Path(__file__).resolve().parents[1] / "docs" / "design-notes" / "M8.7-runtime-verification-harness-facts.md"


def _record(repo: Path) -> Path:
    return rf.review_path(repo, "M1.1", "opus")


# --- A2: a run that writes anything but its notes ------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    "src/a.py",                         # a tracked file
    "work/unrelated-output.txt",        # an untracked file in the project's work/
    "work/reviews/M1.1/scratch.md",     # an ignored file, in the hand-off directory itself
])
def test_a_run_that_writes_anything_but_its_notes_is_a_review_failure_and_files_nothing(tmp_path: Path, rel: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(repo / rel), "text": "x = 2\n"}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["state"] == "incomplete" and run["outcome"] == "review_failure"
    assert run["reason"].startswith(f"review failure: the reviewer run wrote {rel};")
    assert not _record(repo).exists()                                 # the verdict in its output is not filed


def test_the_reviewers_own_notes_are_the_one_write_allowed(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    notes = rf.reviews_dir(repo, "M1.1") / "notes-opus.md"
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(notes), "text": "draft\n"}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]


def test_a_run_that_files_its_own_record_is_a_review_failure_and_the_record_is_put_back(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo, "block"))
    assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["state"] == "complete"
    filed = _record(repo).read_bytes()
    commit_file(repo, "src/a.py", "print('fixed')\n", "fix")
    approve = review_output(git(repo, "rev-parse", "HEAD"), model="opus")
    text = "---\n" + json.dumps({k: v for k, v in approve.items() if k != "notes"}) + "\n---\nmine\n"
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(_record(repo)), "text": text}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "review_failure" and "REVIEW-opus.md" in run["reason"]
    assert _record(repo).read_bytes() == filed                        # the earlier block, not the self-filed approve


def test_a_commit_and_an_ignored_cache_count_as_writes_and_other_checkouts_do_not(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    reviews = rf.reviews_dir(repo, "M1.1")
    nested = repo / "work" / ".worktrees" / "other"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: elsewhere\n")                   # a linked worktree: another checkout
    before = snapshot(repo, reviews, "opus")
    (nested / "edit.py").write_text("theirs\n")
    assert written(before, snapshot(repo, reviews, "opus")) == []
    (repo / "work" / "reviews" / "M1.1").mkdir(parents=True, exist_ok=True)
    (repo / "work" / "reviews" / "M1.1" / "RUN-opus.log").write_text("the run's own log\n")
    assert written(before, snapshot(repo, reviews, "opus")) == []
    git(repo, "commit", "-q", "--allow-empty", "-m", "reviewer commit")
    (repo / "work" / "reviews" / "M1.1" / "RUN-sol.log").write_text("not this run's\n")
    assert written(before, snapshot(repo, reviews, "opus")) == ["git refs", "work/reviews/M1.1/RUN-sol.log"]


def test_one_leafs_reviewer_runs_take_turns(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, verdict_step(repo))
    with review_run_lock(rf.reviews_dir(repo, "M1.1")):
        with pytest.raises(DelegateError, match="another reviewer run of M1.1 is in progress"):
            delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["state"] == "complete"


def test_the_reviewer_process_writes_no_bytecode_or_pytest_cache() -> None:
    env = reviewer_env({"PYTEST_ADDOPTS": "-q"})
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTEST_ADDOPTS"] == "-q -p no:cacheprovider"
    assert reviewer_env(env) == env


# --- A3: missing or malformed output is a rerun request ---------------------------------------------------------

@pytest.mark.parametrize("raw,why", [
    ('{"verdict": "approve", "commit": ', "ends with no JSON object"),
    ('{"verdict": "approve"}', "does not match the review output schema"),
])
def test_malformed_output_is_a_rerun_request_never_a_verdict(tmp_path: Path, raw: str, why: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"raw": raw})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["state"] == "incomplete" and run["outcome"] == "rerun"
    assert run["reason"].startswith("rerun requested: ") and why in run["reason"]
    assert not _record(repo).exists()


def test_output_review_record_refuses_is_a_rerun_request(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    stale = review_output(git(repo, "rev-parse", "HEAD~1"), model="opus")   # not the commit under review
    set_steps(repo, spec, {"answer": stale})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "rerun" and "review record refused the output" in run["reason"]
    assert "Re-review the current commit" in run["reason"] and not _record(repo).exists()


def test_the_last_json_object_of_a_message_is_the_answer() -> None:
    assert json_object({"a": 1}) == {"a": 1}
    assert json_object('Done.\n```json\n{"a": {"b": 1}}\n```\n') == {"a": {"b": 1}}
    assert json_object('{"draft": 1} then {"final": 2}') == {"final": 2}
    assert json_object("no object here") is None and json_object(None) is None


# --- A1: the prompt asks for the object; the schema is the record's -----------------------------------------------

def test_the_output_schema_is_the_record_schema_less_what_specy_road_fills() -> None:
    record = json.loads((Path(rf.__file__).parent / "schemas" / "review-record.schema.json").read_text())
    schema = output_schema()
    assert set(schema["properties"]) == set(record["properties"]) - {
        "family", "independence", "notes_sha256", "signature", "launch_mode"} | {"notes"}
    assert schema["required"] == [*record["required"], "notes"] and schema["additionalProperties"] is False


def test_a_pasted_reviewer_prompt_asks_for_the_object_and_still_files_by_hand(tmp_path: Path) -> None:
    repo, _spec = delegate_repo(tmp_path)
    pasted = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus", read_back=False)[0]
    read_back = role_prompt.build_prompt(repo, "M1.1", role="reviewer", model="opus")[0]
    assert pasted.rstrip().endswith("```") and "## Your final message: one JSON object" in pasted
    assert "you still file the record yourself" in pasted and "specy-road files your record" not in pasted
    assert "**specy-road files your record.**" in read_back and "## Your final message" in read_back


# --- A5: Cursor and Codex reviewer commands ------------------------------------------------------------------------

def test_cursor_reviewer_runs_ask_mode_without_force(tmp_path: Path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("review it")
    fresh = Cursor().reviewer_launch(prompt, "gpt-6.1-sol", tmp_path, schema=tmp_path / "s.json")
    assert fresh.argv == ["agent", "-p", "--output-format", "stream-json", "--mode", "ask", "--trust",
                          "--model", "gpt-6.1-sol", "review it"] and fresh.session_id is None
    resumed = Cursor().reviewer_launch(prompt, None, tmp_path, session=("s1", True))
    assert resumed.argv == ["agent", "-p", "--resume", "s1", "--output-format", "stream-json", "--mode", "ask",
                            "--trust", "review it"] and resumed.session_id == "s1"
    assert "Review-only runs omit `--force`" in M87_NOTE.read_text(encoding="utf-8")   # the note the code matches
    assert "--force" in Cursor().launch(prompt, tmp_path, None, None).argv              # executors keep it


def test_codex_reviewer_runs_read_only_with_the_output_schema(tmp_path: Path) -> None:
    prompt, schema, out = tmp_path / "p.md", tmp_path / "s.json", tmp_path / "OUTPUT-sol.json"
    prompt.write_text("review it")
    fresh = Codex().reviewer_launch(prompt, "gpt-6.1-sol", tmp_path, "high", schema=schema, output=out)
    assert fresh.argv == ["codex", "exec", "--json", "-m", "gpt-6.1-sol", "-c", "model_reasoning_effort=high",
                          "-c", "sandbox_mode=read-only", "-c", "approval_policy=never",
                          "--output-schema", str(schema), "-o", str(out), "-"]
    assert fresh.stdin == "review it"
    resumed = Codex().reviewer_launch(prompt, "gpt-6.1-sol", tmp_path, session=("t1", True), schema=schema, output=out)
    assert resumed.argv == ["codex", "exec", "resume", "--json", "-c", "sandbox_mode=read-only",
                            "-c", "approval_policy=never", "t1", "-"]
    assert "sandbox_mode=read-only" in M87_NOTE.read_text(encoding="utf-8")


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


def test_a_codex_review_delegate_files_the_verdict_from_its_output_file(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: sol, family: openai, roles: [reviewer], harness: codex}\n"))
    reviews = rf.reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True)
    (reviews / "PACKET.md").write_text("# Review packet\n")
    bin_dir, spec = tmp_path / "bin", tmp_path / "codex-spec.json"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(FAKE_CODEX.format(python=sys.executable))
    (bin_dir / "codex").chmod(0o755)
    spec.write_text(json.dumps({"calls": str(tmp_path / "codex-calls.json"),
                                "answer": review_output(git(repo, "rev-parse", "HEAD"), model="sol")}))
    monkeypatch.setenv("FAKE_CODEX_SPEC", str(spec))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    run = delegate(repo, "M1.1", "sol", sleep=lambda s: None)
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]
    argv = json.loads((tmp_path / "codex-calls.json").read_text())
    assert "sandbox_mode=read-only" in argv and "--output-schema" in argv and "--force" not in argv
    assert argv[argv.index("-o") + 1] == str(reviews / "OUTPUT-sol.json")
    rec = rf.load_review(rf.review_path(repo, "M1.1", "sol"), ["A1", "A2"])
    assert rec.ok and rec.data["verdict"] == "approve" and rec.data["launch_mode"] == "full"


def test_prompt_channel_cli_runs_a_cursor_reviewer_read_only_and_files_its_answer(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=(
        "version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
        "  - {id: comp, family: cursor, roles: [reviewer], harness: cursor}\n"))
    rf.reviews_dir(repo, "M1.1").mkdir(parents=True)
    (rf.reviews_dir(repo, "M1.1") / "PACKET.md").write_text("# Review packet\n")
    answer = review_output(git(repo, "rev-parse", "HEAD"), model="comp")
    calls = fake_reviewer_run(monkeypatch, [json.dumps({"type": "result", "subtype": "success",
                                                        "result": "Verdict:\n" + json.dumps(answer)})])
    assert run_main(role_prompt, "M1.1", "--model", "comp", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 0
    (call,) = calls
    assert call["cmd"][:7] == ["agent", "-p", "--output-format", "stream-json", "--mode", "ask", "--trust"]
    assert "--force" not in call["cmd"] and "**specy-road files your record.**" in call["cmd"][-1]
    assert rf.load_review(rf.review_path(repo, "M1.1", "comp"), ["A1", "A2"]).ok


# --- custom reviewer commands: captured, write-checked and filed too ------------------------------------------------

GENERIC = ("version: 1\nroster:\n  - {id: human, family: human, roles: [coordinator, reviewer]}\n"
           "  - {id: gem, family: google, roles: [reviewer], harness: generic, channels: {cli: '{fake} {prompt}'}}\n")


@pytest.mark.parametrize("writes", [False, True])
def test_prompt_channel_cli_captures_a_custom_reviewer_command_and_checks_its_writes(tmp_path: Path, capsys,
                                                                                     writes: bool) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    step = {**verdict_step(repo, model="gem"), "plain": True}
    set_steps(repo, spec, {**step, "write": {"path": str(repo / "work" / "out.txt"), "text": "x"}} if writes else step)
    rc = run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli",
                  "--repo-root", str(repo))
    err = capsys.readouterr().err
    assert (rc, rf.review_path(repo, "M1.1", "gem").exists()) == ((1, False) if writes else (0, True))
    assert ("review_failure: review failure: the reviewer run wrote work/out.txt" in err) is writes
    prompt = (repo / "work" / "prompt-M1.1-reviewer-gem.md").read_text()
    assert "**specy-road files your record.**" in prompt


def test_a_custom_reviewer_command_under_review_delegate_is_checked_and_filed(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True})
    assert delegate(repo, "M1.1", "gem", sleep=lambda s: None)["outcome"] == "recorded"


# --- A1: Antigravity (agy, a generic harness) gets --json-schema from the adapter -------------------------------------

def test_agy_reviewer_commands_get_the_schema_and_read_only_flags(tmp_path: Path) -> None:
    schema = tmp_path / "review-output.schema.json"
    assert reviewer_cli('agy -p "<prompt>" --model g', schema) == (
        f'agy --json-schema {schema} --output-format json --sandbox --print-timeout 30m -p "<prompt>" --model g')
    kept = reviewer_cli("agy --json-schema=s.json --output-format stream-json --sandbox --print-timeout 1h -p x", schema)
    assert kept == "agy --json-schema=s.json --output-format stream-json --sandbox --print-timeout 1h -p x"
    assert reviewer_cli("/opt/bin/agy -p x", schema).startswith(f"/opt/bin/agy --json-schema {schema} ")
    assert reviewer_cli('wrapper agy -p "<prompt>"', schema) == 'wrapper agy -p "<prompt>"'
    with pytest.raises(Unsupported, match="--dangerously-skip-permissions"):
        reviewer_cli("agy -p x --dangerously-skip-permissions", schema)


def test_the_shipped_agy_profile_gets_only_the_flags_it_lacks_as_a_reviewer(tmp_path: Path) -> None:
    profile = load_profile(Path(rf.__file__).parent / "templates" / "project" / "model-profiles" / "google-antigravity"
                           / "agy-gemini-4-argon-high.md")
    schema = tmp_path / "review-output.schema.json"
    cli = reviewer_cli(profile.cli(), schema)
    assert cli == profile.cli().replace("agy ", f"agy --json-schema {schema} --sandbox ", 1)   # keeps json and 60m


FAKE_AGY = '''#!{python}
import json, os, sys
spec = json.loads(open(os.environ["FAKE_AGY_SPEC"]).read())
open(spec["calls"], "w").write(json.dumps(sys.argv[1:]))
envelope = {{"conversation_id": "c-1", "status": "SUCCESS", "response": json.dumps(spec["answer"]),
            "structured_output": spec["answer"], "num_turns": 1}}
print(json.dumps(envelope, indent=2), flush=True)   # one envelope, pretty-printed over many lines
'''


def test_an_antigravity_review_delegate_passes_json_schema_and_files_structured_output(tmp_path: Path,
                                                                                       monkeypatch) -> None:
    repo = make_review_repo(tmp_path, orchestration=GENERIC.replace("{fake} {prompt}", 'agy -p "<prompt>"'))
    reviews = rf.reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True)
    (reviews / "PACKET.md").write_text("# Review packet\n")
    bin_dir, spec = tmp_path / "bin", tmp_path / "agy-spec.json"
    bin_dir.mkdir()
    (bin_dir / "agy").write_text(FAKE_AGY.format(python=sys.executable))
    (bin_dir / "agy").chmod(0o755)
    spec.write_text(json.dumps({"calls": str(tmp_path / "agy-calls.json"),
                                "answer": review_output(git(repo, "rev-parse", "HEAD"), model="gem")}))
    monkeypatch.setenv("FAKE_AGY_SPEC", str(spec))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    run = delegate(repo, "M1.1", "gem", sleep=lambda s: None)
    assert run["state"] == "complete" and run["outcome"] == "recorded", run["reason"]
    argv = json.loads((tmp_path / "agy-calls.json").read_text())
    assert argv[:7] == ["--json-schema", str(reviews / "review-output.schema.json"), "--output-format", "json",
                        "--sandbox", "--print-timeout", "30m"]
    assert json.loads((reviews / "review-output.schema.json").read_text())["title"] == "specy-road reviewer output"
