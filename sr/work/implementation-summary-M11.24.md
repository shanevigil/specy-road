# Implementation summary: M11.24 `worktree-handoff-writable`

Base `8d9b8f0c`; implementation commit `c155b61a`.

## Acceptance

- **A1:** a roster `channels.cli` (and a `generic` command) may name `{reviews_dir}`: `reviews_dir_into` in
  `specy_road/worker_adapters.py` replaces it with the shell-quoted main-checkout `work/reviews/<ID>` (via
  `review_files.reviews_dir`, the same resolver READY uses), for launch and resume, on every harness. Like the
  other placeholders it must be a whole word (bare or in one pair of quotes); `--add-dir={reviews_dir}` and a
  call with no leaf id/project root raise `Unsupported` and never fall back to the default command.
- **A2:** checked against `model-profiles/harness-captures/` (the captures `harness-facts.yaml` cites):
  `codex exec --help` (codex-cli 0.165.0) lists `--add-dir <DIR>` ("writable alongside the primary workspace");
  `agent --help` (2026.10.22) lists `--add-dir <path>`. In a linked worktree the default `codex exec` launch and
  the Cursor launch and resume now pass `--add-dir <reviews dir>` (one shared `Adapter._add_dir`, moved up from
  `ClaudeCode`). `codex exec resume` has no captured help listing the flag, so its default passes none and
  `docs/orchestration-workers.md` says a resumed Codex turn may not reach the hand-off directory. Tests cover
  the argv for each harness, in a linked worktree and in the main checkout.

## Also changed

- **Claude `--add-dir` order (same mechanism):** `claude --add-dir <directories...>` is variadic, and the default
  executor launch/resume put `STDIN_INSTRUCTION` straight after it, so in a linked worktree the instruction
  could be taken as a second directory (`reviewer_launch` already avoided this). `--add-dir` now comes before
  `--permission-mode`; same flags, different order.
- `role_prompt_rca.py`: the reviewer's "Writable root" line names Codex `exec` and Cursor `agent` `--add-dir`
  beside Claude Code's. The reviewer clean-tree check already says to run it in the checkout that has the
  branch, so the planning sheet's reviewer half needed no other change.
- **Reflow to stay under the 400-line cap:** `worker_adapters.py` was at 399 lines. The module docstring, the
  parser import block and four comments were rewrapped to the file's own 120-column style with no change to
  their content beyond the `{reviews_dir}` sentence; the file is 398 lines. The docs file is 399.

## Touch zones

Confirmed: `specy_road/worker_adapters.py`, `specy_road/bundled_scripts/role_prompt_rca.py`,
`docs/orchestration-workers.md`, `tests/`. Not changed, outside the zones: `specy-road prompt --channel cli`
(`bundled_scripts/role_prompt.py`) runs `substitute_prompt` itself, so a `{reviews_dir}` in a roster cli is
passed there literally; the natural home for the placeholder is `worker_adapter_parsers.py`
(`PLACEHOLDERS`/`substitute_prompt`), also outside the zones. Either is a follow-up if the maintainer wants
`prompt --channel cli` to support it.

## Verification

- `python -m pytest -q tests/test_worker_handoff_writable.py tests/test_worker_m310_reconcile_status.py tests/test_worker_adapters.py tests/test_worker_review_round2.py tests/test_review_round6_ops.py tests/test_worktree_paths_agree.py tests/test_review_files.py tests/test_worker_cli.py tests/test_worker_cli_fixes.py tests/test_models_and_prompt.py`: 192 passed.
- `specy-road file-limits`: OK. `ruff check specy_road tests scripts`: OK.
  `python scripts/check_test_private_imports.py`: 0 new.
- Red-green: `tests/test_worker_handoff_writable.py` against the base `worker_adapters.py`: 19 failed, 3 passed
  (the Claude launch, main-checkout and Codex-resume cases already held); with the change, 22 passed (21 after review round 1 dropped the claude-code launch case, E1).
- Not run: `scripts/check_clones.py` (pylint is not installed in this environment); the full `pytest` suite.

## Added

- `REVIEWS_DIR` constant (`worker_adapters.py`): the placeholder's one spelling, shared by the substitution and its error.
- `reviews_dir_into()`: substitutes `{reviews_dir}` as a whole, quoted word; called from `Adapter._custom` and the generic `launch`.
- Guard in `reviews_dir_into` raising `Unsupported` for an embedded placeholder or a missing leaf id/project root: roster input, so it is refused rather than run with literal braces or an unquoted path.
- `Adapter._add_dir()`: moved up from `ClaudeCode` (body unchanged) so Codex and Cursor reuse it; no new logic.
- `node_id` / `repo_root` keyword parameters on `Adapter._custom`: the leaf the directory is resolved for.
- `tests/test_worker_handoff_writable.py`:
  - `linked` fixture: nested project plus linked worktree (reuses `nested_project`).
  - `test_default_launch_adds_the_handoff_dir_only_in_a_linked_worktree` (codex, cursor; claude-code is the existing `test_claude_passes_add_dir_only_in_a_linked_worktree`): A2 launch argv.
  - `test_default_resume_adds_the_handoff_dir_where_the_harness_documents_it`: A2 resume argv, including Codex's documented absence.
  - `test_claude_add_dir_does_not_swallow_the_stdin_instruction`: regression for the variadic-flag order.
  - `test_custom_cli_receives_the_handoff_dir_as_one_argument` (4 harnesses × 3 quoting forms, run through `sh`): A1.
  - `test_custom_cli_resume_receives_the_handoff_dir`: A1 on resume with `{session_flag}`.
  - `test_custom_cli_reviews_dir_is_refused_when_it_cannot_be_substituted`: the two refusals.
- Mocks: none.
