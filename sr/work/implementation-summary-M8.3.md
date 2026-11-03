# Implementation summary: M8.3 — reviewer runs are read-only and specy-road writes the review record from structured output

Branch `feature/rm-reviewer-runs-are-read-only-and-specy-road-writes-the-review-record-from-structured-output`, merged with `origin/WIP/improvements-0-3-1` (fast-forward to `4a82059f`, which brings the M11.59 adapter split) before the change. Round 1: `84f88f75`; touch zones `322e41fd`. Round 2 answers Codex Sol's block (`REVIEW-gpt-6.1-sol.md` at `322e41fd`); the READY file names its commit.

## What changed

- **Adapters (A4, A5).** `Adapter.reviewer_launch` / `Adapter.final_message` on the base (generic: unsupported / `None`), with one implementation per harness module:
  - `worker_adapter_claude.py`: the bare reviewer launch passes `--disallowedTools "Bash(git commit *)" "Bash(git push *)" "Bash(gh *)"` right after `--allowedTools Read,Edit,Bash`, and `--json-schema '<schema>'`; `final_message` reads the `result` event's `structured_output`, else its text.
  - `worker_adapter_codex.py`: `codex exec --json [-m] [effort] -c sandbox_mode=read-only -c approval_policy=never --output-schema <file> -o <OUTPUT-<model>.json> -`; a resume keeps the read-only policy without the two flags (documented for `codex exec` only); `final_message` reads `agent_message` text.
  - `worker_adapter_cursor.py`: `agent -p [--resume id] --output-format stream-json --mode ask --trust [--model] <prompt>`, no `--force`; `final_message` reads the `result` text. Executor launches are unchanged, so `docs/design-notes/M8.7-runtime-verification-harness-facts.md` ("Review-only runs omit `--force`") matches the code.
- **Antigravity (A1, round 2).** `agy` runs as a `generic` harness. The harness-compatibility triage, M8.6's "agy generic profile" and `test_harness_facts` all require a facts record and `--help` captures for every non-generic harness, and `agy` isn't installed. So instead of a new harness value, `worker_adapter_base.reviewer_cli` handles any reviewer command whose program is `agy`:
  - It inserts `--json-schema <schema file>`, `--output-format json`, `--sandbox` and `--print-timeout 30m` right after the program, each only when absent.
  - It refuses `--dangerously-skip-permissions`.
  - The answer comes from the envelope's `structured_output`, which `file_review` unwraps (Claude's json envelope too).
  - The flags come from https://antigravity.google/docs/cli/headless (fetched 2026-11-03): `--json-schema` takes "a schema string, a path to a `.json` schema file, or a primitive type name"; `json` gives one envelope with `status`, `response` and `structured_output`; `--sandbox` is the only sandbox control; there is no read-only mode; `--print-timeout` defaults to 5m.
  - `review delegate` and `prompt --channel cli` both pass every custom reviewer command through `reviewer_cli`.
- **Writer (A1, A2, A3).** `specy_road/review_record_write.py`.
  - The output schema is the review-record schema less the fields `review record` fills (`family`, `independence`, `notes_sha256`, `signature`, `launch_mode`), plus `notes`.
  - **Round 2: the write check is strict.** `snapshot` records `(size, mtime_ns)` of every file in the checkout the reviewer ran in, git-ignored and `work/` files included, and of the leaf's hand-off directory when it lies outside that checkout. It also records `HEAD` and every ref.
  - The only exemptions are `runtime_files`: `notes-<model>.md` and what the run itself writes during the turn (`RUN-<model>.json`, its `.json.tmp`, `RUN-<model>.log`, `OUTPUT-<model>.json`, `review-output.schema.json`, `.review-run.lock`). Prompts and packets are written before the first snapshot, so they need no exemption.
  - The walk skips `.git` and nested checkouts (a directory holding `.git`, e.g. a linked worktree under `work/.worktrees`), since those are other repositories.
  - `review_failure` files nothing and puts back a self-filed `REVIEW-<model>.md`. `rerun` covers missing output, a schema mismatch, and a refusal from `review record`. `recorded` goes through `review record` itself.
  - `review_run_lock`: a non-blocking `flock` (`msvcrt` on Windows) on `.review-run.lock`. Two reviewer runs of one leaf share its hand-off directory and would otherwise fail each other, so a second run is refused at once.
  - `reviewer_env`: the reviewer process gets `PYTHONDONTWRITEBYTECODE=1` and `PYTEST_ADDOPTS=-p no:cacheprovider`, so an honest re-run of Python tests writes nothing under the strict check.
  - `run_and_file` runs one `prompt --channel cli` turn under the lock and files it.
- **Prompt (A1).** Every reviewer prompt ends with the schema section.
  - `read_back=True` says specy-road files the record and the reviewer writes nothing but notes, caches and build output included. Round 2: `prompt --channel cli` now always reads back.
  - `read_back=False` (`paste`, `subagent`) asks for the object and still has the reviewer file it with `review record`.
- **Custom commands (round 2).** `prompt --channel cli` on a roster `channels.cli` or profile `access.cli` reviewer no longer runs it uncaptured. `run_custom_reviewer` passes it through `reviewer_cli`, runs it as `sh -c` under `run_and_file` with the same lock, write check and filing, and parses its output with the entry's harness adapter (generic: the last JSON object). `review delegate` already captured custom commands; they now get `reviewer_cli` too.
- **Wiring.** `prompt --channel cli` runs the adapter's reviewer command for `claude-code`, `codex` and `cursor` entries without `channels.cli` (`run_default_reviewer`). `review delegate` does the same for every non-generic entry without `channels.cli`, takes the lock, snapshots around `_attempts`, files the result, and records `outcome`. Its `_turn` env goes through `reviewer_env`, and the resume prompt asks for the JSON again.
- **Docs.** `docs/orchestration-review.md` covers the argv, the per-harness output table (with an Antigravity row), the strict exemptions, the lock, the cache env and the advice to run reviewers where nothing else writes. The two `specyrd` command stubs were updated to match.

## Touch zones (report, per the brief's section 7)

The zones now include `specy_road/review_delegate.py` and `docs/orchestration-review.md` (`322e41fd`). Round 2 needed nothing new: every file it changes is inside them, and the new `tests/review_delegate_helpers.py` is under `tests/`. `docs/pm-llm-review.md` (the PM GUI's LLM Review guide) is unrelated to implementation reviewers and was left untouched.

## Verification (round 2)

- Targeted: `pytest -q -n 8 -p no:cacheprovider` over the following files ran 211 tests: 210 passed, 1 failed:
  - `tests/test_review_record_write.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`
  - `tests/test_prerelease_review.py`, `tests/test_prerelease_s2.py`, `tests/test_lean_rules.py`, `tests/test_finish_work_cleanup.py`, `tests/test_harness_facts.py`, `tests/test_worker_cli.py`
  - The failure was `tests/test_worker_cli.py::test_sync_wait_ends_on_an_event_or_times_out_with_exit_2`, a wait-timeout test, at load average 38 with other sessions' suites running. It passed when re-run alone, and it doesn't touch reviewer code.
- After the `run_custom_reviewer` refactor: `tests/test_review_record_write.py tests/test_review_files.py tests/test_prerelease_review.py tests/test_models_and_prompt.py` plus that worker test: 82 passed.
- `specy-road file-limits`: OK. `python scripts/check_test_private_imports.py`: 0 new.
- `ruff check specy_road tests scripts` reports one C901, `uncommitted_refs_section` in `review_packet_uncommitted_refs.py`, which came in with the WIP merge. The `run_cli_channel` C901 this round introduced is fixed by extracting `run_custom_reviewer`.
- Red/green: with `written` returning nothing and `reviewer_cli` passing every command through, 8 tests in `tests/test_review_record_write.py` fail: the three write-regression cases, the self-filed record, refs and runtime files, the captured custom command that writes, and both agy tests. With the files restored, all 23 pass.
- The full suite was not re-run this round. Round 1's full run passed: 1700 passed, 2 skipped; then 1615 passed.

## Not verified / open

- **No live harness runs.** The Claude and Codex flags come from the tracked captures, Cursor's from the fixture, and Antigravity's from the vendor page above (not installed; M8.6 records its runtime checks as not run).
  - Whether Codex strict structured output accepts this schema is unverified.
  - Whether `agy --output-format json` prints one line or many is unverified. Both work: `json_object` takes the last top-level object from the whole output.
- **Strict check in a shared checkout.** Any write by another session in the checkout during a review now fails it. That covers a coordinator, an executor, another leaf's reviewer, or `specy-road` commands writing `.specyrd/cache`. Reviewers should run where nothing else writes (`review delegate --worktree <quiet checkout>`). The report lists the paths, so a foreign write is visible.
- **Walking a large checkout is slow.** The main toolkit checkout has 76k files and took about 26s cold with nested checkouts included; this walk skips them.
- **What the check doesn't see:** writes outside the checkout and the hand-off directory, for example `/tmp`, `~`, or another worktree.
- **A `channels.cli` that opens an interactive harness** now has its output captured under `prompt --channel cli`, so it gets no terminal. Use `paste` for an interactive reviewer.

## Added

- `Adapter.reviewer_launch` (base, raises `Unsupported`) and `Adapter.final_message` (base, `None`): generic entries run their command; their output is read whole.
- `CODEX_REVIEW_POLICY`, `REVIEWER_DISALLOWED`: A5 and A4.
- `ClaudeCode.reviewer_launch` `--disallowedTools`/`--json-schema`, `ClaudeCode.final_message`; `Codex.reviewer_launch` (fresh/resume) and `Codex.final_message`; `Cursor.reviewer_launch` and `Cursor.final_message` (its `is_error` guard keeps an error's text from reading as an answer): A1, A4, A5.
- `AGY_REVIEW_FLAGS`, `reviewer_cli`: A1's Antigravity support. Branches:
  - unbalanced quotes are left for `placeholder_problem`;
  - a non-`agy` program is left unchanged;
  - `--dangerously-skip-permissions` is refused, since it would auto-approve writes;
  - a flag already present is not added twice.
- `review_record_write.output_schema`, `write_schema`, `output_path`, `schema_lines`: the A1 schema, its file and the prompt section.
- `runtime_files`, `_walk`, `snapshot`, `Snapshot` (`exempt`, `top`, `restore`), `written`, `_own_records`: the A2 write check. `_walk`'s `OSError` branches cover a directory or file removed mid-walk; the nested-checkout skip covers linked worktrees.
- `review_run_lock`, `ReviewRunBusy`: keep one leaf's reviewer runs from failing each other under the strict check. The `ImportError` branch is Windows; `OSError` means busy.
- `reviewer_env`: lets an honest Python test re-run write nothing.
- `run_text`, `final_output`, `json_object`, the envelope unwrap in `file_review`: A1/A3 extraction.
- `file_review`, `Outcome`, `_review_record` (output captured because `review delegate --json` owns stdout): the A1/A2/A3 outcome.
- `run_logged` (`OSError` for a harness missing from PATH, stdin `OSError` for one that quits early) and `run_and_file` (busy lock reported, exit 1): the `prompt --channel cli` turn.
- `role_prompt.READ_BACK_HARNESSES`, `READ_BACK_LINES`, `PASTED_LINES`, `reviewer_lines`, `read_back`, `_shown`, `run_default_reviewer`, `run_custom_reviewer` (its `Unsupported` branch reports a refused `agy` command): the A1 prompt and both cli paths.
- `review_delegate._Harness.default`/`.launch_mode`, the `reviewer_cli` call, the `review_run_lock` `ExitStack`, the `file_review` call, the `outcome` field, `reviewer_env` in `_turn`, and the new `RESUME_PROMPT`: wiring.
- `tests/review_delegate_helpers.py` (new, public; answers Sol's test-integrity finding):
  - `FAKE` (now with a `plain` step for a final-message-only harness), `CAPACITY`, `delegate_roster`, `delegate_repo` (optional roster with `{fake}`);
  - `set_steps`, `fake_calls`, `verdict_step` (optional model), `fake_reviewer_run` (fakes `review_record_write.run_logged`);
  - all moved from `tests/test_review_delegate.py` and `tests/test_review_files.py`, whose bodies now import them. No assertion was weakened, except that the `channels.cli` test now expects exit 1 and a rerun line, because `cat | head` prints no verdict.
- `tests/review_repo_helpers.review_output`: a valid reviewer JSON.
- `tests/test_review_record_write.py` (23 tests):
  - A2: writes to a tracked file, an untracked `work/` file and an ignored hand-off file each fail, file nothing, and are reported by path (Sol's public-interface regression). Notes are the one write allowed. A self-filed record is put back. A commit (refs) and another model's run file count; this run's own log and a nested checkout don't.
  - The lock refuses a second run. The reviewer env.
  - A3 rerun cases; JSON extraction; schema derivation; pasted vs read-back prompts.
  - A5: Cursor and Codex argv pinned, with the M8.7 note cross-check; a Codex `review delegate` end to end through a fake `codex`; a Cursor `prompt --channel cli` end to end.
  - Custom `channels.cli` under `prompt --channel cli`, filed or failed by its writes, and under `review delegate`.
  - `reviewer_cli` cases, and an Antigravity `review delegate` end to end through a fake `agy` that prints a pretty-printed envelope.
