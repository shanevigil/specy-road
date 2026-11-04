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
