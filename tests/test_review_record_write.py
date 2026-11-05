"""M8.3: reviewer runs are read-only and specy-road files the review record from their final JSON."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.review_delegate_helpers import (FAKE_AGY, FAKE_CODEX, delegate_repo, fake_reviewer_run, set_steps,
                                          strict_problems, verdict_step, wrote_paths)
from tests.review_repo_helpers import commit_file, git, make_review_repo, review_output
from tests.test_models_and_prompt import run_main

from specy_road import review_files as rf
from specy_road.bundled_scripts import review_cli, role_prompt
from specy_road.model_profiles import load_profile
from specy_road.review_delegate import DelegateError, delegate
from specy_road.review_record_write import output_schema, review_run_lock, reviewer_env, snapshot, written
from specy_road.worker_adapter_base import file_instruction
from specy_road.worker_adapters import Codex, Cursor, Unsupported, reviewer_cli

M87_NOTE = Path(__file__).resolve().parents[1] / "docs" / "design-notes" / "M8.7-runtime-verification-harness-facts.md"


def _record(repo: Path) -> Path:
    return rf.review_path(repo, "M1.1", "opus")


# --- A2: the tripwire (git status of the leaf worktree; the hand-off directory by content hash) ----------------------

@pytest.mark.parametrize("rel", [
    "src/a.py",                                         # a changed tracked file
    "new.txt",                                          # a new untracked file
    "work/unrelated-output.txt",                        # a new untracked file in the project's work/
    "work/reviews/M1.1/scratch.md",                     # a new file in the (git-ignored) hand-off directory
    "work/reviews/M1.1/review-output.schema.json",      # the schema specy-road wrote before the run, changed
    "work/reviews/M1.1/PACKET.md",                      # the packet, changed
])
def test_a_write_the_tripwire_sees_is_a_review_failure_and_files_nothing(tmp_path: Path, rel: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(repo / rel), "text": "x = 2\n"}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["state"] == "incomplete" and run["outcome"] == "review_failure"
    assert wrote_paths(run["reason"]) == [rel]
    assert not _record(repo).exists()                                 # the verdict in its output is not filed


@pytest.mark.parametrize("name", ["notes-opus.md", "RUN-opus.json", ".review-run.lock"])
def test_the_notes_and_specy_roads_own_run_files_are_not_the_reviewers_writes(tmp_path: Path, name: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    path = rf.reviews_dir(repo, "M1.1") / name
    set_steps(repo, spec, {**verdict_step(repo), "write": {"path": str(path), "text": "{}\n"}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "recorded", run["reason"]


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


def test_the_tripwire_compares_git_status_entries_and_hand_off_files_by_content(tmp_path: Path) -> None:
    """The exact rules: a status entry new, or with another code or content; a hand-off file added, removed or
    changed, but the notes and run files. A file already dirty before the run counts when it changes again."""
    repo = make_review_repo(tmp_path)
    reviews = rf.reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    (repo / "src" / "a.py").write_text("dirty before the run\n")
    (repo / "untracked.txt").write_text("before\n")
    (reviews / "PACKET.md").write_text("packet\n")
    before = snapshot(repo, reviews, "opus")
    assert written(before, snapshot(repo, reviews, "opus", before)) == []
    for name in ("RUN-opus.log", "RUN-opus.json", "notes-opus.md", ".review-run.lock"):
        (reviews / name).write_text("specy-road's\n")
    assert written(before, snapshot(repo, reviews, "opus", before)) == []
    (repo / "src" / "a.py").write_text("dirty, then changed by the reviewer\n")
    (repo / "untracked.txt").write_text("after\n")
    (reviews / "PACKET.md").unlink()
    (reviews / "RUN-sol.log").write_text("not this run's\n")
    assert written(before, snapshot(repo, reviews, "opus", before)) == [
        "src/a.py", "untracked.txt", "work/reviews/M1.1/PACKET.md", "work/reviews/M1.1/RUN-sol.log"]


def test_the_reviewer_process_writes_no_bytecode_or_pytest_cache() -> None:
    env = reviewer_env({"PYTEST_ADDOPTS": "-q"})
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["PYTEST_ADDOPTS"] == "-q -p no:cacheprovider"
    assert env["GIT_OPTIONAL_LOCKS"] == "0"                                  # no index.lock from a read-only git status
    assert reviewer_env(env) == env


# --- A3: missing or malformed output is a rerun request (end to end; the per-row table is test_review_answer) --------

NOT_ONE = "is not one complete JSON object"
CUT = "is not one JSON object (a cut-off or stray line)"


@pytest.mark.parametrize("raw,why", [
    ('{"verdict": "approve", "commit": ', NOT_ONE),
    ('{"verdict": "approve"}', "does not match the review output schema"),
    ("Verdict:\nVERDICT", NOT_ONE),                       # prose before the object
    ("```json\nVERDICT\n```", NOT_ONE),                  # a fenced object
    ("VERDICT\n{}", NOT_ONE),                             # two objects
    ("[\nVERDICT\n]", NOT_ONE),                          # inside an array
    ('{"wrapper": "draft", "review":\nVERDICT', NOT_ONE),  # nested in an unterminated outer object
])
def test_malformed_output_is_a_rerun_request_never_a_verdict(tmp_path: Path, raw: str, why: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {"raw": raw.replace("VERDICT", json.dumps(verdict_step(repo)["answer"]))})
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


def test_an_answer_with_null_optional_fields_files_the_same_record_as_one_without(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    plain = verdict_step(repo)["answer"]
    nulls = {**plain, "toolkit_version": None, "model_version": None, "delta_from": None, "verify_pre_existing": None}
    texts = []
    for answer in (plain, nulls):
        set_steps(repo, spec, {"answer": answer})
        assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["outcome"] == "recorded"
        texts.append(_record(repo).read_text(encoding="utf-8"))
    assert texts[0] == texts[1] and "null" not in texts[1]
    set_steps(repo, spec, {"answer": {**plain, "commit": None}})              # a required field stays required
    assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["outcome"] == "rerun"


def test_a_valid_result_then_a_truncated_result_line_is_a_rerun_through_the_cli(tmp_path: Path, capsys) -> None:
    """Sol F2: a schema-valid result event, then ``{"type":"result","result":`` before exit 0. The truncated line
    is inside the final turn, so the earlier result never stands in."""
    repo, spec = delegate_repo(tmp_path)
    set_steps(repo, spec, {**verdict_step(repo), "after": '{"type":"result","result":'})
    with pytest.raises(SystemExit) as e:
        review_cli.main(["review", "delegate", "M1.1", "--model", "opus", "--backoff", "0", "--json",
                         "--repo-root", str(repo)])
    run = json.loads(capsys.readouterr().out)
    assert e.value.code == 1 and run["state"] == "incomplete" and run["outcome"] == "rerun"
    assert CUT in run["reason"] and not _record(repo).exists()
    set_steps(repo, spec, verdict_step(repo))                                 # the same result alone is filed
    assert delegate(repo, "M1.1", "opus", sleep=lambda s: None)["outcome"] == "recorded"


# --- A1: the prompt asks for the object; the schema is the record's -----------------------------------------------

def test_the_output_schema_is_the_record_schema_less_what_specy_road_fills() -> None:
    record = json.loads((Path(rf.__file__).parent / "schemas" / "review-record.schema.json").read_text())
    schema = output_schema()
    assert set(schema["properties"]) == set(record["properties"]) - {
        "family", "independence", "notes_sha256", "signature", "launch_mode", "harness_model",
        "model_mismatch"} | {"notes"}
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
    told = file_instruction(prompt.resolve())   # M15.9 A1: the prompt file is named, its text never on argv
    assert fresh.argv == ["agent", "-p", "--output-format", "stream-json", "--mode", "ask", "--trust",
                          "--model", "gpt-6.1-sol", told] and fresh.session_id is None
    resumed = Cursor().reviewer_launch(prompt, None, tmp_path, session=("s1", True))
    assert resumed.argv == ["agent", "-p", "--resume", "s1", "--output-format", "stream-json", "--mode", "ask",
                            "--trust", told] and resumed.session_id == "s1"
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
    assert "sandbox_mode=read-only" in argv and "--force" not in argv
    schema = json.loads(Path(argv[argv.index("--output-schema") + 1]).read_text())
    assert strict_problems(schema) == []                                    # OpenAI strict mode accepts it
    assert list(schema["properties"]["acceptance"]["properties"]) == ["A1", "A2"]   # the leaf's ids
    out = Path(argv[argv.index("-o") + 1])                                  # a private scratch file, removed after
    assert repo not in out.parents and reviews not in out.parents and not out.exists()
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
                                                        "result": json.dumps(answer)})])
    assert run_main(role_prompt, "M1.1", "--model", "comp", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 0
    call = next(c for c in calls if list(c["cmd"][:2]) == ["agent", "-p"])   # the reviewer launch, by its argv
    assert call["cmd"][:7] == ["agent", "-p", "--output-format", "stream-json", "--mode", "ask", "--trust"]
    prompt = repo / "work" / "prompt-M1.1-reviewer-comp.md"   # M15.9 A1: named on argv, its text in the file
    assert "--force" not in call["cmd"] and call["cmd"][-1] == file_instruction(prompt.resolve())
    assert "**specy-road files your record.**" in prompt.read_text(encoding="utf-8")
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
    rc = run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli", "--run",
                  "--repo-root", str(repo))
    err = capsys.readouterr().err
    assert (rc, rf.review_path(repo, "M1.1", "gem").exists()) == ((1, False) if writes else (0, True))
    failure = next((line for line in err.splitlines() if line.startswith("review_failure: ")), "")
    assert bool(failure) is writes and (not writes or wrote_paths(failure) == ["work/out.txt"])
    prompt = (repo / "work" / "prompt-M1.1-reviewer-gem.md").read_text()
    assert "**specy-road files your record.**" in prompt


def test_a_custom_reviewer_command_under_review_delegate_is_checked_and_filed(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True})
    assert delegate(repo, "M1.1", "gem", sleep=lambda s: None)["outcome"] == "recorded"


@pytest.mark.parametrize("harness", ["codex", "cursor"])
def test_a_plain_text_wrapper_on_a_codex_or_cursor_entry_is_filed_from_its_final_message(tmp_path: Path, capsys,
                                                                                          harness: str) -> None:
    """The roster shape of a wrapper script as `channels.cli` (`codex exec … "<prompt>"`, `agent -p --output-format
    text`): no event stream, so the final message's JSON object is the answer."""
    repo, spec = delegate_repo(tmp_path, GENERIC.replace("harness: generic", f"harness: {harness}"))
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True})
    assert run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli", "--run",
                    "--repo-root", str(repo)) == 0
    assert rf.load_review(rf.review_path(repo, "M1.1", "gem"), ["A1", "A2"]).ok
    run = json.loads((rf.reviews_dir(repo, "M1.1") / "RUN-gem.json").read_text())
    assert run["source"] == "prompt-cli" and run["state"] == "complete" and not run["events"]   # M11.72's record


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


@pytest.mark.parametrize("bin_name,program", [
    ("bin", lambda b: "agy"),                                          # found on PATH
    ("tools with spaces", lambda b: f'"{b}/agy"'),                     # a quoted path with spaces stays one word
    ("tools with spaces", lambda b: f"'{b}/agy'"),
    ("tools with spaces", lambda b: f"{b}/agy".replace(" ", "\\ ")),
], ids=["on-path", "double-quoted", "single-quoted", "backslash-escaped"])
def test_an_antigravity_review_delegate_passes_json_schema_and_files_structured_output(tmp_path: Path, monkeypatch,
                                                                                       bin_name: str,
                                                                                       program) -> None:
    bin_dir, spec = tmp_path / bin_name, tmp_path / "agy-spec.json"
    cli = f'{program(bin_dir)} -p "<prompt>"'.replace("'", "''")      # in a single-quoted YAML string
    repo = make_review_repo(tmp_path, orchestration=GENERIC.replace("{fake} {prompt}", cli))
    reviews = rf.reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True)
    (reviews / "PACKET.md").write_text("# Review packet\n")
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
