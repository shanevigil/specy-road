# Implementation summary: M15.9 — Harness launches survive large prompts and a harness binary off PATH

Implementation commit: `a0820f11` on `feature/rm-harness-launches-survive-large-prompts-and-binaries-off-path` (base `94d30274`).

## What changed

- **A1 (prompt never on argv).** Cursor was the only adapter putting the prompt text on argv. `agent --help` (the
  shipped 2026.10.22 capture) documents no stdin, so `Cursor.launch`, `resume` and `reviewer_launch` (M8.3's
  `--mode ask` included) now pass one short argument, `file_instruction(<absolute prompt path>)`, as Claude Code's
  `STDIN_INSTRUCTION` does. Claude Code and Codex already used stdin. No `--add-dir` for the prompt's directory: an
  executor's extra roots are writable (`tests/test_worker_handoff_writable.py` guards that), so the instruction
  names the absolute path only.
- **A2 (pre-exec refusal).** `worker_adapter_base.oversized_arg` / `checked` refuse an argv element over the OS
  single-argument limit (128 KiB, Linux `MAX_ARG_STRLEN`) with the size and the `{prompt}` fix. Applied to every
  custom command an adapter builds (`Adapter._custom`, generic `launch`), to `prompt --channel cli`'s custom
  reviewer (a rerun request) and plain commands (exit 1, e.g. `--role rca`).
- **A3 (harness binary).** New `specy_road/harness_binary.py`: `resolve(harness, harness_bin)` — roster
  `harness_bin`, else `PATH`, else install dirs (`~/.local/bin`; `~/.claude/local` for claude); not found raises
  `HarnessNotFound` (an `Unsupported`) naming the dirs searched and `harness_bin`. Adapters take an optional
  `harness_bin` kwarg on launch/resume/reviewer_launch and use it as argv[0] (and for Cursor's `agent create-chat`);
  with none passed, `Adapter._program` resolves PATH → install dirs. Callers pass the roster entry's resolved
  binary: `worker delegate` (`worker_ops_launch`), `review delegate` (`_Harness`, before any run file is written),
  `prompt --channel cli` (`run_reviewer_channel`, a rerun request when not found). Recorded: the worker
  `launched` event's `detail.argv0` and the reviewer `RUN-*.log` header already log `argv[0]`, now the absolute path.
- Schema: `harness_bin` on roster entries (`templates/project/schemas/orchestration.schema.json`).
- Docs: new `docs/orchestration-harness-launch.md`.

## Gaps and out-of-zone notes (for the reviewers and the PM)

- **`worker message` / resume ignores `harness_bin`.** `specy_road/worker_ops_message.py:85` (outside the zones)
  calls `adapter.resume` without `harness_bin`, so a resume resolves PATH → install dirs only (still a refusal, not
  exit 127, when absent). Fix: pass `harness_bin=entry_binary(rec.harness, entry, default=not cli)` there; add that
  file to the zones. Documented in the new doc.
- `docs/orchestration-workers.md:358` (outside zones) still says the cursor prompt is an argument with the 100 KiB
  refusal; it should point at the new doc.
- Shipped model profiles' `access.cli` (templates/project/model-profiles, outside zones) use `"<prompt>"`; a prompt
  over 128 KiB through them is now refused pre-exec with the `{prompt}` fix (A2's intended behaviour).
- `sr/schemas/orchestration.schema.json` (toolkit's own project copy) is not updated; `upgrade` refreshes it.
- Touch zones confirmed as listed; `worker_adapter_parsers.py` was not changed. No file-limits issue.

## Verification

- `pytest -n 4 tests/` — 4880 passed, 1 failed (a new private reference `_Harness` in my test), fixed by testing
  through `review_delegate.delegate`; the affected files then passed.
- `ruff check specy_road tests scripts`, `specy-road file-limits`, `scripts/check_clones.py`,
  `scripts/check_test_private_imports.py`, `scripts/check_machine_paths.py`, dogfood `validate` / `export --check` /
  `digest --check` — all exit 0.
- Red-green: `tests/test_harness_launch.py -k "cursor and (executor or reviewer)"` against the pre-change
  `worker_adapter_cursor.py` — 2 failed (exit 1).

## Added

### Helpers / modules
- `specy_road/harness_binary.py` `resolve`, `entry_binary`, `HarnessNotFound`, `INSTALL_DIRS` — A3 resolution order and refusal.
- `worker_adapter_base.PROGRAMS` — the default program per harness, shared by adapters and the resolver.
- `worker_adapter_base.ARG_LIMIT`, `oversized_arg`, `checked` — A2 pre-exec refusal.
- `worker_adapter_base.file_instruction` — A1 short argument naming the prompt file.
- `Adapter._program` — argv[0] from the resolved binary, else PATH → install dirs.
- `worker_adapter_cursor._prompt_args` — Cursor's prompt argument (the file instruction).
- `role_prompt_cli._refused` — one rerun-request path for a reviewer refused before anything ran.

### Branches / guards
- `harness_bin` kwarg on every adapter's `launch` / `resume` / `reviewer_launch`; `create_chat(worktree, program)` — runs the resolved binary.
- `checked(...)` around custom launches in `Adapter._custom`, generic `launch`, `run_custom_reviewer`; `oversized_arg` in `run_plain_cli` — A2.
- `entry_binary` calls in `worker_ops_launch._launch_locked`, `review_delegate._Harness.__init__`, `role_prompt_cli.run_reviewer_channel` — A3 before launch.
- Schema property `harness_bin` — roster entries may set it.

### Mocks
- `tests/conftest.py` autouse `harness_binaries_are_not_looked_up` — stubs `harness_binary.resolve` to the bare program name so tests do not depend on installed harnesses (as the existing `create_chat` stub does); `test_harness_launch.py` uses the real resolver.
- `conftest` `create_chat` stub now accepts `program` — new signature.

### Tests
- `tests/test_harness_launch.py::test_a_200_kib_prompt_never_puts_an_argument_over_32_kib` (4 harnesses × executor/reviewer/rca) — A1.
- `::test_cursor_names_the_prompt_file_on_every_launch` — A1, Cursor launch/resume/ask reviewer.
- `::test_a_prompt_text_command_over_the_limit_is_refused_by_every_adapter`, `::test_the_limit_is_one_argument_not_the_whole_command`, `::test_a_custom_reviewer_with_prompt_text_is_a_rerun_request_and_nothing_runs` — A2.
- `::test_resolution_order_harness_bin_then_path_then_install_dirs`, `::test_not_found_is_a_refusal_naming_the_dirs_searched_and_harness_bin`, `::test_worker_and_reviewer_launches_run_the_resolved_binary`, `::test_a_missing_binary_refuses_every_launch_before_anything_runs` — A3.
- Updated to the new behaviour (not loosened): `test_worker_turn_check.py` cursor launch, `test_review_record_write.py` cursor reviewer argv and `prompt --channel cli` cursor reviewer, `test_prerelease_review.py` huge `"<prompt>"` now refused pre-exec.
