# Implementation summary: M8.3 — reviewer runs are read-only and specy-road writes the review record from structured output

Branch `feature/rm-reviewer-runs-are-read-only-and-specy-road-writes-the-review-record-from-structured-output`, merged with `origin/WIP/improvements-0-3-1` (fast-forward to `4a82059f`, which brings the M11.59 adapter split) before the change. Round 1: `84f88f75`; touch zones `322e41fd`. Round 2 answers Codex Sol's block (`REVIEW-gpt-6.1-sol.md` at `322e41fd`); the READY file names its commit. Merged `origin/WIP/improvements-0-3-1` again at `260030ad` (M11.23, M8.6). The only conflict was `worker_adapters.py`'s docstring: M11.23's `channels.cli_resume` and `permission_denials` text and this leaf's reviewer paragraph are both kept. M11.23's logic lives in `worker_adapter_parsers.py` and `worker_ops_*`, so no adapter code moved. `6b22ff8a` adds one test against M8.6's shipped `agy` profile. Merged WIP again at `869950c5` (M11.71, forced RCA). The only conflict was `role_prompt.build_prompt`'s signature and docstring, and the `build_prompt` call in `main`. `build_prompt` now takes both `read_back` and M11.71's `force_reason`, and `main` keeps M11.71's `--force`/`--reason` checks and passes both. The rca branch (`rca_trigger`, `forced` precondition) and the reviewer branch (`reviewer_lines`, `schema_lines`) are unchanged. Merged WIP again at `67a4b3fb` (M11.72, M8.5, M11.39, M11.27, and new Codex reviewer entries). Resolutions: `role_prompt.py`: M11.72's open/close `RUN` wrapper in `main` now wraps this leaf's reviewer runners, with `ref` and the roster command passed through, and its transcript is threaded through `run_default_reviewer`/`run_custom_reviewer` into `review_record_write.run_and_file`/`run_logged`, which add the raw lines, a launch error and the outcome line; the runners, M11.72's `_stream_and_capture` and the plain-CLI fallback (`run_plain_cli`) moved unchanged into the new `bundled_scripts/role_prompt_cli.py`, because the merge took `role_prompt.py` to 442 lines; that file was added to the zones (`6501adee`), and the move also clears the `run_cli_channel` C901 the merge introduced; `review_delegate.py`: WIP's move of `CAPACITY`/`valid_record`/run helpers to `reviewer_run_failure` and its `source`/`events` fields are kept, the env is `reviewer_env(harness_env(os.environ, "reviewer"))`, the JSON `RESUME_PROMPT` is kept, and a new `_close` sends a recorded verdict through M11.72's `close_run`, while a review failure or rerun request stays incomplete with a `reviewer-failure` event (the harness error, else the outcome); `tests/review_repo_helpers.py`: both helpers kept; `tests/test_review_delegate.py`: WIP's new tests kept, on the public helpers; `tests/test_review_files.py`: WIP's private `_fake_run` (now with `Popen`) folded into the public `fake_reviewer_run`, which also patches `role_prompt_cli`. Re-verified: `pytest` over the 14 reviewer/prompt/adapter/guard/availability/RCA test files gave 251 passed, and `tests/test_review_record_write.py` 26 after `474e3554` added the codex/cursor plain-wrapper test; file limits OK; ruff's remaining C901s (`uncommitted_refs_section`, `load_availability_overlay`) are WIP's.

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

- After the WIP merge (`260030ad`): `pytest -q -n 6 -p no:cacheprovider` over `tests/test_review_record_write.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_worker_resume_permissions.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py` and `tests/test_harness_facts.py`: 189 passed. File limits OK; private imports 0 new; `ruff` unchanged (the WIP C901 only).

- After the M11.71 merge (`869950c5`): `pytest -q -n 6 -p no:cacheprovider` over `tests/test_review_rca.py`, `tests/test_review_record_write.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_prerelease_s2.py`, `tests/test_lean_rules.py`, `tests/test_worker_adapters.py` and `tests/test_planning_sheet_bootstrap.py`: 154 passed. File limits OK; `ruff` on `role_prompt.py` clean.

## Round 3 (Codex Sol's block at `f859aff5`; commit `df2c588c`)

- **A2, content compare.** Each file in the snapshot is recorded as `(size, mtime_ns, sha256)` (`_content`; a symlink hashes its target text; an unreadable file is `unreadable`). An equal-length overwrite with its atime/mtime put back is now a review failure. Regression through `review delegate`: `test_a_same_length_rewrite_with_its_mtime_put_back_is_a_review_failure`. The fake harness gained a `keep_mtime` write option.
- **A3, malformed final object.** `json_object` takes the last complete top-level object only if it starts a line (prose or a ```` ```json ```` fence may precede it) and no `{` appears after it. So a valid object followed by a truncated or malformed one is a rerun request, and the earlier object never stands in as the verdict. Other trailing text without a brace stays permitted: a closing fence, or a harness's status lines such as a token count, which a plain-text Codex wrapper may print after the answer. End-to-end regression through `review delegate`: `test_a_valid_object_followed_by_truncated_json_is_a_rerun_request_and_files_nothing` (the same object alone is then filed). The unit cases now cover a cut-off later object, a truncated object whose inner object would decode, and an object that doesn't start its line.
- **Verification:**
  - `pytest -q -n 6 -p no:cacheprovider` over `tests/test_review_record_write.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_orchestration_guard_hooks.py`, `tests/test_review_rca.py`, `tests/test_harness_facts.py` and `tests/test_role_prompt_file_limits.py`: 234 passed. `tests/test_review_record_write.py` alone: 28 passed.
  - File limits OK; private imports 0 new. `ruff`'s two C901s are WIP's.
  - Red/green: with the digest and the trailing-object rule removed, the three new tests fail.
- **Cost:** hashing every file twice makes the walk slower on a large checkout, which is one more reason to run reviewers from the leaf's worktree.
- **WIP merge `cfc98efe`** (M11.36 resumed-delta approval, rework findings, and more). The only conflict was in `role_prompt.py`: M11.36's `reviewer_lines(root, node_id, model, t, ref, loop)`, which returns `(preamble, packet, error)` and adds the resumed-delta preamble, gained this leaf's `read_back` argument and appends `READ_BACK_LINES`/`PASTED_LINES`; `build_prompt` uses M11.36's call form and still ends the packet with `schema_lines()`. The round-3 fixes (content digest, final-object rule, both regressions) are unchanged. `pytest -n 4` over the leaf's test files plus `tests/test_resumed_delta_review.py`, `tests/test_rework_findings_in_prompt.py` and `tests/test_ready_command.py`: 174 passed; file limits OK.

## Round 4 (Codex Sol's block at `c12efa63`; commit `eacd6581`)

Required change → what changed:

- **"Protect the Git index in the post-run write check, and add a public-interface regression proving an index-only write is a review failure and files no verdict."**
  - **Check:** `review_record_write.snapshot` adds a `git index` entry, the SHA-256 of `git ls-files --stage -v -z`. It covers each entry's mode, blob, stage and assume-unchanged / skip-worktree flag. So `git update-index --assume-unchanged`, `git rm --cached` and `git add` are writes (reported as `wrote git index`), the verdict is not filed, and the run is a review failure.
  - **Why not the index bytes:** a read-only `git status` rewrites `.git/index` when it refreshes the stat cache, and comparing bytes would fail honest reviews.
  - **Regressions** in `tests/test_review_record_write_git.py`, split out because `tests/test_review_record_write.py` hit 405 lines:
    - `specy-road review delegate` with `update-index --assume-unchanged` and with `rm --cached`: each exits 1 with `outcome: review_failure` and no `REVIEW-opus.md`. The first also shows that `git status` sees no change, which is how the write hid.
    - `specy-road prompt --channel cli` with the same write: exits 1, `review_failure` on stderr, no record.
    - `git status` against a stale stat cache rewrites the index file's bytes and the review is still recorded.
  - The fake harness in `tests/review_delegate_helpers.py` gains a `git` step. `docs/orchestration-review.md` names the index among the writes.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`): 163 passed. After the split, the two `review_record_write` test files: 32 passed.
  - File limits OK; private imports 0 new.
  - Red/green: with the `git index` entry removed, the three index-only cases fail and the `git status` case still passes.
- **Still not inspected (round 4):** other `.git` metadata. Round 6 covers it.

## Round 5 (Codex Sol's block at `fca22fea`)

- **"Remove the new mock call-count assertion at `tests/test_review_record_write.py:260`; select the reviewer launch by its observable argv."** `test_prompt_channel_cli_runs_a_cursor_reviewer_read_only_and_files_its_answer` no longer unpacks exactly one recorded call (`(call,) = calls`). It selects the launch whose argv starts `agent -p` and keeps the exit code, the full argv prefix, the no-`--force` check, the prompt text and the filed-record assertions. Verification: `pytest -n 4 tests/test_review_record_write.py`, 28 passed; file limits OK.

## Round 6 (Codex Sol's block at `07169a5a`; commit `4523789e`)

Required change → what changed:

- **"Protect Git metadata in the post-run write check, including the resolved worktree/common Git directories and the checkout's .git pointer, while keeping the semantic index comparison."**
  - New `review_record_write._walk_git`, called from `snapshot`. It walks every file of the resolved common Git directory (`rev-parse --path-format=absolute --git-common-dir`: hooks, config, info, objects, refs, logs) and of the worktree's own Git directory (`--git-dir`), content-hashed like the checkout. A linked worktree's `.git` pointer file is digested too.
  - Skipped: `<common>/worktrees`, other linked worktrees' private directories (other checkouts, as nested checkouts already are), and raw index bytes. This checkout's index is skipped because the semantic `git index` comparison (`ls-files --stage -v`) stands in for it, so a `git status` stat refresh is still not a write. The main checkout's index is skipped when the reviewer is in a linked worktree, since it belongs to that other checkout.
  - `_walk` takes a `skip` set for this.
- **"Add a public-interface regression proving a reviewer-created hook is a review_failure and files no verdict."** In `tests/test_review_record_write_git.py`, through `specy-road review delegate`:
  - a reviewer-created `.git/hooks/pre-commit` in the main checkout exits 1 with `outcome: review_failure`, reason `wrote .git/hooks/pre-commit`, and no record;
  - with `--worktree <linked worktree>`, a hook written into the common Git directory, and a rewritten worktree `.git` pointer, are each a review failure with no record.
  - The existing stale-stat `git status` test still records. `test_a_commit_and_an_ignored_cache_count_as_writes_and_other_checkouts_do_not` now also requires the commit's `.git/` metadata among the writes.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`): 166 passed.
  - File limits OK; private imports 0 new; ruff's two C901s are WIP's.
  - Red/green: without the `_walk_git` call, the hook, linked-worktree hook, pointer and commit-metadata tests fail.
- **Cost and the shared repository:**
  - On this overloaded machine one snapshot of a toolkit worktree, including its ~5.7k Git files, took about 55s.
  - The common Git directory is shared by every worktree. Another session's commit or fetch during a review (new objects, logs, refs) now counts as a write, as refs already did. Run reviewers when nothing else commits to the repository.

- **WIP merge `e2c1a2d0`** (M8.2 hardened launches and chore reviews, M10.20, M11.35, review lessons). Conflicts and resolutions: `worker_adapter_claude.py` and `worker_adapter_codex.py` keep M8.2's executor permissions, Codex memory-off and per-profile `CODEX_HOME` beside this leaf's read-only `reviewer_launch`/`final_message`; `role_prompt.py`'s reviewer preamble has M10.20's `verify_cmd_lines` and the review-lessons lines plus this leaf's `READ_BACK_LINES`/`PASTED_LINES`. `review_delegate.py` merged without a conflict marker but changed behaviour: M8.2's chore reviews (`--review` chores) have a reviewer that writes its own verdict file, so a chore run keeps M8.2's contract. That means Claude's bare reviewer without the schema, else the adapter's own command, no `reviewer_cli` flags, no snapshot or JSON filing, `close_run` as before, and its own resume prompt (`CHORE_RESUME_PROMPT`). M8.3's read-only check and filing stay on roadmap reviews. The round 3–6 fixes are unchanged. `pytest -n 4` over the leaf's test files plus `tests/test_review_lessons.py`, `tests/test_verify_cmd.py`, `tests/test_worker_turn_check.py`, `tests/test_chore_mode.py` and `tests/test_review_hardening.py`: 216 passed. File limits OK; ruff clean.

## Round 7 (gpt-5.6-sol-medium's block at `e6195893`; commits `fc5628cf`, `f669980a`)

Required change → what changed:

- **"Include file permission mode in the checkout, hand-off, Git-directory, and linked-worktree .git-pointer snapshots."**
  - `_walk` now records `(st_mode, size, mtime_ns, sha256)` for every file. That covers the checkout, the hand-off directory, and the common and worktree Git directories, which all go through `_walk`.
  - `_walk_git` records the same for a linked worktree's `.git` pointer. A `chmod` alone is a write.
  - `docs/orchestration-review.md` says files are compared by permission mode too.
- **"Add a public-interface regression proving a reviewer-only chmod is a review_failure and files no verdict."**
  - `test_review_delegate_cli_fails_a_reviewer_only_chmod_and_files_no_verdict` in `tests/test_review_record_write_git.py`, through `specy-road review delegate`, is parametrized over the four areas: `src/a.py`, `work/reviews/M1.1/PACKET.md`, `.git/config`, and a linked worktree's `.git` with `--worktree`.
  - Each time the fake reviewer flips only the owner-execute bit. The test confirms that content, size and mtime are unchanged and that the run is a `review_failure` naming the path, with no `REVIEW-opus.md`.
  - The fake harness gained a `chmod` step.
- **File limits and touch zones:** the mode fix took `specy_road/review_record_write.py` to 401 lines. The post-run write check (`runtime_files`, `_own_records`, `_content`, `_walk`, `_walk_git`, `Snapshot`, `snapshot`, `written`, and the `OUTPUT_SCHEMA_NAME` / `OUTPUT_PREFIX` / `LOCK_NAME` constants it uses) moved, otherwise unchanged, to the new `specy_road/review_write_check.py`. `review_record_write` re-exports those names, so callers and tests are unchanged. The new file was outside the touch zones, so it was added with `specy-road edit-node M8.3 --add touch_zones=specy_road/review_write_check.py` (`f669980a`).
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`): 176 passed, before and after the split.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: without `st_mode` in the two snapshot tuples, all four chmod cases fail.

## Round 8 (gpt-5.6-sol-medium's block at `3387a90d`; commit `3d2a7670`)

Required change → what changed:

- **"Make the checkout snapshot record reviewer-created nested .git files, while continuing to handle the checkout's actual Git directory through _walk_git."**
  - `review_write_check._walk` no longer skips every entry named `.git`. `snapshot` passes the checkout's own top-level `.git` in `skip`, because `_walk_git` already walks it: the common and worktree Git directories and the pointer.
  - A nested checkout (a directory holding `.git`) still has its contents skipped as another repository's. Its `.git` marker is now recorded by the new `_git_marker`: a pointer file by `(mode, size, mtime, sha256)`, and a `.git` directory as present only, since that repository's own activity moves its times.
  - So a reviewer-created `.git` file, which would also turn its new directory into an apparent nested checkout, or a `git init`, is a write. The existing nested-worktree case (`test_a_commit_and_an_ignored_cache_count_as_writes_and_other_checkouts_do_not`) still passes: edits inside an existing nested checkout aren't counted.
  - `docs/orchestration-review.md` says so.
- **"Add a public-interface regression proving such a write is review_failure with no verdict filed."**
  - `test_review_delegate_cli_fails_a_reviewer_created_nested_git_and_files_no_verdict` in `tests/test_review_record_write_git.py`, through `specy-road review delegate`, has two cases: a reviewer that writes `work/hidden/.git` into a new directory, and one that runs `git init work/nested`.
  - Each is a `review_failure` naming the `.git` path, with no `REVIEW-opus.md`.
  - The fake harness's `write` step now creates missing parent directories.
- **Touch zones:** no new path; `specy_road/review_write_check.py` was added in round 7.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`): 178 passed.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: with the old global `.git` skip restored, both cases fail.

## Round 9 (gpt-5.6-sol-medium's block at `d5f3e39d`; commit `3453c6ad`)

Required change → what changed:

- **"Include stable file identity/link metadata in checkout, hand-off, Git-directory and linked-worktree .git-pointer snapshots."**
  - New `review_write_check._record(st, path, is_link)` returns `(st_dev, st_ino, st_nlink, st_mode, st_size, st_mtime_ns, sha256)`. All three places that record a file use it:
    - `_walk`: the checkout, the hand-off directory, and the common and worktree Git directories;
    - `_git_marker`: a nested checkout's `.git` pointer file;
    - the linked-worktree `.git` pointer in `_walk_git`.
  - A file swapped for a hard link to an identical copy elsewhere now differs by inode and link count.
  - `docs/orchestration-review.md` names identity among the compared fields.
- **"Add a public review-delegate regression proving an identical hard-link replacement is review_failure with no verdict filed."**
  - `test_review_delegate_cli_fails_an_identical_hard_link_replacement_and_files_no_verdict` in `tests/test_review_record_write_git.py`, through `specy-road review delegate`, covers the four areas: `src/a.py`, `work/reviews/M1.1/PACKET.md`, `.git/config`, and a linked worktree's `.git` with `--worktree`.
  - Each time the fake reviewer copies the file outside every snapshotted tree with `shutil.copy2`, unlinks it, and hard-links the copy back. The test confirms that mode, size, mtime and content are unchanged, that the inode is now the outside alias's with link count 2, and that the run is a `review_failure` naming the path with no `REVIEW-opus.md`.
  - The fake harness gained a `relink` step.
- **Touch zones:** no new path.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`): 182 passed.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: with `_record` back to `(mode, size, mtime, sha256)`, all four hard-link cases fail.

- **WIP merge `4983a4d5`** (M11.62: limits from the Claude transcript, background tasks off for reviewers, Codex overrides). Resolutions: `role_prompt.py` keeps this leaf's side, since the reviewer runners live in `role_prompt_cli`, and M11.62's `stream_and_capture` and `CLAUDE_REVIEWER_AVOID_ENV` imports moved there; `role_prompt_cli.py` drops its copy of `_stream_and_capture` for M11.62's `role_prompt_stream.stream_and_capture`, and `run_default_reviewer` puts `CLAUDE_REVIEWER_AVOID_ENV` on a Claude reviewer's `Launch.env`, which `review_record_write.run_logged` now applies under `reviewer_env`; `review_delegate.py` uses `reviewer_env(harness_env(os.environ, "reviewer", harness=h.harness))`; `tests/test_review_files.py` keeps the shared `fake_reviewer_run`, which now also patches `role_prompt_stream`. M11.62's new `tests/test_headless_limits_denials.py` imports `role_prompt_cli.run_default_reviewer` (this leaf's name for `run_bare_reviewer`), and its env assertion is unchanged. It expects exit 1, because its fake prints no verdict, so nothing is filed. The round 3–9 fixes are unchanged. `pytest -n 4` over the leaf's test files plus `tests/test_headless_limits_denials.py`: 190 passed. File limits OK; ruff clean.

## Round 10 (gpt-5.6-sol-medium's block at `06d90dba`)

Required change → what changed:

- **"Include stable change-time metadata (st_ctime_ns on the supported POSIX filesystems) in _record."**
  - `review_write_check._record` returns `(st_dev, st_ino, st_nlink, st_mode, st_size, st_mtime_ns, st_ctime_ns, sha256)`. Every snapshot entry goes through it: checkout, hand-off, Git directories, a nested `.git` marker, and a linked worktree's `.git` pointer.
  - The inode change time can't be set back by a process, so a rewrite with its mtime restored differs.
  - `docs/orchestration-review.md` names change time among the compared fields. The paragraph was reflowed to keep the file at 400 lines; nothing was removed except the word "same-length", which the broader sentence covers.
- **"Add a public review-delegate regression proving that rewriting a tracked file with identical bytes and restoring its mtime is review_failure with no verdict filed."**
  - `test_review_delegate_cli_fails_an_identical_rewrite_with_its_mtime_restored_and_files_no_verdict` in `tests/test_review_record_write_git.py`, through `specy-road review delegate`. The fake reviewer rewrites the tracked `src/a.py` with its own bytes and restores its atime/mtime, using the existing `keep_mtime` write step.
  - The test confirms device, inode, link count, mode, size, mtime and bytes are all unchanged and only `st_ctime_ns` moved. The run is a `review_failure` naming `src/a.py`, with no `REVIEW-opus.md`.
- **Touch zones:** no new path.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`, `tests/test_headless_limits_denials.py`): 191 passed. That includes the honest `git status` case, so change time adds no false failure there.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: without `st_ctime_ns` in `_record`, the new test fails.

## Not verified / open

- **No live harness runs.** The Claude and Codex flags come from the tracked captures, Cursor's from the fixture, and Antigravity's from the vendor page above (not installed; M8.6 records its runtime checks as not run).
  - Whether Codex strict structured output accepts this schema is unverified.
  - Whether `agy --output-format json` prints one line or many is unverified. Both work: the envelope is the output's final object, starting a line.
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
- `git index` entry in `snapshot` (round 4): Sol's A2 index finding.
- `_record` (round 9): file identity and links in every snapshot entry, for Sol's hard-link finding.
- `st_ctime_ns` in `_record` (round 10): Sol's identical-rewrite finding.
- `_git_marker`, and `_walk`'s top-level-only `.git` skip (round 8): Sol's nested-`.git` finding.
- `st_mode` in the snapshot tuples, and the `review_write_check` module split (round 7): Sol's chmod finding, and the file limit.
- `_walk_git` and `_walk`'s `skip` (round 6): Git metadata in the A2 snapshot. Its `resolved()` returns `None` when git can't answer.
- `_content` (round 3): the content digest in the A2 snapshot. Its `OSError` branch covers a file removed mid-walk or without read permission. `json_object`'s final-object rule (round 3): A3.
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
  - After the WIP merge: the shipped `agy-gemini-4-argon-high` profile's `access.cli` (already `--output-format json --print-timeout 60m`) gets only `--json-schema` and `--sandbox`.
