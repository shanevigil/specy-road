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

## Round 11 (gpt-5.6-sol-medium's block at `26f5cfb6`; commit `f0baf8c3`)

Required change → what changed:

- **"Include directory metadata in the checkout, hand-off, and Git-directory snapshots."**
  - `review_write_check._walk` now records every directory it enters, its base included, as `_dir_record`: `("dir", st_dev, st_ino, st_nlink, st_mode, st_mtime_ns, st_ctime_ns)`. Creating, renaming or deleting an entry moves the directory's mtime and ctime, so a file created and deleted again still leaves a write.
  - `written` shows the checkout root as `.`.
  - Two directories have their own metadata left out (`quiet`), while their files and subdirectories are still compared:
    - the hand-off directory root, where the run's own files appear during an honest run (the run record's `.tmp` and rename, `RUN-<model>.log`, Codex's `-o` file);
    - each Git directory holding an index (this checkout's, and the main checkout's when this one is linked), where a read-only `git status` creates and renames `index.lock`.
  - So a file created and deleted directly in the hand-off root or the Git directory root is still not seen. Its subdirectories (`history/`, `hooks/`, `refs/`, …) are.
  - `docs/orchestration-review.md` says so, within its 400 lines.
- **"Add a public review-delegate regression proving a reviewer-created, written, then deleted non-notes file is review_failure with no verdict filed."**
  - `test_review_delegate_cli_fails_a_created_written_and_deleted_file_and_files_no_verdict` in `tests/test_review_record_write_git.py`, through `specy-road review delegate`, has three cases: `src/`, `.git/hooks/`, and the hand-off `history/`. Each time the fake reviewer creates, writes and deletes `scratch.tmp`.
  - The test confirms nothing is left, that the run is a `review_failure` naming that directory, and that there is no `REVIEW-opus.md`.
  - The fake harness gained a `transient` step.
- **Tests adapted to the wider report:**
  - A write now also names the directories whose entries it changed (`wrote src, src/a.py;`). The earlier write tests use the new public helper `wrote_only(reason, path)` in `tests/review_delegate_helpers.py`: the path must be named, and every other named path must be one of its directories, so the check is no looser.
  - `test_a_commit_and_an_ignored_cache_count_as_writes_and_other_checkouts_do_not` now creates the hand-off directory before its first snapshot, as a run does.
- **Touch zones:** no new path.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`, `tests/test_headless_limits_denials.py`): 194 passed. That includes the honest `git status`, Codex `-o` and prompt-CLI runs, so there are no false failures from directory metadata.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: without the directory records, all three new cases fail.

## Round 12 (gpt-5.6-sol-medium's block at `aa94cafa`; commit `07dd812f`)

Required change → what changed:

- **"Make a create/write/delete directly in work/reviews/<ID>/ (and the analogous quiet Git-directory root) observable as review_failure without false-failing specy-road's own runtime files."**
  - **Git directory roots:** `reviewer_env` now sets `GIT_OPTIONAL_LOCKS=0`, so a read-only `git status` (or `diff`) takes no `index.lock` and doesn't refresh the index. `_walk_git` no longer makes the index-holding directories quiet; their own metadata is compared like any directory's.
  - **Hand-off root:** it stays quiet in the snapshot, because specy-road changes its entries between harness turns (the run record's `.tmp` and rename, the schema file). Instead the new `review_write_check.RootFence` records the root's `(mtime, ctime, link count)` around each harness turn:
    - in `review_delegate._turn`, after its log is open;
    - in `review_record_write.run_and_file` (`prompt --channel cli`), which now creates the log before the first snapshot.
  - A move during the turn is a write, unless one of `harness_files` appeared, went or was replaced in that turn: Codex's `OUTPUT-<model>.json` and the reviewer's `notes-<model>.md`.
  - `file_review(..., fenced=)` reports the root, e.g. `work/reviews/M1.1`.
  - `docs/orchestration-review.md` says so, within its 400 lines.
- **"Add a public review-delegate regression for the hand-off-root case."**
  - `test_review_delegate_cli_fails_a_created_written_and_deleted_file_and_files_no_verdict` (through `specy-road review delegate`) gains `work/reviews/M1.1`, the hand-off root, and `.git`, the Git root, beside `src`, `.git/hooks` and `work/reviews/M1.1/history`.
  - Each case is a `review_failure` naming that directory, with no `REVIEW-opus.md`.
- **No false failures from specy-road's own files, checked by the existing tests:**
  - the Codex `-o` end-to-end delegate, where Codex creates `OUTPUT-sol.json` in the root during its turn;
  - the reviewer's own notes in the root (`test_the_reviewers_own_notes_are_the_one_write_allowed`);
  - the prompt-CLI runs;
  - capacity retries, where the run record is saved between turns;
  - chores;
  - the stale-stat `git status`, renamed `test_a_read_only_git_status_with_a_stale_stat_cache_is_not_a_write`. It now asserts that the index file is left alone under the reviewer env, rather than rewritten, and that the review is recorded.
- **Tests adapted to the wider report:**
  - Index-only writes now also name `.git`, where Git takes `index.lock` to write the index. Those tests require exactly `{"git index", ".git"}`.
  - The commit test accepts `.git` itself among the commit's metadata.
  - `test_the_reviewer_process_writes_no_bytecode_or_pytest_cache` asserts `GIT_OPTIONAL_LOCKS=0`.
- **Remaining limit:** if, in the same turn, the harness's own `OUTPUT-<model>.json` or the reviewer's notes appear, go or are replaced in the hand-off root, that explains the root's move and would hide another file created and deleted there in that turn.
- **Touch zones:** no new path.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`, `tests/test_headless_limits_denials.py`): 196 passed.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: with the fence result dropped and the Git roots quiet again, the `work/reviews/M1.1` and `.git` cases fail.

## Round 13 (gpt-5.6-sol-medium's block at `a158edd9`; commit `1737539f`)

Required change → what changed:

- **"Make hand-off-root write detection observe a forbidden entry created/written/deleted in the same harness turn even when an allowed OUTPUT-<model>.json or notes-<model>.md transition also occurs."**
  - Round 12's `RootFence` treated the root's move as explained when an allowed file appeared, went or was replaced, and that hid a forbidden transient file in the same turn. The exception is gone.
  - The new `review_write_check.prepare_harness_files(reviews, model)` creates both allowed files before the first snapshot: `OUTPUT-<model>.json` emptied, replacing the old `unlink` so a stale answer still never stands in, and `notes-<model>.md` kept if present. It runs in `review_delegate.delegate` and in `review_record_write.run_and_file` (`prompt --channel cli`).
  - Written in place during the turn, they change no entry of the root. `RootFence(root)` now compares the root's `(mtime, ctime, link count)` strictly before and after each turn: any move is a write, whatever else the turn wrote.
  - `final_output` already treats an empty `-o` file as absent.
  - Consequence: a harness that replaces its answer or notes by renaming a temporary file over them is reported as a write. Codex's `-o` and Claude's file tools are believed to write in place; that is not verified against live harnesses (see Not verified).
  - `docs/orchestration-review.md` says so, within its 400 lines.
- **"Add a public review-delegate or prompt --channel cli regression proving review_failure with no verdict filed for that combined case."**
  - `test_review_delegate_cli_fails_a_transient_hand_off_file_beside_an_allowed_write` in `tests/test_review_record_write_git.py`, through `specy-road review delegate`, is parametrized over `notes-opus.md` and `OUTPUT-opus.json`. In one harness turn the fake reviewer writes the allowed file (draft notes, or the verdict JSON as Codex's `-o` answer) and creates, writes and deletes `scratch.tmp` in the hand-off root.
  - The test confirms the allowed file holds what was written and the scratch file is gone, that the run is a `review_failure` naming `work/reviews/M1.1`, and that there is no `REVIEW-opus.md`.
  - The companion `test_an_allowed_answer_or_notes_write_alone_is_still_filed` shows either allowed write on its own is still recorded. The existing notes-only and Codex `-o` end-to-end tests pass unchanged.
- **Touch zones:** no new path.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`, `tests/test_headless_limits_denials.py`): 200 passed.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: with the three production files back at `a158edd9`, both combined cases fail and the allowed-only cases pass.

## Round 14 (gpt-5.6-sol-medium's block at `8663f3f0`; commit `7d68f9b3`)

Required change → what changed:

- **"Reject malformed outer JSON instead of accepting a nested object as the final verdict."**
  - `review_record_write.json_object` keeps its rules: the final complete object must start a line, and no `{` may open after it. It now adds a third: the final object must be at top level.
  - The new `_open_braces(value, spans)` counts the braces outside the complete objects found before it (`{` adds one, `}` takes one away but never below none). If an object is still open where the final one starts, the output is a rerun request.
  - So an unterminated outer object followed by a complete nested verdict is never filed. Balanced prose (`use {x} here`) and a stray `}` still leave the answer at top level.
  - `docs/orchestration-review.md`'s rerun-request bullet says so, within its 400 lines.
- **"Add a public review-delegate regression using an unterminated outer object followed on a new line by a schema-valid nested verdict; require outcome rerun and no REVIEW file."**
  - `test_a_verdict_nested_in_an_unterminated_outer_object_is_a_rerun_request` in `tests/test_review_record_write.py` goes through `specy-road review delegate --json`. The fake reviewer prints `{"wrapper": "draft", "review":` and then, on the next line, the full verdict, which the test first confirms is valid against `output_schema()`.
  - The test confirms exit 1, `state: incomplete`, `outcome: rerun` with reason `rerun requested: the reviewer's output ends with no JSON object`, and no `REVIEW-opus.md`.
  - The `json_object` unit test gained the nested case (`None`) and the balanced-prose-plus-stray-brace case (still the answer).
- **Touch zones:** no new path.
- **Verification:**
  - `pytest -n 4` over the leaf's test files (`tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`, `tests/test_headless_limits_denials.py`): 201 passed.
  - File limits OK; ruff clean; private imports 0 new.
  - Red/green: without the `_open_braces` condition, the new regression and the unit test fail.

## WIP merge `2012edce` (M11.75 reviewer probe rules, M11.77; commit `0d76d22f`)

The leaf had been approved at `b8b7c294` and finished (`7ef16419`), but WIP moved and the branch no longer merged. Sol's old block at `322e41fd` was answered in round 2 and is not reopened here.

- **`role_prompt.py`** (the only code conflict): `reviewer_lines` now returns the preamble, `REMOVED_TEXT_LINES`, M11.75's `PROBE_RULES_LINES`, `LAUNCH_MODE_LINES`, verify and lesson lines, the escalation note, then this leaf's `READ_BACK_LINES`/`PASTED_LINES`. Both sides' lines are in the prompt and in the same order they had.
- **Bookkeeping:** `sr/roadmap/registry.yaml` and `sr/roadmap-context.md` are WIP's versions. Then the finish is re-applied: the M8.3 row is removed (it was the only entry, so `entries: []`, as in the project template), `M8.json` keeps M8.3 `Complete`, and `specy-road export` and `specy-road digest` were regenerated from `sr/`. The summary moves back from `work/done/` to `work/`, since the review packet reads it there; finish moves it again.
- **`tests/test_run_record_no_false_failure.py` (M11.77): rewritten**, not deleted. Its old reviewer copied a hand-written `REVIEW-opus.md` into the hand-off directory, which M8.3 classes as a write violation. It also imported `_steps`, `_files_record`, `_roster` and `_repo`, which this branch replaced with the public `tests/review_delegate_helpers.py`. The four tests keep M11.77's intent on the structured-output path, with a `generic` entry (`GENERIC` from `tests/test_review_record_write.py`) whose `channels.cli` prints its final JSON:
  - `prompt --channel cli` with a filed verdict: exit 0, `REVIEW-gem.md` filed, the run `complete` with no reason, no events, attempt error `None`, and no "no review record was filed" in `RUN-gem.json`;
  - `prompt --channel cli` with no JSON: non-zero, nothing filed, the run `incomplete` with an attempt error and a `reviewer-failure` event (the old test pinned the "no review record was filed" text here; a run without JSON is now a rerun request, so only the failure is pinned);
  - a verdict for an older commit: not filed, the run `incomplete`;
  - `review delegate` with a filed verdict: `recorded`, and `RUN-gem.json` has no error.
- **File limit:** the merge took `docs/orchestration-review.md` to 433 lines (this leaf +63 and WIP +33 over the merge base; the cap is 400). The "Reviewer output and the read-only check" body moved unchanged to the new **`docs/orchestration-reviewer-output.md`** (`0d76d22f`), and a short section with a link stays in its place. The two "(next section)" pointers above it now link there. Nothing else was removed. `docs/orchestration-reviewer-output.md` needs adding to the touch zones.
- **Verification:**
  - `pytest -q -n 4 -p no:cacheprovider` over `tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_headless_limits_denials.py`, `tests/test_models_and_prompt.py`, `tests/test_review_record_rules.py`, `tests/test_run_record_no_false_failure.py` and every test module that imports `role_prompt` (38 files): 530 passed. There is no `tests/test_reviewer_probe_rules.py`; M11.75's tests are `tests/test_review_record_rules.py`, which is included.
  - `tests/test_doc_links.py` and `tests/test_review_round6_docs.py` after the doc move: 15 passed.
  - `specy-road file-limits`: OK after the move. `specy-road validate` from `sr/`: OK. `export --check` and `digest --check`: OK. `ruff` clean on the changed files; private imports 0 new.
  - The merge commit itself was made with `git commit -F` on the staged merge result, because git refuses `--only` during a merge. Nothing outside the merge was staged.

## Fix round: Git metadata scope (coordinator, live failure at `f01824de`; commit `9b01c380`)

- **Failure:** in the shared toolkit repository every review was filed as `review_failure` for `.git`, `.git/config` and `.git/logs/refs/heads/<other branches>`, all written by other processes (an IDE's git polling, other worktrees committing). `_walk_git` walked the whole common Git directory, its own directory metadata included, and `git refs` compared every ref.
- **Fix:** `review_write_check._walk_git` now records only the checkout's own `HEAD` and `logs/HEAD` (from `--git-dir`), each reviewed branch's loose ref, reflog and `packed-refs` line, the shared `hooks/` and a linked worktree's `.git` pointer. `git refs` compares `HEAD` and the reviewed branch. The new `branches` names the reviewed branch: the one checked out, plus the local branch `ref` names (`review delegate` passes `t.ref`; `prompt --channel cli` passes `--ref`), so a reviewer on a detached quiet checkout that moves the leaf branch is still caught. Not recorded any more: the common directory's own metadata, `config`, `objects`, `FETCH_HEAD`, `ORIG_HEAD`, other branches' refs and reflogs, and other worktrees' directories. The worktree walk and its directory-metadata rule (Sol, `26f5cfb6`) are unchanged, and the index is still compared by its entries.
- **Kept beyond the coordinator's list:** `hooks/`. A hook is code every checkout runs, other sessions rarely write it, and Sol's round-6 hook tests still pass. Dropping it is one line in `_walk_git` if the coordinator wants the narrower list.
- **Tests changed to the new scope** (the coordinator asked for this change in behaviour):
  - the index-only writes now report `{"git index"}` only, not also `.git`, since the Git directory root is no longer compared;
  - the chmod and hard-link cases' `git-dir` target is `.git/HEAD` instead of `.git/config`;
  - the transient-file case drops `where=".git"`, the Git directory root; `.git/hooks` stays;
  - `test_a_commit_and_an_ignored_cache_count_as_writes_and_other_checkouts_do_not` now requires the reviewed branch's reflog among the writes, within `HEAD`'s reflog and the branch's ref and reflog, instead of any `.git/` path.
- **Tests added:**
  - `test_only_a_commit_on_the_reviewed_branch_fails_the_review_not_other_sessions_git_activity` covers two cases. In `other-worktree`, during the run another worktree commits on branch `other`, `config` is rewritten and an `index.lock` is created and removed in the common root; the review is `recorded`. In `reviewer`, a reviewer commit on the reviewed branch is a `review_failure` naming `git refs`, `.git/logs/HEAD` and the branch's reflog. Red/green: with the old `review_write_check.py`, the `other-worktree` case fails.
  - `test_the_reviewed_branch_is_checked_when_the_reviewer_runs_on_a_detached_checkout`: an `update-ref` of the leaf branch from a detached worktree is a write.
- **Docs:** `docs/orchestration-reviewer-output.md` states the scope. The module docstrings of `review_write_check` and `review_record_write` match.
- **Verification:**
  - `pytest -n 4 -p no:cacheprovider` over `tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_review_file_case.py`, `tests/test_chore_mode.py`, `tests/test_headless_limits_denials.py`, `tests/test_orchestration_guard_hooks.py`, `tests/test_roster_harness_model.py` and `tests/test_run_record_no_false_failure.py`: 173 passed. These are every test module that imports `review_record_write`, which is the only importer of `review_write_check`, or `review_delegate`.
  - `specy-road file-limits` OK; `ruff` clean on the changed files.

## Fix round: strict Codex output schema (coordinator, live failure at `0a00c503`)

Codex 0.166 sends `--output-schema` in OpenAI strict mode, and the API refused the schema file before any review ("'schema.required' is required to include every key in properties. Missing 'toolkit_version'").

- `write_schema(root, reviews)` now writes `strict_schema(ids)` for the leaf the hand-off directory is named for: optional root fields become required as `anyOf [field, null]`, and `acceptance` becomes an object whose properties are exactly the leaf's acceptance ids, all required, `additionalProperties: false`. Probed against the live API (gpt-6.1-sol): `minLength`, `pattern`, `$ref`/`$defs`, `$ref` with a sibling `description`, `anyOf` with null, type arrays, root `$schema`/`title` and an empty-properties object are accepted; `propertyNames` is refused ("not permitted when strict is true"), which the strict `acceptance` no longer uses.
- `file_review` drops `null` optional fields (`drop_nulls`) before validating against `output_schema()`, unchanged; a `null` required field is still a rerun request. The prompt says an optional field may be left out or `null`.
- Claude Code (`--json-schema`) and `agy` read the same file; they get the strict form too, since anything it admits is, less its nulls, an answer `output_schema()` accepts. Not run live for those harnesses in this round.
- Live smoke: the strict schema written for M8.3 (A1..A5) with `codex exec --skip-git-repo-check --json -m gpt-6.1-sol -c model_reasoning_effort=low -c sandbox_mode=read-only -c approval_policy=never --output-schema review-output.schema.json -o OUTPUT-sol.json -` returned a strict answer with nulls; after `drop_nulls` it validated against `output_schema()` and `review_semantic_errors` for A1..A5 with no errors (`--skip-git-repo-check` only because the smoke ran outside a repository).
- Tests: the Codex `review delegate` test now checks the schema file the fake `codex` received against `strict_problems` and pins its acceptance properties to `["A1", "A2"]`; new `test_an_answer_with_null_optional_fields_files_the_same_record_as_one_without`. `FAKE_CODEX` moved to `tests/review_delegate_helpers.py` with `strict_problems`, for the file limit.

## Fix round 2 (Grok's block at `5919a0cc`: A2, A3)

- A3: `_open_braces` counts `[` and `]` with `{` and `}`, so a verdict inside an array, closed (`[\n<verdict>\n]`) or not (`[\n<verdict>`), is not at top level and `json_object` returns `None`: a rerun request. Balanced prose brackets (`[the docs](x)`) still leave the final object at top level; the earlier cases (unterminated objects, trailing prose, a later truncated object) are unchanged.
- A2, schema file: `review-output.schema.json` is no longer in `runtime_files`, and it is written before the first snapshot on every path. `review delegate` writes it under the run lock after `prepare_harness_files`; its `_Harness.launch` now only passes the path, so a retry turn no longer writes it mid-run. The `prompt --channel cli` reviewer paths (`run_default_reviewer`, `run_custom_reviewer`) write it before `run_and_file` takes its snapshot, as before; Claude Code's launch reads the file to inline it, so that write stays before the lock. `write_schema` therefore leaves the file alone when it already holds the same text, so a run refused by the lock never changes the running one's file.
- A2, run record: `RUN-<model>.json` stays exempt from the snapshot comparison because `review delegate` saves it (temporary file renamed over it) after every turn, inside the snapshot window. It is now guarded per turn instead: `RootFence(root, model)` also keeps the run record's identity, times and content, and specy-road writes it only between turns (`review delegate`) or before and after the run (`prompt --channel cli`), so a change during a turn makes the run a review failure, reported as the hand-off directory. Without the fence the tamper was erased by the next save under `review delegate`, but under `prompt --channel cli` `close_reviewer_cli_run` re-reads the file (its `log` field says where the transcript is written).
- Tests: `test_malformed_output_is_a_rerun_request_never_a_verdict` gains both array cases through `review delegate`; `test_the_final_complete_json_object_of_a_message_is_the_answer` gains them plus balanced prose brackets; `test_a_run_that_writes_anything_but_its_notes_is_a_review_failure_and_files_nothing` gains the schema-file and run-record overwrites; `test_one_leafs_reviewer_runs_take_turns` checks that a `prompt --channel cli` run refused by the lock leaves the schema file's mtime and ctime as they were. `FAKE_AGY` moved to `tests/review_delegate_helpers.py`, for the file limit.

## Merge with WIP `458dca91` (pre-release-checks fixes, git < 2.48 test setup, clone-gate helpers, roster)

- `specy_road/bundled_scripts/role_prompt.py`: `reviewer_lines` takes both M8.3's `read_back` and WIP's `config`; the preamble gets WIP's `signed=` (`--sign-key` under `policy.signed_reviews`) and still ends with M8.3's read-back or pasted lines; `build_prompt` passes both.
- `specy_road/review_delegate.py`: imports take WIP's `save_run` (renamed from `_save`), `turn_capacity_error`, `WorkerError` and its `capacity_error`/`gate_policy_summary`/`valid_record` re-export, plus M8.3's `harness_error_line` and `reviewer_cli`. `delegate` keeps M8.3's lock, schema write, snapshots, `file_review` and `_close`, with `save_run` for each save.
- `tests/test_review_delegate.py`: WIP's copies of `FAKE`, `_roster`, `_repo`, `_steps`, `_calls` and `_files_record` were dropped, since M8.3 moved them to `tests/review_delegate_helpers.py`. WIP's `say` step was added to that `FAKE`. WIP's two new tests (`test_an_unsafe_recorded_session_id_is_refused_without_a_traceback`, `test_review_text_that_mentions_capacity_is_not_a_capacity_error`) now use `delegate_repo`, `set_steps` and `fake_calls`, with their assertions unchanged.
- Interaction fix in `review_record_write.run_and_file`: WIP's `turn_capacity_error` reads a capacity error from the last plain output line only. M8.3 appended its rerun line after a failed harness's output, which hid the usage limit (`test_prompt_cli_channel_records_usage_limit_and_shows_it_on_the_gate_line`). After a non-zero exit, a rerun request is no longer appended to the transcript. A review failure, or a rerun after a clean exit, still goes last. That branch is reached by the test named above.
- No conflict in `sr/roadmap/registry.yaml`, `sr/roadmap.md` or `sr/roadmap-context.md`; `export --check` and `digest --check` pass with the branch's code.

## Fix round 3 (Sol's block at `3e5894b5`: F1-F4; Grok approved)

- F1 (A2, transcript): `review_write_check.RunLog` keeps a SHA-256 of what `RUN-<model>.log` held when the run began, plus every byte specy-road appends through `RunLog.write`. Both turn loops write the harness's output through it: `review_record_write.run_logged` and `review_delegate._turn`. The log is opened with `newline=""`, so the bytes written are the bytes hashed. `file_review(log=...)` names the log as a write when `RunLog.changed()` is true: the harness rewrote, truncated, removed or appended to it. The log stays out of the snapshot comparison, because specy-road appends to it during the turn.
- F2 (A3, retries): `review_delegate._attempts` calls `prepare_harness_files` before every attempt, not once per run, so `OUTPUT-<model>.json` is empty when each turn starts. A resumed attempt (a Codex resume writes no `-o` file) is therefore judged by its own final message.
- F3 (A1, signed reviews): `review delegate --sign-key PATH` and `prompt --role reviewer --channel cli --sign-key PATH` pass the key through `delegate(sign_key=)`, `run_cli_channel`, `run_default_reviewer`, `run_custom_reviewer` and `run_and_file` to `file_review` and `_review_record`, which runs `review record --sign-key`. Signature verification is unchanged. Without a key under `policy.signed_reviews`, `review record` refuses as before (its existing message), and the run is a rerun request.
- F4 (lock order): the leaf's run lock is now taken before the run writes any file. `delegate` takes it before `_start` (prompt and packets), `_preflight`, the prompt files and the run record. `prompt --role reviewer --channel cli` takes it in `main`, before `build_prompt`, the prompt file and `open_reviewer_cli_run`; the body of `main` moved to `_run`. `run_and_file` no longer takes the lock itself; its caller holds it. The pre-lock `OUTPUT-<model>.json` unlinks in `run_default_reviewer` and `run_custom_reviewer` are gone; `prepare_harness_files` empties the answer under the lock. Because every schema write is now under the lock, `write_schema` is back to a plain write: fix round 2's unchanged-text branch is removed.
- Tests:
  - `test_a_run_that_writes_anything_but_its_notes_is_a_review_failure_and_files_nothing` gains the `RUN-opus.log` overwrite.
  - New `test_a_retry_never_files_an_earlier_attempts_answer`: the first attempt leaves a valid `OUTPUT-opus.json` and hits capacity; the resumed attempt prints no verdict; the result is a rerun with no record.
  - `test_one_leafs_reviewer_runs_take_turns` moved from `tests/test_review_record_write.py` to `tests/test_review_delegate.py` (file limit) and extended. A refused `review delegate` and a refused `prompt --channel cli` launch leave every file under `work/` (prompts, run record, answer, schema, record) with its bytes and mtime, and create none.
  - New `test_a_launched_reviewers_verdict_is_filed_signed_with_the_callers_key` in `tests/test_review_signing.py`. With `signed_reviews` on, no key gives a rerun with the existing refusal. `review delegate --sign-key` and `prompt --channel cli --sign-key` each file a record the gate verifies.
  - The three regressions for F1, F2 and F4 fail on `3e5894b5`.
  - `fake_reviewer_run`'s `run_logged` fake writes through the `RunLog`.

## Fix round 4 (Sol's block at `08da7813`: F1, F2; Grok approved)

- F1 (A1, quoted `agy` path): `reviewer_cli` inserts the Antigravity flags where `worker_adapter_base._program_end` says the first shell word ends. It reads the word as `shlex.split` does, so whitespace inside single or double quotes, or after a backslash, stays in the program path. The old `\s*\S+` match split `"tools with spaces/agy"` inside its quotes.
- F2 (A3, later array): `json_object` also returns `None` when `review_record_write._later_array` finds a line after the final object that opens a JSON array. That covers any `[` that starts with a JSON value (`[1,`, `[1,,2]`, `[]`) or never closes (`[`, `[broken`), as a later `{` already did for objects. A closed bracket of prose after the answer (`[INFO] done`, `[the docs](x)`) is still permitted, like other trailing text. `_open_braces`' depth count moved into `_depth`, which both use. `docs/orchestration-reviewer-output.md` states the rule.
- Tests:
  - `test_malformed_output_is_a_rerun_request_never_a_verdict` gains five inputs: a valid verdict followed by `\n[`, `\n[1,`, `\n[broken`, `\n[1,,2]` and ` [`. Each is a rerun with no REVIEW file.
  - `test_the_final_complete_json_object_of_a_message_is_the_answer` gains one assertion: prose brackets after the answer still leave the answer.
  - `test_an_antigravity_review_delegate_passes_json_schema_and_files_structured_output` is parametrized over the program word: on PATH, double-quoted, single-quoted and backslash-escaped. The last three use a fake `agy` in a directory with spaces.
  - The new cases fail on `08da7813`, except the prose guard, which passes there too.

## Fix round 5 (Sol's block at `27d39730`: F1-F3; commit `bc0236ba`)

Required change → what changed:

- **F1 (A2, run lock).** `.review-run.lock` is no longer in `review_write_check.runtime_files`. Both launch paths create and lock it before their first snapshot and never write it, so the snapshot now compares it like any hand-off file (identity, mode, size, times, content). An in-place overwrite is a `review_failure` naming the lock, and nothing is filed. `docs/orchestration-reviewer-output.md` and the `runtime_files` docstring say so.
- **F2 (A2/A3, prompt-CLI closure).** `run_and_file` appends its `Outcome` to an optional `filed` list, threaded through `run_cli_channel`, `run_default_reviewer` and `run_custom_reviewer`. After `close_reviewer_cli_run` (outside the zones, unchanged), `role_prompt._run` calls the new `role_prompt_cli.close_unfiled_cli_run`. For a review failure or rerun request, a run that `close_run` marked complete because an older record of the commit was valid becomes incomplete, with `outcome`, reason and a reviewer-failure event, through the new `review_record_write.close_unfiled`. A run that is already incomplete has its event already, so it only gets `outcome`. `close_unfiled` is the failure branch of `review_delegate._close`, moved so both CLIs close a failed filing the same way.
- **F3 (A3, empty terminal answer).** `final_message` now returns `""`, not `None`, for an answer event with no valid answer: Codex's `agent_message` with a non-string `text`, Claude's `result` with neither `structured_output` nor string `result`, and Cursor's error or text-less `result`. `final_output` keeps the last non-`None` value, so that `""` replaces an earlier answer and `file_review` makes it a rerun request. Other lines still return `None`. The base docstring states the contract.
- **Tests:** new `tests/test_review_record_write_closure.py`, all through public entry points:
  - `review delegate --json` with a reviewer that overwrites `.review-run.lock` in place → exit 1, `review_failure` naming only the lock, no record.
  - `prompt --channel cli` after `delegate` filed a valid record of the same commit, parametrized over a rerun (`not a verdict`) and a review failure (a write to `src/a.py`) → exit 1, RUN `incomplete` with matching `outcome`, reason and last reviewer-failure event; the older record's bytes unchanged.
  - `delegate(resume=True)` on a fake `codex` (`exec resume`, no `-o`) that prints a valid verdict `agent_message` and then one with `text: null` → `rerun`, no record. The control without the null event files the verdict.
- **Verification:**
  - `pytest -q -n 4 -p no:cacheprovider` over `tests/test_review_record_write.py`, `tests/test_review_record_write_git.py`, `tests/test_review_record_write_closure.py`, `tests/test_review_delegate.py`, `tests/test_review_files.py`, `tests/test_worker_adapters.py`, `tests/test_models_and_prompt.py`, `tests/test_prerelease_review.py`, `tests/test_review_rca.py`, `tests/test_role_prompt_file_limits.py`, `tests/test_resumed_delta_review.py`, `tests/test_chore_mode.py`, `tests/test_review_signing.py`, `tests/test_run_record_no_false_failure.py`, `tests/test_worker_turn_check.py` and `tests/test_headless_limits_denials.py`: 252 passed. Another 10 files that import `role_prompt` or the adapters (rework, do-next prompt, ready, lessons, verify_cmd, hardening, guard hooks, harness facts, lean rules, worker cli): 183 passed.
  - File limits OK (`role_prompt.py` 398 lines); ruff clean; private imports 0 new.
  - Red/green: with this round's production changes reverted, 4 of the 5 new cases fail (the lock, both prompt-CLI cases, the null-text resume); the control passes either way.
- **Touch zones:** no new path. `reviewer_run_failure.py` (`close_reviewer_cli_run`, `close_run`) is outside the zones and unchanged; the closure is corrected after it, from `role_prompt.py`.

## Rework (reopened 2026-11-04): design pass

The maintainer reopened M8.3 after five Sol rounds, each of which found a new input class. The coordinator's RCA: the answer extractor and the write check were each built from special cases. This pass answers Sol's F1–F3 on `27d39730` by replacing both mechanisms, and the run closure, with one rule each. Commits: `052823ab` merges WIP; `73b0fea1` is the design pass.

### WIP merge (`052823ab`)

`git fetch origin && git merge origin/WIP/improvements-0-3-1`. There were three conflicts:
- `specy_road/worker_adapter_claude.py`: an import conflict only. WIP added `claude_projects_dir`; this leaf added `REVIEWER_DISALLOWED`. Both imports are kept, and the merged file equals WIP's plus this leaf's reviewer changes.
- `sr/roadmap-context.md`, `sr/roadmap/registry.yaml`: these are WIP-maintained bookkeeping (the generated digest and the claim registry), so they were taken from WIP.

The 12 adapter, review and prompt test files then gave 218 passed.

### 1. One final-answer extractor (F3 and past A3 rounds)

- **Adapters map, they don't decide.** `Adapter.final_message(line)` is gone. Each adapter implements `Adapter.messages(lines, output) -> list[Message] | None` in `worker_adapter_base`. A `Message` is `(body, terminal)`, where `body` is a dict (structured output the harness validated), text, or `None` (no answer). `None` means the output has none of the harness's events: a `generic` harness or a plain-text wrapper, whose whole output is one terminal message.
  - **Claude** (`CLAUDE_EVENTS`): `assistant` → intermediate. `result` → terminal: `structured_output` if a dict, else `result`; `None` if `is_error`.
  - **Codex** (`CODEX_EVENTS`): `agent_message` → intermediate. `turn.completed` makes the turn's last message terminal, or adds a terminal `None` if the turn had none. The body is the `-o` file when Codex wrote one, else that message's text. `turn.failed` → terminal `None`.
  - **Cursor** (`CURSOR_EVENTS`): like Claude, without structured output.
  - **Antigravity**: a `generic` entry, so its whole output is the message. The envelope's `structured_output` is unwrapped by the extractor, unambiguously: the output schema forbids that key.
- **One function decides.** That function is `specy_road/review_answer.final_answer(adapter, text, output) -> dict | Rerun` (new module). Rules:
  - only the last message counts, and it must be terminal;
  - `None`, empty text, or text that does not end with one top-level JSON object (`text_object`) is a rerun request;
  - a non-object is a rerun request;
  - so is an object that fails `output_schema()` once its nulls are dropped;
  - no earlier message or earlier attempt is ever read: `run_text` returns only the last attempt's output, and Codex's `-o` file is removed before every attempt.
- **`text_object` replaces `json_object`, `_later_array`, `_depth` and `_open_braces`.** It has one rule with three conditions: the object starts a line, it runs to the end of the text (only a closing fence may follow), and no `{` or `[` before it is left open. A later object, a later array, a trailer and an object nested in malformed JSON all fail the "runs to the end" condition, not a dedicated check.
- `file_review` now takes `answer` (`dict | Rerun`), not raw output. The schema check moved into the extractor.

**Shape table** (`final_answer` through each real adapter; all in `tests/test_review_answer.py::test_the_last_terminal_message_is_the_answer_or_a_rerun`, ids `harness:shape`):

| Harness | Shape | Result | Test |
|---|---|---|---|
| Claude | valid (`structured_output`) | answer | `[claude-code:valid structured]` |
| Claude | valid (text `result`, prose before) | answer | `[claude-code:valid text]` |
| Claude | null `result` | rerun: no answer | `[claude-code:null]` |
| Claude | error result (`is_error`, valid text) | rerun: no answer | `[claude-code:error result]` |
| Claude | empty | rerun: empty | `[claude-code:empty]` |
| Claude | non-JSON | rerun: no JSON object | `[claude-code:non-JSON]` |
| Claude | schema-invalid | rerun: schema | `[claude-code:schema-invalid]` |
| Claude | multiple terminals: valid, then null | rerun: no answer | `[claude-code:multiple: valid then null]` |
| Claude | multiple terminals: null, then valid | answer (the last) | `[claude-code:multiple: null then valid]` |
| Claude | truncated (init, assistant, no `result`) | rerun: no final message | `[claude-code:truncated]` |
| Claude | plain-text wrapper | answer | `[claude-code:plain-text wrapper]` |
| Codex | valid (`-o` file at `turn.completed`) | answer | `[codex:valid -o file]` |
| Codex | valid (resume, last `agent_message`) | answer | `[codex:valid message (resume: no -o)]`; end to end `tests/test_review_record_write_closure.py::test_a_codex_resume_whose_last_answer_event_has_no_text_is_a_rerun[False]` |
| Codex | null `text` | rerun: no answer | `[codex:null]`; end to end `…closure.py::test_a_codex_resume_whose_last_answer_event_has_no_text_is_a_rerun[True]` (Sol F3) |
| Codex | no message in the turn | rerun: no answer | `[codex:no message in the turn]` |
| Codex | `turn.failed` | rerun: no answer | `[codex:turn failed]` |
| Codex | empty | rerun: empty | `[codex:empty]` |
| Codex | empty `-o` file | judged by the message | `[codex:empty -o file falls to the message]` |
| Codex | non-JSON | rerun: no JSON object | `[codex:non-JSON]` |
| Codex | schema-invalid | rerun: schema | `[codex:schema-invalid]` |
| Codex | multiple: valid, then null message | rerun: no answer | `[codex:multiple: valid then null message]` |
| Codex | multiple terminals: valid turn, then null turn | rerun: no answer | `[codex:multiple: valid turn then null turn]` |
| Codex | truncated after a valid message | rerun: no final message | `[codex:truncated after a valid message]`; `tests/test_review_answer.py::test_the_answer_file_counts_only_for_a_turn_that_completed` |
| Codex | a failed fresh turn's `-o`, then a resumed turn | rerun (stale `-o` never read) | `…closure.py::test_a_retried_codex_turn_never_files_the_failed_fresh_turns_answer_file` |
| Codex | plain-text wrapper | answer | `[codex:plain-text wrapper]` |
| Cursor | valid | answer | `[cursor:valid]` |
| Cursor | null | rerun: no answer | `[cursor:null]` |
| Cursor | error result | rerun: no answer | `[cursor:error result]` |
| Cursor | empty | rerun: empty | `[cursor:empty]` |
| Cursor | non-JSON | rerun: no JSON object | `[cursor:non-JSON]` |
| Cursor | schema-invalid | rerun: schema | `[cursor:schema-invalid]` |
| Cursor | multiple terminals: valid, then error | rerun: no answer | `[cursor:multiple: valid then error]` |
| Cursor | truncated | rerun: no final message | `[cursor:truncated]` |
| Cursor | plain-text wrapper | answer | `[cursor:plain-text wrapper]` |
| Antigravity | valid envelope (pretty-printed) | answer | `[generic:antigravity valid]` |
| Antigravity | null `structured_output` | rerun: no answer | `[generic:antigravity null]` |
| Antigravity | empty output | rerun: empty | `[generic:antigravity empty output]` |
| Antigravity | non-JSON | rerun: no JSON object | `[generic:antigravity non-JSON]` |
| Antigravity | schema-invalid | rerun: schema | `[generic:antigravity schema-invalid]` |
| Antigravity | multiple: valid, then null envelope | rerun: no answer | `[generic:antigravity: valid, then a null envelope]` |
| Antigravity | multiple: valid, then truncated envelope | rerun: no JSON object | `[generic:antigravity: valid, then a truncated envelope]` |
| Antigravity | truncated | rerun: no JSON object | `[generic:antigravity truncated]` |

The text rule's own cases (fence, prose before, CRLF, trailer, later object or array, nesting) are in `tests/test_review_answer.py::test_a_messages_text_must_end_with_one_top_level_json_object`.

### 2. A write check with no exemptions (F1)

- **Removed:** `runtime_files` (the exemption list), `harness_files`/`prepare_harness_files`, `RootFence`, the `quiet` set for the hand-off directory, `Snapshot.exempt`, `OUTPUT_PREFIX`/`output_path`, and the notes allowance. `.review-run.lock` stays non-exempt, as in round 5.
- **One rule:** every snapshotted path is compared. The files specy-road itself writes in the tree during the run are `OwnFile`s:
  - each exists before the first snapshot and is written in place, so no directory entry moves;
  - `written(before, after, own)` compares each one's identity and mode (device, inode, link count, mode) like any file, and its content by `OwnFile.changed()`: SHA-256 of what it held at the start plus every byte specy-road wrote since;
  - `OwnFile.rewrite` first checks that nothing else changed the file, so a tamper that specy-road's own overwrite would erase is still kept (`tampered`).

**What the check snapshots, and how:**

| Path | How |
|---|---|
| Every file of the checkout the reviewer runs in, ignored and `work/` files included (the hand-off directory too when inside it) | entry `(dev, ino, nlink, mode, size, mtime_ns, ctime_ns, sha256)` (`_record`) |
| Every directory of the checkout, the checkout and hand-off root included | `(dev, ino, nlink, mode, mtime_ns, ctime_ns)` (`_dir_record`): a file created, renamed or deleted there is a write |
| The hand-off directory, when outside the checkout (reviewer in a linked worktree) | the same, walked separately |
| A nested checkout's `.git` marker | a pointer file as `_record`; a directory as present only (its contents are another repository's) |
| Own Git dir `HEAD`, `logs/HEAD`; reviewed branch's loose ref, reflog, `packed-refs` line; shared `hooks/` (walked); a linked worktree's `.git` pointer | `_record` (packed-refs: its matching lines) |
| `HEAD` and the reviewed branch's commit | `git refs`: resolved ids |
| The Git index | `git index`: SHA-256 of `ls-files --stage -v -z` (entries, not bytes) |
| `RUN-<model>.log` (both CLIs) and `RUN-<model>.json` (`review delegate`) | identity and mode as above; content by `OwnFile` (specy-road's expected hash) |

**What specy-road writes during a run, and where:**

| File | When | Where | Check |
|---|---|---|---|
| `.review-run.lock` | created and locked before the first snapshot; never written | hand-off directory | compared like any file (F1) |
| `review-output.schema.json` | before the first snapshot | hand-off directory | compared like any file |
| prompt files `work/prompt-*.md` | before the first snapshot | checkout | compared like any file |
| `RUN-<model>.json` | created before the first snapshot; `review delegate` rewrites it in place after each attempt (was tmp + rename); the final update comes after the last snapshot | hand-off directory | `OwnFile` |
| `RUN-<model>.log` | created (`touch`) before the first snapshot; appended to during each turn | hand-off directory | `OwnFile` |
| Codex's `-o` answer | during the fresh turn, by the harness | private `tempfile.TemporaryDirectory` (`answer_scratch`), removed with the run | outside the tree; removed before every attempt; read only at `turn.completed` |
| `notes-<model>.md`, `REVIEW-<model>.md`, `history/` | after the last snapshot (`file_review`) | hand-off directory | after the check |
| prompt-CLI log rewrite and the final run-record update | after the last snapshot (`close_cli_review_run`, `delegate`'s `finally`) | hand-off directory | after the check |

- **Nothing is exempt.** Scope limits that are not exemptions:
  - the parts of the Git directories `_walk_git` leaves out, because other sessions of the repository write there;
  - nested checkouts' contents (other repositories);
  - the scratch directory, which is outside the tree: what a reviewer could put there is at most its own answer, which it gives anyway, and it is read only at a completed turn.
- **Behaviour changes, by design:**
  - The reviewer may no longer write `notes-<model>.md`; its notes travel in the JSON (`notes`), and the prompt now says "Write no file at all". A2 ("any file other than its notes" is a failure) still holds; the check is stricter than A2 requires.
  - `OUTPUT-<model>.json` in the hand-off directory is no longer written by anyone, so a write there is a failure.
- **Known limit:** if `TMPDIR` lies inside the checkout, Codex's answer write is reported as a write. That is a false failure, never a false pass.

### 3. The filing outcome is never dropped (F2)

- **The one close function** is `review_record_write.close_review_run(repo_root, t, model, run, filed: Outcome, *, reason, errors, tail)`. `filed` is required and typed, and `Outcome.state` is `Literal["recorded", "rerun", "review_failure"]`, plus `exit` (the harness's exit code). Only `recorded` goes to `close_run`, which still validates the record; anything else becomes `incomplete` with `outcome`, a reason and a reviewer-failure event, whatever older record exists. `close_run`'s fallback to an older valid record can no longer be reached by a launched reviewer's filing.
- **Callers:**
  - `review delegate._close` (a roadmap review), and `delegate`'s interrupt handler, which passes `Outcome("rerun", "interrupted: …", exit=None)`, chore runs included;
  - `prompt --channel cli` through `role_prompt_cli.close_cli_review_run`, for every exit, an interrupt included.
  The only `close_run` caller left is a chore's completed run, which files nothing: under M8.2 its reviewer writes its own verdict file.
- **Every exit of `prompt --channel cli` returns an `Outcome`.** Its reviewer path is now `role_prompt_cli.run_reviewer_channel(...) -> Outcome`, so there's nothing for a caller to forget:
  - a failed preflight, a refused `agy` flag, and a missing or malformed cli are rerun requests with an exit code;
  - `run_default_reviewer`, `run_custom_reviewer` and `run_and_file` return the filing.
  `run_cli_channel` is now for non-reviewer roles only; `preflight` and `resolve_cli` are shared helpers. `role_prompt` no longer calls `reviewer_run_failure.close_reviewer_cli_run` or `fail_reviewer_cli_run`. Both are now unused and stay in `reviewer_run_failure.py`, which is outside the touch zones; delete them in a follow-up if wanted.
- **Regressions** (`tests/test_review_record_write_closure.py`):
  - `test_prompt_cli_keeps_a_failed_filing_incomplete_beside_an_older_record_of_the_commit[rerun|review_failure]` (from round 5);
  - new: `test_prompt_cli_that_sends_nothing_stays_incomplete_beside_an_older_record_of_the_commit[preflight|interrupt]`. On the pre-design code (HEAD `052823ab`) the preflight case fails, because the run ends `complete`. The interrupt case fails there only because it patches the new entry point.

### Probes (inputs checked and found safe)

- **Extractor:** everything in the table above, plus direct probes:
  - CRLF output: a plain answer passes, and a CRLF closing fence now passes too. It was a false rerun before the `rstrip` fix and is now tested.
  - Claude `structured_output` that is a list → the same `result` message's text.
  - Codex `agent_message` with integer text → rerun (not an object).
  - Codex `reasoning` item or `error` event around the answer → answer (neither is a message).
  - An envelope whose `structured_output` is a JSON string → rerun.
  - A nested envelope → rerun (schema).
  - A stray `{"type": "assistant"}` line before a plain answer on a Claude entry → rerun (a native stream with no terminal message).
  - A BOM before the answer → rerun.
  - Whitespace-only output → rerun (empty).
- **Write check:** direct `OwnFile` probes in a scratch repository:
  - honest appends and rewrite → no write;
  - a foreign append to the log → the log;
  - the record deleted, then rewritten by specy-road → the record and its directory;
  - a chmod of the record → the record;
  - the record tampered, then rewritten by specy-road → the record.
  Plus through `review delegate`: the parametrized `test_a_run_that_writes_anything_is_a_review_failure_and_files_nothing` (tracked file, untracked `work/`, ignored hand-off file, schema, `RUN-opus.json`, `RUN-opus.log`, `notes-opus.md`, `.review-run.lock`); `test_review_delegate_cli_fails_a_notes_or_answer_write_in_the_hand_off_directory` (alone, or with a transient file); the lock overwrite; and every earlier round's git, chmod, hard-link, ctime, transient and nested-`.git` cases, unchanged and passing.
- **Close:** `recorded` → complete. Rerun, review failure, failed preflight and interrupt beside an older record → incomplete with an event (tests above). Capacity retries exhausted → incomplete with the capacity reason (`tests/test_review_delegate.py::test_capacity_retries_are_bounded_and_end_incomplete`). Usage limit under `prompt --channel cli` → the event names it (`test_prompt_cli_channel_records_usage_limit_and_shows_it_on_the_gate_line`). Chore run → still judged by its own verdict file (`tests/test_chore_mode.py`).
- **Red/green:**
  - without `delegate`'s per-attempt removal of the answer file, `test_a_retried_codex_turn_never_files_the_failed_fresh_turns_answer_file` fails;
  - without `OwnFile.rewrite`'s tamper check, the `RUN-opus.json` case of `test_a_run_that_writes_anything_is_a_review_failure_and_files_nothing` fails;
  - on the pre-design production code, the preflight close case fails.

### Tests changed by this design (not loosened)

- `tests/test_review_record_write.py`:
  - `test_the_reviewers_own_notes_are_the_one_write_allowed` is removed, and `notes-opus.md` and `.review-run.lock` are added to the write-failure parametrization: the allowance is gone by design;
  - `RUN-opus.json` is now named by its own path, since there is no fence;
  - `test_the_final_complete_json_object_of_a_message_is_the_answer` moved to `tests/test_review_answer.py` as `text_object` cases. Its two trailer expectations (`tokens used`, `[INFO] done` after the answer) became rerun requests; the prompt already said "nothing after it";
  - the Codex `-o` assertion now requires the file outside the checkout and the hand-off directory, removed after the run;
  - the commit/cache test now appends the log through `OwnFile`, and also expects the hand-off directory's new entry.
- `tests/test_review_record_write_git.py`: the two "allowed answer or notes write" tests became `test_review_delegate_cli_fails_a_notes_or_answer_write_in_the_hand_off_directory`, alone or with a transient file.
- `tests/test_review_delegate.py`:
  - `test_a_retry_never_files_an_earlier_attempts_answer` now has the failed attempt print its verdict, since an in-tree `OUTPUT-opus.json` write is now a review failure; the stale `-o` case is the new Codex test above;
  - the interrupt test patches `run_reviewer_channel`.
- `tests/test_headless_limits_denials.py`: `run_default_reviewer(...).state == "rerun"` (it returns an `Outcome`).
- `tests/review_delegate_helpers.py`: the fake prints no init event on a `plain` step, since a plain-text harness has no event stream; `fake_reviewer_run` no longer patches `role_prompt.subprocess`, which `role_prompt` no longer uses.

### Verification

- Targeted: `pytest -q -n 4 -p no:cacheprovider` over the 21 files named in READY: 382 passed. A wider run with 8 more importer files also passed (496), before the last two test additions.
- `specy-road file-limits` OK. `ruff check specy_road tests scripts` clean. Private imports 0 new.
- The full suite was not run, per the maintainer's rule.

### Touch zones

- **New module: `specy_road/review_answer.py`** (the extractor and the output schema it validates against; `review_record_write` re-exports `output_schema`, `drop_nulls`, `final_answer`, `Rerun`, `text_object`). Please add it to M8.3's zones.
- `tests/test_review_answer.py` is under `tests/`.
- Unchanged and outside the zones: `specy_road/reviewer_run_failure.py`. Its `close_reviewer_cli_run` and `fail_reviewer_cli_run` are now unused.

## Rescope round (maintainer decision 2026-11-04, WIP `25e8e930`)

About 15 Sol rounds each found another way past "detect ANY write" (A2) and another salvage path (A3). A post-run snapshot cannot prove that no write happened. The maintainer rescoped both:

- A2 is now **prevention plus a bounded tripwire**.
- A3 is now **strict final-answer parsing**.

A1 (specy-road files the record) and the read-only launches cover the real risks: a forged record, and a commit or push. A1, A4 and A5 are unchanged.

### WIP merge and generated files (Sol F4)

- `origin/WIP/improvements-0-3-1` was merged (`09f1ee11`) with no conflicts.
- `specy-road export` and `digest` were run from `sr/`. `sr/roadmap.md` now shows M8 and M8.3 as Not Started, matching the graph (`90cb2766`). `roadmap-context.md` was unchanged.

### REMOVED

Line counts are taken at `HEAD` before this round. Diff total: 917 deleted, 418 added.

- **`specy_road/review_write_check.py`: 240 → 102 lines.** Removed:
  - `OwnFile` (34);
  - `_walk_git` (27) and `_walk` (29);
  - `_record` (7), `_dir_record` (4) and `_content` (10);
  - `_git_marker` (9), `branches` (7), `_file` (6) and `_IDENTITY` (2);
  - the old `snapshot` (18) and `written` (12), replaced by smaller ones.

  With them go: inode, device, link-count, mode, size, mtime and ctime records; directory records; the `.git` / `hooks` / refs / reflogs / `packed-refs` / index scoping; nested-checkout markers; and the in-place content tracking of specy-road's own files.
- **`review_record_write` / `review_delegate`:** removed:
  - the `own` parameter of `file_review` and `written`;
  - the `ref` parameter of `snapshot`;
  - `OwnFile` in `run_logged`, `run_and_file` and `_turn`;
  - `_Harness.record`, the in-place `record.rewrite` between turns, and both log `touch()` calls before the snapshot.

  The log is now a plain append.
- **Adapter message mapping:** `Adapter.messages` in the base class (5), Claude Code (11), Codex (18) and Cursor (9). Also `Message` (8), `native_events` (3), and `CLAUDE_EVENTS`, `CODEX_EVENTS` and `CURSOR_EVENTS` (8 with comments). The `TURNS` table below replaces them.
- **`review_answer.py` salvage:** `text_object` (16), `_open` (7), `_FENCE_END` and `_LINE_OBJECT`. The prose-before-object, closing-fence and "ends with an object" rules are gone. The old `final_answer` (27) is replaced by `final_answer` plus `_answer`, driven by the table.
- **Tests:**
  - `tests/test_review_record_write_git.py` was deleted (277 lines). It covered: index-only writes, stale stat cache, hooks, linked-worktree Git metadata, chmod, nested `.git`, hard-link swaps, identical rewrites, create-and-delete, transient notes, and other sessions' Git activity. All of these are now out of scope.
  - In `tests/test_review_record_write.py`, the snapshot unit tests (mtime put back, commit refs, detached-checkout branch) and the `text_object` assertions were removed.
  - `test_an_in_place_overwrite_of_the_run_lock_is_a_review_failure_and_files_no_verdict` was removed: the lock is now an allowed run file.
  - In `tests/review_delegate_helpers.py`: the fake's `keep_mtime`, `transient`, `relink`, `chmod` and `git` steps (18 lines) and `wrote_only` (6) were removed.

### Per-adapter table (A3): `review_answer.TURNS`

| Row | Final turn starts at | Must contain | Terminal message (its body) |
|---|---|---|---|
| `claude-code` | its first event (one process is one turn) | — | the `result` event: `structured_output` if a dict, else `result`; `None` when `is_error` |
| `codex` | the last `turn.started` (none: the first event) | `turn.completed` | the last `item.completed` / `agent_message` text; the `-o` file instead when non-blank |
| `cursor` | its first event | — | the `result` event's `result` text; `None` when `is_error` |
| `generic` (Antigravity `agy`, any `channels.cli`) | the whole output | — | the whole output, one object; an envelope's `structured_output` |

An output with none of a row's event types is read by the `generic` row (a plain-text wrapper). Inside the final turn:

- Every non-blank line must be one JSON object, or it is a rerun request (Sol F2).
- The last terminal message is the only answer. Its text, stripped of surrounding whitespace, must parse as **one** JSON object, and that object must pass the schema.
- Each of these is a rerun request: missing, `null`, empty, not JSON, prose, a code fence, two objects, an array, or schema-invalid.
- Nothing is salvaged, and an earlier answer is never used.
- A Codex turn without `turn.completed` is a rerun request: cut off, `turn.failed`, or a later `turn.started` (Sol F3).

The prompt's last section and `RESUME_PROMPT` now ask for exactly one JSON object, with nothing before or after it.

Tests: `tests/test_review_answer.py` has 59 cases over the four rows, and a check that every row has cases. The cases are: valid; missing; null; error; empty; non-JSON; prose; fenced; two objects; nested; schema-invalid; multiple; **F2** (valid result then a truncated `{"type":"result","result":` line); stray text after; **F3** (completed turn then `turn.started`); an unparseable line in the final turn vs an earlier one; and plain wrappers. There is also an end-to-end F2 test through `review delegate --json` in `tests/test_review_record_write.py`.

### Prevention (A2)

- **Claude Code:** `--allowedTools Read,Glob,Grep,Bash --disallowedTools Write Edit NotebookEdit "Bash(git commit *)" "Bash(git push *)" "Bash(gh *)"`. `--permission-mode acceptEdits` is dropped, so nothing approves edits. The new constants are `REVIEWER_TOOLS` and `REVIEWER_NO_WRITES`.
- **Codex:** `sandbox_mode=read-only`.
- **Cursor:** `--mode ask --trust`, with no `--force`.

Each argv is pinned: Claude in `test_claude_code_reviewer_without_channels_cli_runs_bare`; Cursor and Codex in `test_cursor_reviewer_runs_ask_mode_without_force` and `test_codex_reviewer_runs_read_only_with_the_output_schema`.

### Tripwire's exact rules (`review_write_check.py`)

A run is a **review failure** (and nothing is filed) when `written(before, after)` is non-empty. That happens when:

1. The leaf worktree's `git status --porcelain -z --untracked-files=all` lists a path it did not list before the run, or lists one with another two-letter status code or another SHA-256 of its content. This covers a changed tracked file and a new untracked file, and also a file that was already dirty and changed again. For a rename or copy entry, its source field is skipped. Paths under the hand-off directory are left to rule 2.
2. The hand-off directory `work/reviews/<ID>/`, walked recursively, gains, loses or changes (by SHA-256) any file except four: `notes-<model>.md`, `RUN-<model>.json`, `RUN-<model>.log` and `.review-run.lock`.

A `REVIEW-<model>.md` that the run filed itself is still put back (`Snapshot.restore`).

Out of scope, stated in the module docstring and in `docs/orchestration-reviewer-output.md`: identical-byte rewrites, writes undone before the run ends, metadata-only changes, git-ignored files outside the hand-off directory, and Git internals (`HEAD`, refs, reflogs, index, hooks, config). The tripwire is not a security boundary; prevention is. A reviewer commit is therefore stopped by the launch bans, not detected.

Tests in `tests/test_review_record_write.py`:

- six writes that fail: tracked, new untracked, untracked in `work/`, hand-off new file, schema, packet;
- the three allowed files that stay recorded: notes, `RUN-opus.json`, lock;
- the self-filed record put back;
- a direct `snapshot`/`written` test of the exact rules, including dirty-before-then-changed, a removed hand-off file, and another model's run file.

### Verification

- `pytest -q -n 4 -p no:cacheprovider` over the 17 core files (`tests/test_review_answer.py tests/test_review_record_write.py tests/test_review_record_write_closure.py tests/test_review_delegate.py tests/test_run_record_no_false_failure.py tests/test_review_signing.py tests/test_review_files.py tests/test_headless_limits_denials.py tests/test_worker_adapters.py tests/test_roster_harness_model.py tests/test_chore_mode.py tests/test_orchestration_guard_hooks.py tests/test_worker_turn_check.py tests/test_claude_config_dir.py tests/test_review_record_rules.py tests/test_dynamic_routing_reviewers.py tests/test_models_and_prompt.py`): 453 passed.
- All 83 test files that import a changed module (`review_answer`, `review_record_write`, `review_write_check`, `review_delegate`, `worker_adapter*`, `role_prompt*`, `review_files` or the delegate helpers): 1231 passed. The full suite was not run.
- `specy-road file-limits`: OK. `docs/orchestration-review.md` was trimmed to 400 lines; the WIP merge had taken it to 408.

### Touch zones

All changed files are inside M8.3's zones: `review_answer`, `review_write_check`, `review_record_write`, `review_delegate`, `worker_adapter_base/claude/codex/cursor`, `worker_adapters`, both docs, and `tests/`.

## Fix round (Sol-low block at `e559ea74`; Sol block at `26d95ca0`)

WIP merged first (`ed936c6b`), no conflicts.

### Sol-low F1: tests coupled to fake-harness call count and order

- **Class:** a test that asserts how many launches the fake harness recorded, or reads a launch by its position, instead of by what the launch observably was. Fake-call position is not behaviour; it breaks if the toolkit adds a preflight or probe call.
- **Design:** a new public helper, `tests/review_delegate_helpers.launches(calls, flag)`, selects launches by an argv flag: `--session-id` for a fresh turn, `--resume` for a resumed one. Retry counts are now asserted only from the run record's `attempts`.
- **Changed:**
  - `test_review_record_write_closure.py`: the Codex resume test selects resumes by `exec resume`, asserts no `-o` (fresh) launch, and asserts a single attempt. The retried-Codex test selects the fresh launch by `-o` and the resume by `exec resume`; it keeps the `attempts` capacity list `[True, False]`.
  - `test_review_delegate.py`:
    - success: selects the fresh launch with `launches`;
    - capacity retry: every `--resume` launch names the fresh session and gets the continue prompt; the count is from `attempts`;
    - retry-never-files: `attempts == [True, False]`;
    - bounded retries: `attempts` gives three capacity errors;
    - resume: some `--resume` launch names the recorded session;
    - zero retries and capacity-in-review-text: `attempts` only.
  - `test_review_files.py`: both Claude reviewer tests select the launch by argv prefix (`claude -p`, `sh -c`), not `calls[0]` or a one-element unpack.
- Every outcome, argv, prompt and no-record assertion is kept.

### Sol (`26d95ca0`) R1-R4: status at this tip

- R1 (identical-byte writes to `RUN-<model>.json` / `.log`) was **withdrawn by the maintainer's rescope** on WIP `25e8e930`. Those are run files specy-road writes, which the A2 tripwire leaves out. Identical-byte rewrites are documented as out of scope. No code is added for R1.
- R2 (a valid result, then a truncated result line) was fixed by the A3 table in the rescope round. It has a table row and an end-to-end `review delegate --json` test.
- R3 (Codex `turn.started` after a completed turn) was fixed by the same table, which requires `turn.completed` in the final turn. It is a table row.
- R4 (stale `sr/roadmap.md`) was fixed in `90cb2766`. `specy-road export --check` passes at this tip.

## Probes

- `grep` over every test file this branch changes for `(call,) =`, `len(fake_calls`, `calls[0]`, positional `first, second` unpacks, and reading `calls.read_text()` by position: all instances fixed. The one remaining `[-1]` selects among argv-filtered fresh launches.
- `FAKE_CODEX` / `FAKE_AGY` in `review_delegate_helpers` write the launch's argv to a file: each test reads flags out of that argv (`--output-schema`, `-o`, `sandbox_mode=read-only`), never a count. Left as is.
- The `FAKE` script picks its step by call index (`min(len(calls), len(steps))`): that is how the fake scripts a sequence, not an assertion. Each test's outcome is asserted from the run record. Left as is.
- `test_one_leafs_reviewer_runs_take_turns` and the bad-option test assert that `calls.json` does not exist (no launch at all): that is observable, not a count. Left as is.
- Sol R2 class (malformed lines after a valid answer) over all four `TURNS` rows: Claude Code and Cursor truncated-result rows give a rerun; Codex with an unparseable line in the final turn gives a rerun; generic with an extra or truncated envelope gives a rerun.
- Sol R3 class (a later turn opening after an answer): Codex `turn.started` after `turn.completed` gives a rerun. Claude Code and Cursor treat one process as one turn, and `run_text` takes only the last attempt's output.
- `specy-road export --check` (from `sr/`): OK. `specy-road file-limits`: OK. `ruff check` on the changed tests: clean.
- Targeted `pytest -q -n 4 -p no:cacheprovider` over the 17 core reviewer files: 453 passed.

## Fix round 2 (Sol-low block at `0022a371`: F1, A1 with M15.18)

WIP merged first, no conflicts.

- **Class:** the strict harness schema's closed acceptance key set diverging from the keys `review record` requires. `strict_schema` allowed only the leaf's A# ids (`additionalProperties: false`). M15.18's required `removed-test: …` entries (and `removed-test-file`, `new-skip`, `assert-loss`) were therefore rejected, so no strict-schema reviewer could approve such a leaf. M8.3 itself is one.
- **Design:**
  - The new `review_record_write.acceptance_keys(root, node_id, ref)` resolves the **same target** `review record` resolves (`resolve_target(root, node_id, ref)`). It returns that target's `acceptance_ids(t.node)` and `integrity_removals.target_unplanned_removals(root, t)`, the source both the packet and the record check use.
  - `write_schema(root, reviews, ref)` builds `strict_schema(ids, removals)` from it. `review delegate` and both `prompt --channel cli` reviewer paths now pass the reviewed `ref`, the same one they hand to `review record`.
  - `strict_schema` derives every key's value from `output_schema()`'s own `acceptance`. Ids take its `additionalProperties`. Removals take its `patternProperties` value: `pass` only, as a strict-mode `enum: ["pass"]`, or `null`. So the open (prompt) schema and the strict (harness) schema come from one definition and cannot diverge.
  - `null` lets a blocking reviewer leave a removal unanswered: the record schema allows only `pass` there, and an unjustified removal is a block with a `required_changes` entry. `drop_nulls` now also removes `null` acceptance entries before validation and filing.
- **Test:** `tests/test_review_strict_schema_removals.py` (new). A leaf branch deletes `test_old` without planning it, and `review delegate` runs a fake `codex`.
  - **Approve with `"removed-test: tests/test_leaf.py::test_old": "pass"`:** the `--output-schema` file Codex received passes `strict_problems`, requires `A1`, `A2` and the removal key, accepts the answer, and rejects `fail` for the removal. `review record` files the approve with the entry.
  - **Block with the entry `null`:** fits the schema too, and is filed with the entry dropped.
  - **Approve without the entry:** a rerun request naming the removal; nothing is filed.
  - **No removals:** the keys are the ids alone.

## Probes (fix round 2)

- Where the closed key set reaches: Codex `--output-schema` reads `write_schema`'s file; Claude Code inlines the same file as `--json-schema`; `agy` gets it via `reviewer_cli`. All three now carry the removal keys (one file, one function).
- Ids source: the strict schema used `index(load_nodes(root))` (the checkout), while `review record` uses `acceptance_ids(t.node)` of the resolved target. Both now use the target, with a checkout fallback only when the target does not resolve, in which case `review record` refuses anyway.
- Removals source: the same `target_unplanned_removals(root, t)` that `review_record_rules.unplanned_removal_problem` calls, with the same `ref`. Before, `write_schema` had no ref.
- Pass-only constraint: `strict_schema` reuses the record schema's `patternProperties` value (`const: pass`). The test asserts that `fail` is rejected by the harness schema.
- Milestone targets: `acceptance_keys` goes through `resolve_target`, so it gets `target_unplanned_removals` for milestones too (their leaves' plans). Not exercised by a new test.
- Prompt schema (`schema_lines` / `output_schema`): it already allows removal keys through `propertyNames` and `patternProperties`, so no change was needed.
- Chore reviewers: they write no schema (unchanged).
- Other closed sets in `strict_schema`: the top-level properties come from `output_schema()` (the record schema less the fields specy-road fills, plus `notes`), the same set `final_answer` validates against. No other `additionalProperties: false` maps were found.
- Sol (`26d95ca0`) R1-R4: unchanged from fix round 1. R1 was withdrawn by the rescope; R2 and R3 are fixed by the `TURNS` table; R4 is fixed and `export --check` passes.
- Targeted `pytest -q -n 4 -p no:cacheprovider` over 19 files (the 17 core reviewer files plus `test_review_strict_schema_removals.py` and `test_planned_test_changes.py`): 472 passed. `ruff`: clean. `file-limits`: OK.

## Fix round 3 (Sol-low block at `d36faf66`: F1, A2 tripwire)

WIP merged first, no conflicts.

- **Class:** a decision in the tripwire made on a **resolved** path, that is, one that follows a symlink the reviewer could have created. `_status` resolved each `git status` entry before checking whether it lay in the hand-off directory. So `T src/a.py`, a tracked file replaced by a symlink into `work/reviews/<ID>/notes-<model>.md`, was excluded as if it were the notes. The same class reached three other places: `snapshot` re-resolved the checkout and the hand-off directory after the run; `_handoff` walked with `rglob`/`is_file`, which follow symlinks; and `_hash` read through symlinks.
- **Design:** nothing reviewer-controllable is resolved or followed.
  - The first snapshot fixes where the checkout and the hand-off directory are: git's toplevel, plus the hand-off directory's real path, which specy-road created before the run. The snapshot after the run takes `like=before` and reuses both.
  - A `git status` entry is excluded only when its path **as git prints it** starts with the hand-off directory's checkout-relative parts (`PurePosixPath.parts` prefix). Every other entry (`M`, `A`, `D`, `T`, `R`, `C`, `??`) is compared.
  - `_handoff` walks with `os.walk` (no following). A symlinked directory there is one entry. The hand-off directory itself replaced by a symlink is one entry.
  - `_hash` hashes a symlink's target text, never its target.
  - Only `notes-<model>.md`, `RUN-<model>.json`, `RUN-<model>.log` and the lock, directly in the hand-off directory, are excluded there.
- **Callers:** `review delegate` and `run_and_file` (`prompt --channel cli`) pass `before` to the after-snapshot.
- **Docs:** the `review_write_check` docstring and `docs/orchestration-reviewer-output.md` state the lexical rule. `docs/orchestration-review.md`: the WIP merge had brought it back to 406 lines, so the tripwire paragraph is folded into the launch paragraph (397).
- **Tests:** `tests/test_review_tripwire_symlinks.py` (new; public `review delegate` and `prompt --channel cli`):
  - `src/a.py` typechanged to a symlink (git reports `T src/a.py`), and a new untracked symlink, each pointing at the notes path (absolute and relative) or at a file outside the repository: a review failure naming exactly that path, and no record (6 cases);
  - the same typechange through `prompt --channel cli`;
  - a symlink to `src/` created inside the hand-off directory: one entry, not followed;
  - the hand-off directory replaced by a symlink to `src/`: the exclusion does not move onto `src/`, and `src/a.py`, the directory and its lost `PACKET.md` are reported.
  - The fake harness gained a `symlink` step.

## Probes (fix round 3)

- `grep resolve|realpath|is_relative_to` in `review_write_check.py`: one `resolve()` remains, on the hand-off directory in the **first** snapshot only (before the reviewer starts; specy-road's own directory). `is_relative_to` is used only between fixed paths (that real path and git's toplevel) and for display. No per-entry resolution remains.
- `_status` exclusion: lexical prefix of git's printed path. Covered by a typechange into the notes (absolute and relative link text), a link out of the repo, and a new untracked link: all reported.
- Rename/copy entries (`R`, `C`): the new path is compared and the source field is skipped. The new path is under the hand-off directory only if git prints it there.
- `_handoff` walk: `os.walk(followlinks=False)`. A symlinked subdirectory is listed as an entry, never walked; tested.
- Hand-off directory swapped for a symlink during the run: reported. The exclusion keeps the place fixed before the run; tested.
- `_hash`: symlinks are hashed by `readlink` text, so a link's target content never stands in for the link.
- Checkout toplevel: taken once from `git rev-parse --show-toplevel` before the run and reused. Before, it was resolved again after the run.
- `Snapshot.restore` (puts back this model's record): it uses the caller's hand-off path, unchanged, and is reached only after a reported failure.
- Sol (`26d95ca0`) R1-R4: unchanged. R1 was withdrawn by the rescope; R2 and R3 are fixed by `TURNS`; R4 is fixed and `export --check` passes.
- Targeted `pytest -q -n 4 -p no:cacheprovider` over 20 files (the 19 from fix round 2 plus `test_review_tripwire_symlinks.py`): 481 passed. `ruff`: clean. `file-limits`: OK.

## Merge with WIP (M14.6: `review usage`, per-round RUN history)

Conflicts in `specy_road/review_delegate.py`, `tests/review_delegate_helpers.py` (add/add), `tests/test_review_delegate.py` and `tests/test_run_record_no_false_failure.py`. Both sides were kept.

- **`review_delegate.delegate`:**
  - M8.3's structure is kept: the lock, the scratch answer file, the schema, the tripwire snapshots, `final_answer`, `file_review` and the single `close_review_run` close.
  - M14.6's `archive_round(repo_root, node_id, model)` runs at the same point as on WIP: after `_start` and the prompt files, before the new run record is saved. That is inside the lock and **before the tripwire's first snapshot**, so archiving the previous round's RUN json, log and notes into `history/` is never seen as the reviewer's write.
  - M14.6's `review usage` registration (`add_usage_parser`) and its docstring line came through the auto-merge.
- **`tests/review_delegate_helpers.py`:**
  - M8.3's fake and helpers are kept: structured final JSON, `plain`, `after`, `symlink` and `launches`.
  - The fake's result line now also carries a step's `result` fields (usage, cost, turns), as Claude's stream-json does. M14.6's `FAKE_USAGE` patched this in by string replacement.
  - M14.6's names are kept on the same fake: `roster`, `read_delegate_calls`, `set_delegate_steps`, `make_delegate_repo`, `run_review_cli`, `run_review_delegate` and `handoff_status_node`.
  - `files_record_step` now returns a step whose final JSON specy-road files, because under M8.3 a reviewer that writes `REVIEW-<model>.md` is a review failure.
- **`tests/test_review_delegate.py`, `tests/test_run_record_no_false_failure.py`:** WIP's change there was only the same helper extraction this branch had already made, so this branch's side is kept.
- **`tests/test_review_usage.py` (M14.6, ported):**
  - Each round's notes now travel in the final JSON, and specy-road writes `notes-opus.md`. The fake no longer writes notes or the record.
  - Notes are compared by the text below the front matter (`_notes`).
  - Each notes line ends `not a defect because …`, so `review record` accepts the approve.
  - Every M14.6 assertion is kept: per-round history, `review usage` totals, reviewers in `worker usage`, no relabeled notes, prompt-cli runs excluded.

Verification: 68 test files that import the reviewer, delegate, usage, run-record or adapter modules, `pytest -q -n 4 -p no:cacheprovider`: 1005 passed. `ruff check specy_road tests scripts`: clean. `file-limits`: OK. `export --check`: OK.

## Fix round 4 (Sol-low block at `b148b290`: R1-R3)

WIP merged first (`--no-edit`), no conflicts.

### R1: specy-road wrote through a reviewer's symlink while recovering

- **Class:** specy-road writing into the hand-off directory, once the reviewer has started, through a path the reviewer may have replaced with a symlink, either the file or a parent directory. The named instance was `Snapshot.restore` writing the old record bytes through `REVIEW-opus.md -> src/a.py`. The same class reaches:
  - `notes-<model>.md` written by `file_review`;
  - `RUN-<model>.json` (and its fixed `.tmp` name) written by `save_run`;
  - `RUN-<model>.log`, appended in `_turn` and `run_logged`, and rewritten as the transcript in `close_cli_review_run` and `close_reviewer_cli_run`;
  - the schema file;
  - `review record`'s own `REVIEW-<model>.md` and `history/` writes after a passing tripwire;
  - restore's `unlink`s through a symlinked `history/`.
- **Design:**
  1. **No symlink in the hand-off directory, ever.** specy-road never makes one, so `_handoff` reports every symlink there as a review failure, changed or not (`written` always counts a `SYMLINK` entry). That covers the directory itself, a subdirectory, and a file at an excluded name (notes, run files, lock). A tripwire pass therefore guarantees `review record` and the notes write see no symlink.
  2. **specy-road's own writes never follow one.**
     - `replace_file` writes a fresh exclusive `mkstemp` file beside the path, then `os.replace`s it over the path; a rename replaces a link rather than writing through it. It is used by `save_run` (no more fixed `.tmp` name), the notes, the transcript logs, the schema and restore.
     - `append_log` opens with `O_NOFOLLOW`; on a symlink the turn's output goes to `/dev/null` and the tripwire reports the link.
  3. **Restore replaces paths; it never follows them.** It runs against the hand-off directory as fixed before the run. It removes every symlink there (deepest first), makes every parent a real directory again (`real_dirs`), and only then unlinks the run's own records and puts the old ones back with `replace_file`.
  4. **A symlink at `RUN-<model>.json` is not lost.** `review delegate`'s between-turn record update replaces it, which would remove the evidence. `_attempts` notes the link, and the after-snapshot reports it (`Snapshot.with_symlinks`).

### R2: a non-string event `type`

- **Class:** a JSON value from the harness used as a set member or compared as an event type without checking that it is a string. Instances: the `row.events` and `row.start` membership tests (a list or object raises `TypeError`), `row.end`, the `result` and `agent_message` checks, and the nested `item.type`.
- **Design:** one accessor, `review_answer.event_type(d)`, returns the `type` only when it is a string. Every table decision goes through it, so a non-string `type` is no harness event. The object then falls to the generic row and is schema-checked, which gives a rerun request.

### R3: U+2028 split as a line

- **Class:** harness output split with `str.splitlines`, which also breaks on U+2028, U+2029, U+0085 and C0 separators. A UTF-8 JSON string may carry the first three raw. Instances: `final_answer`, `run_text`, `review_usage._log_turns` (M14.6; usage would drop a turn), and the error tail in `review_delegate._close`.
- **Design:** `review_answer.stream_lines` splits on `\n` only, the JSON Lines delimiter, and every instance uses it or `split("\n")`. Live reading of harness stdout already uses universal newlines (`\n`, `\r`), not `splitlines`.

### Tests: `tests/test_review_untrusted_output.py` (new, 47 cases; public `delegate` and `final_answer`)

- **R1:**
  - With a block on file, the next reviewer turn replaces each of `REVIEW-opus.md`, `notes-opus.md`, `RUN-opus.json`, `RUN-opus.log`, `.review-run.lock` and `RUN-opus.json.tmp` with a symlink to `src/a.py`. Each run is a review failure naming the path; `src/a.py` is byte-identical; the link is gone; the record is the earlier block as a regular file.
  - `history/` replaced by a symlink to `src/`: a review failure; `src/` unchanged; `history/` is a real directory again with its record copies.
  - A symlink planted before the run: still a failure.
- **R2:** `{"type": v, "result": null}` with `v` in `[]`, `{}`, `["result"]`, `{"x": 1}`, `1` and `null`, on all four adapters: a schema-invalid rerun. Through `review delegate` with a generic reviewer (list and object): a rerun, no record.
- **R3:** U+2028, U+2029 and U+0085 raw in the notes string, on all four adapters: the answer is returned intact. End to end, a fake Claude writes its result line with U+2028 unescaped (new fake option `unescaped`): `run_text` keeps it, the run is recorded, and `notes-opus.md` holds it.
- The fake harness's `symlink` step now also replaces a directory.

Touch zones: `specy_road/reviewer_run_failure.py` (`save_run`) and `specy_road/review_usage.py` (`_log_turns`) were added to M8.3's zones (`sr/roadmap/phases/M8.json`, `registry.yaml`).

## Probes (fix round 4)

- Every write specy-road makes into the hand-off directory after the reviewer starts (`grep write_text|write_bytes|open(|save_run` over `review_record_write`, `review_delegate`, `role_prompt_cli`, `reviewer_run_failure`, `review_write_check`): all now go through `replace_file` or `append_log`. The lock is opened before the run, and the prompt files and archive moves happen before it too.
- `save_run`'s fixed `RUN-<model>.json.tmp` name, a second R1 path: replaced by `mkstemp`. Tested with a planted `.tmp` symlink: the source is unchanged.
- `RUN-<model>.json` symlink erased by the between-turn update: reported through `with_symlinks`. Tested.
- `RUN-<model>.log` symlink: `O_NOFOLLOW` sends the output to `/dev/null`, and the link is reported. Tested. `run_text` reads through the link, but read-only, and the run fails first.
- `review record` (outside the zones) writes `REVIEW-<model>.md` and a `history/` copy only after a tripwire pass, which now guarantees no symlink anywhere in the hand-off directory.
- Restore with the hand-off directory itself symlinked: the link is removed and a real directory is made; the records are written from memory. Restore uses the place fixed before the run, not the caller's path.
- `real_dirs` on a regular file standing where a directory belongs: unlinked and made a directory.
- `event_type` on every adapter's `parse_events` and `final_answer` with `type` and nested `item.type` and `message.content` set to `[]`, `{}`, `1`, `null` and `true` (scratch probe): no exception anywhere.
- `_result`'s `is_error` and `structured_output`, and `_agent_message`'s text: they take no hashing path; a non-string text falls to "not one complete JSON object".
- Line splitting: `grep splitlines` over the reviewer modules finds none left. Live stdout iteration uses universal newlines only (a raw `\r` cannot occur inside a valid JSON string).
- Raw C0 separators (`\x0b`, `\x0c`, `\x1c`-`\x1e`) cannot occur in valid JSON strings (they must be escaped), so they are not tested as raw characters.
- No test in this branch imports a `_`-prefixed name from another test module (`grep` over the changed test files).
- Sol (`26d95ca0`) R1-R4: unchanged. R1 is withdrawn by the rescope; R2 and R3 are fixed by `TURNS`; R4 is fixed.
- Verification: 69 importer test files, `pytest -q -n 4 -p no:cacheprovider`: 1052 passed. `ruff check specy_road tests scripts`: clean. `file-limits`: OK. `export --check`: OK.

## Not verified / open

- **No live harness runs.** The Claude and Codex flags come from the tracked captures, Cursor's from the fixture, and Antigravity's from the vendor page above (not installed; M8.6 records its runtime checks as not run).
  - Whether Codex strict structured output accepts this schema is unverified.
  - Whether `agy --output-format json` prints one line or many is unverified. Both work: the envelope is the output's final object, starting a line.
- **Shared checkout.** Another session that changes `git status` or the hand-off directory during a review still fails it (rescope tripwire). Run reviewers where nothing else writes.
- **Strict parsing vs. live models.** A reviewer that wraps its final JSON in prose or a fence now gets a rerun request. The prompt says so explicitly, but no live Cursor run (no structured-output flag) has been tried.
- **What the tripwire doesn't see:** writes outside the worktree's `git status` and the hand-off directory (`/tmp`, `~`, another worktree, ignored files), plus everything listed as out of scope above.
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
- `_dir_record`, `_walk`'s `quiet` set and `wrote_only` (round 11): directory metadata for Sol's create-and-delete finding.
- `RootFence`, `harness_files`, `file_review`'s `fenced`, `_Harness.fenced`, `GIT_OPTIONAL_LOCKS=0` in `reviewer_env` and `wrote_paths` (round 12): Sol's hand-off-root and Git-root finding.
- `prepare_harness_files`, and `RootFence` without exceptions (round 13): Sol's combined allowed-plus-forbidden finding.
- `_open_braces` and its condition in `json_object` (round 14): Sol's nested-in-malformed-JSON finding.
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
- WIP merge (`2012edce`, `0d76d22f`): `tests/test_run_record_no_false_failure.py` rewritten onto the public helpers and the structured-output path (M11.77's intent kept; its old self-filed record is a write violation now). `docs/orchestration-reviewer-output.md` (new): the moved section, for the file limit. No new code, branch or guard.
- Git-scope fix round (`9b01c380`): `review_write_check.branches` (the reviewed branch's ref names) and `_file` (one Git metadata file, absent means no entry), plus the `ref` parameter of `snapshot`, all for the coordinator's live shared-repository failure. Two tests are added; the existing tests changed are listed in that round's section.
- Strict Codex schema fix round: `review_record_write.strict_schema` (the Codex strict form; also written for Claude Code and `agy`), `drop_nulls` (null optional fields read as absent), the `root` parameter of `write_schema` (the leaf's acceptance ids) and the prompt's `null` sentence, for the live Codex schema rejection. No new guard. Tests: `tests/review_delegate_helpers.strict_problems` (a checker for OpenAI strict rules), `FAKE_CODEX` moved there, one new test and one extended (named in that round's section).
- Fix round 2: `_open_braces` counting `[`/`]` (Grok's A3 array finding); `review_delegate.delegate` writing the schema once before its snapshot, `write_schema`'s unchanged-text branch (reached by the extended lock test) and `OUTPUT_SCHEMA_NAME` dropped from `runtime_files` (Grok's A2 schema finding); `RootFence`'s `model` parameter and run-record entry, with its `OSError` branch for `run_default_reviewer`/`run_custom_reviewer` called without a run record (reached by `tests/test_headless_limits_denials.py::test_review_delegate_and_the_bare_reviewer_command_disable_background_tasks`) (Grok's A2 run-record finding). No new test function; three parametrized tests and the lock test extended.
- WIP merge `458dca91`: the `rc and outcome.state == "rerun"` condition in `run_and_file` (WIP's last-line capacity rule), and the `say` step in `tests/review_delegate_helpers.FAKE` (WIP's capacity-wording test).
- Fix round 3: `review_write_check.RunLog` (`open`, `write`, `changed`, `_bytes`) and `file_review`'s `log` parameter (F1); the per-attempt `prepare_harness_files` in `_attempts` (F2); the `sign_key` parameter of `_review_record`, `file_review`, `run_and_file`, `run_default_reviewer`, `run_custom_reviewer`, `run_cli_channel` and `delegate`, plus the `--sign-key` options of `review delegate` and `prompt` (F3); the lock in `role_prompt.main` with its `ReviewRunBusy` exit, `role_prompt._run`, and `delegate`'s lock moved before `_start` (F4). Removed: the lock and busy branch in `run_and_file`, the pre-lock unlinks, and `write_schema`'s unchanged-text branch. Tests: two new, two extended, one moved (named in that round's section).
- Fix round 4: `worker_adapter_base._program_end` (F1: where the quoted or escaped program word ends); `review_record_write._later_array` with `_ARRAY_LINE` and `_JSON_VALUE` (F2: a later JSON array is a rerun request), and `_depth`, factored out of `_open_braces`. Tests: two extended, one parametrized (named in that round's section).
- Fix round 5: `review_record_write.close_unfiled` (F2: the failure branch of `review_delegate._close`, moved for reuse); `run_and_file`'s `filed` parameter, threaded through `run_cli_channel`, `run_default_reviewer` and `run_custom_reviewer` (F2: the filing outcome reaches the prompt-CLI closure); `role_prompt_cli.close_unfiled_cli_run` and its already-incomplete branch (F2: no second event when `close_run` already recorded one); the `""` return of Codex's, Claude's and Cursor's `final_message` (F3: an answer event with no answer replaces an earlier one). Removed: `.review-run.lock` from `runtime_files` (F1). Tests: `tests/test_review_record_write_closure.py` (new: the lock overwrite, the prompt-CLI rerun/review-failure beside an older record, the Codex resume with a null last answer and its control). No new mock or guard.
- Design pass (`73b0fea1`):
  - `worker_adapter_base.Message` and `native_events`, `Adapter.messages` (generic: `None`), and the Claude, Codex and Cursor `messages` with `CLAUDE_EVENTS`, `CODEX_EVENTS` and `CURSOR_EVENTS`: each adapter maps its stream to `(body, terminal)` (replaces `final_message`).
  - `specy_road/review_answer.py`: `final_answer`, `Rerun`, `text_object` and `_open` (the one extractor; replaces `final_output`, `json_object`, `_later_array`, `_depth` and `_open_braces`), with `output_schema`, `drop_nulls`, `FILLED_BY_SPECY_ROAD` and `NOTES_DESCRIPTION` moved from `review_record_write`.
  - `review_write_check.OwnFile` (`RunLog` generalized, plus `rewrite` with its tamper check) and `written`'s `own` parameter with `_IDENTITY`: specy-road's own files compared by content. Removed: `runtime_files`, `harness_files`, `prepare_harness_files`, `RootFence`, `quiet`, `Snapshot.exempt`, `OUTPUT_PREFIX`.
  - `review_record_write.answer_scratch`: Codex's `-o` file outside the tree. `close_review_run` and `Outcome.exit` with the `Literal` state: the one close (replaces `close_unfiled`). `run_and_file` returns `Outcome` and takes `output`; `file_review` takes `answer` and `own`.
  - `review_delegate`: `_Harness.output` and `.record`, the per-attempt answer-file removal, the in-place record rewrite, the log `touch` before the snapshot, and `_close`/interrupt through `close_review_run`.
  - `role_prompt_cli`: `run_reviewer_channel` (the reviewer path, an `Outcome` on every exit), `preflight` and `resolve_cli` (shared with `run_cli_channel`), `close_cli_review_run` (replaces `close_unfiled_cli_run` and the use of `close_reviewer_cli_run`/`fail_reviewer_cli_run`), and `READ_BACK_HARNESSES` (moved from `role_prompt`).
  - Tests: `tests/test_review_answer.py` (new; the shape table and the text rule); in `tests/test_review_record_write_closure.py`, `FAKE_CODEX_TURNS`/`_codex` (a fake Codex with a fresh failing turn and a resumed turn), `test_a_retried_codex_turn_never_files_the_failed_fresh_turns_answer_file` and `test_prompt_cli_that_sends_nothing_stays_incomplete_beside_an_older_record_of_the_commit`. No new mock beyond the fake harness binaries and the interrupt `monkeypatch`.
