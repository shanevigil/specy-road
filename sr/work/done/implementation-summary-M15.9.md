# Implementation summary: M15.9 — Harness launches survive large prompts and a harness binary off PATH

Implementation commits: `a0820f11`, fix round `f1da5ed6` (after merging `origin/WIP/improvements-0-3-1`); first commit `a0820f11` on `feature/rm-harness-launches-survive-large-prompts-and-binaries-off-path` (base `94d30274`).

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
  `harness_bin` kwarg on launch/resume/reviewer_launch; `Adapter._program` is the one resolver: it calls
  `resolve(harness, harness_bin)` whenever a default command is built (argv[0], and Cursor's `agent create-chat`).
  Every caller passes the roster entry's raw `harness_bin`: `worker delegate` (`worker_ops_launch`), `worker message`
  resume (`worker_ops_message`), `review delegate` (launch, resume and the default-resume fallback of a custom
  command without `{session}`), `prompt --channel cli` (a rerun request when not found). Recorded: the worker
  `launched` event's `detail.argv0` and the reviewer `RUN-*.log` header already log `argv[0]`, now the absolute path.
- Schema: `harness_bin` on roster entries (`templates/project/schemas/orchestration.schema.json`).
- Docs: new `docs/orchestration-harness-launch.md`.

## Fix round (gpt-6.1-sol-low block of `da4a1fb6`)

- **R1 — class: a caller that builds a default harness command without forwarding the roster's `harness_bin`.**
  Removed by design rather than patched at one site: `entry_binary` is gone; callers pass the raw roster value and
  the adapter resolves it at the single point where a default argv[0] is chosen (`Adapter._program`). Resolution now
  happens only when a default command is actually built, so a custom command never triggers it and a custom
  command's default-resume fallback cannot miss it. The documented workaround is removed from the new doc.
  Behaviour change: `review delegate` with a missing binary is now refused at the first launch (its run record is
  closed as a rerun request) rather than before the run record opens; `prompt --channel cli` resolves after writing
  the output schema. Neither runs the harness.
- **R2 — class: docs describing the Cursor prompt on argv / the old 100 KiB refusal.** Cursor and generic rows in
  `docs/orchestration-workers.md` now describe the file instruction and the 128 KiB pre-exec guard, linking
  `orchestration-harness-launch.md`; the Cursor `channels.cli` example (`"<prompt>"`) now notes the refusal.

## Probes

- Every adapter call site in `specy_road/` (`grep adapter.*.(launch|resume|reviewer_launch)(`): worker_ops_launch, worker_ops_message, review_delegate (launch/resume/reviewer), role_prompt_cli — all pass `harness_bin` now.
- Claude Code resume with a custom command lacking `{session}` (falls back to the default): runs the `harness_bin` binary — tested.
- Cursor `create_chat`: gets its program from `_program` — tested (`chats == [agent]`).
- Bare program names elsewhere in `specy_road/`: only `human_resume` (claude/agent/codex `--resume`, a command shown to a person for their interactive shell; callers `worker_cli.py`, `worker_lease.py` outside zones) — unchanged, noted.
- `_JSON_FORMS` text-output note and `model_from_argv` / `launch_model`: match by basename or flags, unaffected by an absolute argv[0].
- R1 red-green: `test_worker_message_resumes_with_a_binary_only_harness_bin_reaches` against `worker_ops_message.py` without the forward — fails with `HarnessNotFound` (exit 1); passes with it.
- Docs sweep for `100 KiB` / "prompt is an argument" / `E2BIG`: only `docs/orchestration-models.md:170` remains ("exits 1 with the reason — use `{prompt}`"), still accurate (now refused before launch); outside zones, unchanged.

## Gaps and out-of-zone notes (for the reviewers and the PM)

- `human_resume` commands stay bare program names (see Probes).
- Shipped model profiles' `access.cli` (templates/project/model-profiles, outside zones) use `"<prompt>"`; a prompt
  over 128 KiB through them is now refused pre-exec with the `{prompt}` fix (A2's intended behaviour).
- `sr/schemas/orchestration.schema.json` (toolkit's own project copy) is not updated; `upgrade` refreshes it.
- Touch zones confirmed as listed; `worker_adapter_parsers.py` was not changed. No file-limits issue.

## Verification

Fix round: targeted suite (17 files incl. `test_harness_launch.py`, `test_worker_cli.py`, `test_review_delegate.py`) 336 passed; `ruff check specy_road tests scripts` and `specy-road file-limits` exit 0.

First round:

- `pytest -n 4 tests/` — 4880 passed, 1 failed (a new private reference `_Harness` in my test), fixed by testing
  through `review_delegate.delegate`; the affected files then passed.
- `ruff check specy_road tests scripts`, `specy-road file-limits`, `scripts/check_clones.py`,
  `scripts/check_test_private_imports.py`, `scripts/check_machine_paths.py`, dogfood `validate` / `export --check` /
  `digest --check` — all exit 0.
- Red-green: `tests/test_harness_launch.py -k "cursor and (executor or reviewer)"` against the pre-change
  `worker_adapter_cursor.py` — 2 failed (exit 1).

## Added

### Helpers / modules
- `specy_road/harness_binary.py` `resolve`, `HarnessNotFound`, `INSTALL_DIRS` — A3 resolution order and refusal (`entry_binary` removed in the fix round).
- `worker_adapter_base.PROGRAMS` — the default program per harness, shared by adapters and the resolver.
- `worker_adapter_base.ARG_LIMIT`, `oversized_arg`, `checked` — A2 pre-exec refusal.
- `worker_adapter_base.file_instruction` — A1 short argument naming the prompt file.
- `Adapter._program` — the single resolver for every default command's argv[0] (fix round: resolves `harness_bin` itself).
- `worker_adapter_cursor._prompt_args` — Cursor's prompt argument (the file instruction).
- `role_prompt_cli._refused` — one rerun-request path for a reviewer refused before anything ran.

### Branches / guards
- `harness_bin` kwarg on every adapter's `launch` / `resume` / `reviewer_launch`; `create_chat(worktree, program)` — runs the resolved binary.
- `checked(...)` around custom launches in `Adapter._custom`, generic `launch`, `run_custom_reviewer`; `oversized_arg` in `run_plain_cli` — A2.
- `harness_bin=entry.get("harness_bin")` in `worker_ops_launch._launch_locked`, `worker_ops_message` resume (fix round, R1), `review_delegate._Harness` (launch, resume and reviewer kw), `role_prompt_cli.run_reviewer_channel`; `run_default_reviewer` turns `HarnessNotFound` into a rerun request.
- Schema property `harness_bin` — roster entries may set it.

### Mocks
- `tests/conftest.py` autouse `harness_binaries_are_not_looked_up` — stubs `harness_binary.resolve` to the bare program name so tests do not depend on installed harnesses (as the existing `create_chat` stub does); `test_harness_launch.py` uses the real resolver.
- `conftest` `create_chat` stub now accepts `program` — new signature.

### Tests
- `tests/test_harness_launch.py::test_a_200_kib_prompt_never_puts_an_argument_over_32_kib` (4 harnesses × executor/reviewer/rca) — A1.
- `::test_cursor_names_the_prompt_file_on_every_launch` — A1, Cursor launch/resume/ask reviewer.
- `::test_a_prompt_text_command_over_the_limit_is_refused_by_every_adapter`, `::test_the_limit_is_one_argument_not_the_whole_command`, `::test_a_custom_reviewer_with_prompt_text_is_a_rerun_request_and_nothing_runs` — A2.
- `::test_worker_message_resumes_with_a_binary_only_harness_bin_reaches` (fix round) — R1: launch and `worker message` resume both run the binary only `harness_bin` reaches; plus the custom-command default-resume fallback.
- `::test_resolution_order_harness_bin_then_path_then_install_dirs`, `::test_not_found_is_a_refusal_naming_the_dirs_searched_and_harness_bin`, `::test_worker_and_reviewer_launches_run_the_resolved_binary`, `::test_a_missing_binary_refuses_every_launch_before_anything_runs` — A3.
- Updated to the new behaviour (not loosened): `test_worker_turn_check.py` cursor launch, `test_review_record_write.py` cursor reviewer argv and `prompt --channel cli` cursor reviewer, `test_prerelease_review.py` huge `"<prompt>"` now refused pre-exec.
