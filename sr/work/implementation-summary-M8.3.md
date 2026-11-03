# Implementation summary: M8.3 — reviewer runs are read-only and specy-road writes the review record from structured output

Branch `feature/rm-reviewer-runs-are-read-only-and-specy-road-writes-the-review-record-from-structured-output`, merged with `origin/WIP/improvements-0-3-1` (fast-forward to `4a82059f`, which brings the M11.59 adapter split) before the change. Implementation commit: `84f88f75`.

## What changed

- **Adapters (A4, A5).** `Adapter.reviewer_launch` / `Adapter.final_message` on the base (generic: unsupported / `None`), with one implementation per harness module:
  - `worker_adapter_claude.py`: the existing bare reviewer launch now passes `--disallowedTools "Bash(git commit *)" "Bash(git push *)" "Bash(gh *)"` right after `--allowedTools Read,Edit,Bash`, and `--json-schema '<schema>'` when given the schema file; `final_message` reads the `result` event's `structured_output`, else its text.
  - `worker_adapter_codex.py`: `codex exec --json [-m] [effort] -c sandbox_mode=read-only -c approval_policy=never --output-schema <file> -o <OUTPUT-<model>.json> -`; a resume (`codex exec resume`) keeps the read-only policy but leaves out the two flags, which are documented for `codex exec` only; `final_message` reads `agent_message` text.
  - `worker_adapter_cursor.py`: `agent -p [--resume id] --output-format stream-json --mode ask --trust [--model] <prompt>`, no `--force`; `final_message` reads the `result` text. Executor launches are unchanged (Cursor keeps `--force`, Codex `workspace-write`), so `docs/design-notes/M8.7-runtime-verification-harness-facts.md` ("Review-only runs omit `--force`; executor template keeps `--force`", and its `sandbox_mode=read-only` Codex run) now matches the code. The note itself needed no edit.
- **Writer (A1, A2, A3).** New `specy_road/review_record_write.py`: the output schema is the review-record schema less the fields `review record` fills (`family`, `independence`, `notes_sha256`, `signature`, `launch_mode`), plus a required `notes`. It also covers the before/after snapshot, the final-message extraction and the outcome:
  - `review_failure`: the run changed a checkout file (outside the project's `work/`), moved `HEAD`, or filed its own `REVIEW-<model>.md`/history copy. That self-filed record is put back as it was.
  - `rerun`: no JSON object, a schema mismatch, or `review record` refused it.
  - `recorded`: the notes go to `notes-<model>.md`, then `review record` itself files the record. That reuses every check, the family, signing refusal, `history/` copy and launch mode.
- **Prompt (A1).** `role_prompt.build_prompt` ends every reviewer prompt with the schema section. With `read_back=True` (the default, used by `review delegate`) it says specy-road files the record and the reviewer writes nothing but notes. With `read_back=False` (`paste`, `subagent`, a roster `channels.cli`) it asks for the object and still has the reviewer file it with `review record`.
- **Wiring.** `prompt --channel cli` runs the adapter's reviewer command for `claude-code`, `codex` and `cursor` entries without `channels.cli` (`run_default_reviewer`, replacing `run_bare_reviewer`), logs to `RUN-<model>.log`, and files the result. `review delegate` does the same for every non-generic entry without `channels.cli`, and files from the run log or Codex's `-o` file for every run, so a `channels.cli`/generic reviewer's final message is parsed as plain JSON. The run record gains `outcome`, and the resume prompt asks for the JSON again.
- **Docs.** `docs/orchestration-review.md` now has the new argv and a "Reviewer output and the read-only check" section. Its step 2 no longer says Codex reviewers run `workspace-write`, and step 5 describes the outcome. The two `specyrd` command stubs (`specyrd-prompt.md`, `specyrd-review-record.md`) each got one line.

## Touch zones (report, per the brief's section 7)

Final list I needed: the brief's zones **plus** `specy_road/review_delegate.py` and `docs/orchestration-review.md`; **minus** `docs/pm-llm-review.md`, which documents the PM GUI's advisory LLM Review button and has nothing to do with implementation reviewers. I left it untouched.

- `specy_road/review_delegate.py`: outside the zones, edited because the maintainer asked that review delegate get the reviewer launches. It only ever called `ClaudeCode.reviewer_launch`, so Cursor and Codex reviewers ran the executor command. The edit is wiring only: `_Harness.default`/`launch_mode`, the `reviewer_launch` call, the snapshot before `_attempts`, `file_review` after them, the `outcome` field, the resume prompt and two docstring sentences. No logic moved, and nothing was deleted except the replaced lines.
- `docs/orchestration-review.md`: outside the zones. It is where reviewer launches are documented, and it stated the opposite of A5 (Codex `workspace-write`). The edits replace the argv block and step 2's Codex sentence and add one section. No other text was removed.

## Verification

- `pytest -n auto` over the whole suite, in two halves to fit the foreground limit: 1700 passed, 2 skipped; then 1615 passed. Both halves exited 0.
- Targeted: `pytest tests/test_review_record_write.py tests/test_review_delegate.py tests/test_review_files.py tests/test_worker_adapters.py tests/test_models_and_prompt.py tests/test_prerelease_review.py` all passed.
- `specy-road file-limits`: OK. I added the `reviewer_lines` helper so `build_prompt` stays under the 80-line function cap.
- Red/green: with `file_review`'s write check disabled, Codex's reviewer policy set back to `workspace-write`, and the Claude deny list emptied, 5 tests fail: both A2 delegate tests, the Codex argv test, the Codex end-to-end test, and the pinned Claude argv test. With the fix restored they pass.
- `ruff check specy_road tests scripts` reports one C901, in `review_packet_uncommitted_refs.py`. That file came in with the WIP merge and this leaf does not touch it.
- `scripts/check_clones.py` (pylint from a scratch venv) reports 2 new pairs, `abort_task_pickup`↔`pm_sync` and `planning_sheet_bootstrap`↔`planning_scaffold_check`. Neither involves a file this leaf touched.

## Not verified / open

- Live harness runs were not made. The flags come from the tracked captures and harness-facts fixture (`claude --help` `--json-schema <schema>`; `codex exec --help` `--output-schema <FILE>`, `-o`; Cursor `--mode ask`).
  - Whether Codex's strict structured output accepts this schema (optional properties, `propertyNames`) is unverified. A rejection would surface as a harness error, which the run reports as incomplete.
  - Claude's `structured_output` field name on the `result` event is also unverified. If it is absent, the result text is parsed instead.
- Antigravity has no adapter, so specy-road passes no `--json-schema` for it. An `agy` entry's own `channels.cli` would have to pass it, and its final message is parsed as plain JSON.
- `prompt --channel cli` with a roster `channels.cli` still runs the command as written, without capturing output, because an interactive harness needs its terminal. That reviewer files with `review record` itself, and A2 is not checked on that path. `review delegate` checks every path.
- Paths git ignores, other than the model's own record files, are not inspected by the write check.

## Added

- `Adapter.reviewer_launch` (base, raises `Unsupported`): a generic entry has no default reviewer command; the error says to set `channels.cli`.
- `Adapter.final_message` (base, returns `None`): generic output is read whole as the final message.
- `CODEX_REVIEW_POLICY`: read-only sandbox config for Codex reviewer turns (A5).
- `REVIEWER_DISALLOWED`: the three deny patterns for the bare Claude reviewer (A4).
- `ClaudeCode.reviewer_launch` `--disallowedTools` / `--json-schema` args and `ClaudeCode.final_message`: A4 and A1.
- `Codex.reviewer_launch` (fresh/resume branch) and `Codex.final_message`: A5 and A1. The resume branch exists because `exec resume` documents no `--output-schema`/`-o`.
- `Cursor.reviewer_launch` and `Cursor.final_message`: A5 and A1. The `is_error` guard stops an error result's text from being read as an answer.
- `review_record_write.output_schema`, `write_schema`, `output_path`, `schema_lines`: A1 schema, the file the harness flags read, and the prompt section.
- `review_record_write.snapshot`, `Snapshot.restore`, `written`, `_digest`, `_own_records`: A2 write detection, plus putting back a self-filed record so the gate never counts it. `_digest` handles a missing file or directory (`OSError` from a deleted path or a nested repo). The rename branch handles git's `-z` second path.
- `review_record_write.run_text`, `final_output`, `json_object`: A1/A3 extraction from the log, the Codex `-o` file, or plain text.
- `review_record_write.file_review`, `Outcome`, `_review_record`: A1/A2/A3 outcome. Output is captured because `review delegate --json` owns stdout.
- `review_record_write.run_logged`: runs a `prompt --channel cli` reviewer turn with a log, echoing event summaries. Its `OSError` branch covers a harness that isn't on PATH, and its stdin `OSError` covers a harness that quits early.
- `role_prompt.READ_BACK_HARNESSES`, `READ_BACK_LINES`, `PASTED_LINES`, `reviewer_lines`, the `read_back` parameter, `_shown`, `run_default_reviewer` (replaces `run_bare_reviewer`): A1 prompt, routing Codex and Cursor too, and a terminal line that doesn't echo the prompt or the inline schema.
- `review_delegate._Harness.default` / `.launch_mode`, the `file_review` call, the `outcome` field and the new `RESUME_PROMPT` text: wiring (see Touch zones).
- Test helper `tests/review_repo_helpers.review_output`: a valid reviewer JSON.
- `tests/test_review_delegate.py`: the fake answers with JSON (`answer`/`raw` steps) instead of writing the record. `_files_record` now returns an answer, and the clean-exit test asserts the rerun reason.
- `tests/test_review_files.py`: `_fake_run` also fakes `role_prompt.run_logged`. The bare-reviewer test now pins the full argv (A4) and checks the filed record (A1).
- `tests/test_review_record_write.py`, 13 tests:
  - A2: a checkout edit fails the review; a self-filed record fails it and is put back; a commit (HEAD) counts as a write while specy-road's `work/` doesn't.
  - A3: truncated JSON and a schema mismatch are rerun requests; a `review record` refusal (stale commit) is a rerun request.
  - JSON extraction cases; the output schema derivation; pasted vs read-back prompt text.
  - A5: Cursor argv pinned, with the M8.7 note cross-check and executors keeping `--force`; Codex argv pinned, fresh and resume.
  - End to end: a Codex `review delegate` through a fake `codex` binary filing from `-o`, and a Cursor `prompt --channel cli` filing from the result text.
