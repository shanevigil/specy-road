# Implementation summary: M11.23 — a custom launch command's permissions carry through resume

Branch `feature/rm-resume-keeps-permissions`, merged with `origin/WIP/improvements-0-3-1` at 54aaaff7 (the zones that name the post-split modules).

## What changed

- **A1 — `channels.cli_resume`.** New optional roster field (schema: a string that must name `{session}` or `{session_flag}`). `worker message` / `resume` run it in place of the launch command (`worker_ops_message._resume_cli`, called in `_send` right after `_cli_for`), through the adapter's unchanged `resume` → `_custom` path, so `{session}`, `{effort}`, `{reviews_dir}` and `{prompt}` work as in `channels.cli`. That gives Codex (`codex exec resume …`) and Cursor (`agent -p --resume …`), where `{session_flag}` is refused, a resume that keeps the launch's flags. I implemented `cli_resume` only, not the alternative `extra_args`: A1 offers them as alternatives, and `extra_args` would have needed the Codex and Cursor adapter files, which are not in the zones. "Both fields" is tested as `channels.cli` (launch argv) and `channels.cli_resume` (resume argv), on Codex and Cursor. Claude Code is tested with the documented `{session_flag}` command.
- **A2 — reports before launch.** `worker_ops_launch._report_cli`, called in `_launch_locked` after `_cli_for`, prints to stderr before the spawn:
  - `resume_form_note` (a warning), only on a harness that can resume: the launch command (roster `channels.cli`, or the profile `access.cli` that `_cli_for` returns) names no session placeholder and the roster sets no `cli_resume`, so resumes would run the default command with the default's permissions.
  - `output_mode_note`: a command that visibly runs `claude` / `agent` / `cursor-agent` in print mode without `--output-format stream-json`, or `codex exec` without `--json`. It suggests the stream-json (or `--json`) form. Wrapper scripts are not looked into. This applies to both `cli` and `cli_resume`.
  
  These are reports, not refusals. The existing behaviour (the documented launch-only command, and `tests/test_worker_adapters.py::test_delegate_passes_the_executor_effort_to_default_and_custom_commands`, which delegates with `wrapper {prompt}`) keeps working. The resume fallback is no longer silent.
- **A3** — `docs/orchestration-workers.md`, "A hands-off Claude Code executor": a settings JSON with allow and deny lists (no bare `Edit` / `Write` allow) and the `channels.cli` line `claude -p --output-format stream-json --verbose {effort} --permission-mode acceptEdits --settings ~/.config/specy-road/claude-worker.json --add-dir {reviews_dir} {session_flag} < {prompt}`. It also warns that a bare `Edit` allow in `dontAsk` mode lets a worker write anywhere (the main checkout included), and that relative deny rules cover only the worker's own worktree.
- **A4** — the test parses that JSON block from the doc and checks that `deny` holds `Bash(git push *)` and `Bash(gh pr *)`, and that `allow` has no bare `Edit` / `Write`.
- **A5** — the "Permissions." paragraph now says a `-p` denial does not stop the run: it shows as `permission_denied` and in `permission_denials`, and the turn exits 0. This is the fact already recorded in `model-profiles/harness-facts.yaml` from the M8.7 run. "may stop at a shell permission" is gone from the doc and from the `worker_adapters.py` docstring. Installation check 1 becomes "Permission denials". The deny list uses the prefix form. A test asserts that the default Codex resume argv repeats every `-c` launch flag (policy and effort).
- The roster example in the doc gains `cli_resume` examples for Codex and Cursor.

## Line budget

`docs/orchestration-workers.md` was at 398 of 400 lines. To fit the additions I joined three nearby paragraphs, each onto one line, with their wording unchanged: "Claude and `{session}`", "Permissions in the harness's settings file", and "It looks for Claude Code's own transcript…". No text was removed. It is now 400 lines, and `specy-road file-limits` passes. Every touched `.py` file stays under the cap (parsers 239, ops_launch 236, ops_message 97). No new module was needed.

## Touch zones (final)

Files edited: `specy_road/worker_adapter_parsers.py`, `specy_road/worker_ops_launch.py`, `specy_road/worker_ops_message.py`, `specy_road/worker_adapters.py` (docstring only), `specy_road/templates/project/schemas/orchestration.schema.json`, `docs/orchestration-workers.md`, `tests/test_worker_resume_permissions.py`.

Not needed in the end: `worker_adapter_base.py`, `worker_adapter_claude.py`, `worker_ops.py`, `bundled_scripts/worker_cli.py`.

Not touched (outside the zones): `sr/schemas/orchestration.schema.json`, the toolkit roadmap's own copy of the schema. It does not use `cli_resume`, and `refresh-schemas` updates it.

## Verification

- `python -m pytest tests/test_worker_resume_permissions.py -q` → 14 passed.
- Red-green: with the pre-change `worker_ops_launch.py`, `worker_ops_message.py` and schema, 7 of those 14 fail (exit 1).
- `python -m pytest -n auto -q tests/test_worker_*.py tests/test_review_delegate.py tests/test_review_round6_policy.py tests/test_review_round6_ops.py tests/test_orchestration*.py` → 294 passed.
- `python -m pytest -n auto -q` (full suite) → 3316 passed, 2 skipped, exit 0. An earlier run was stopped by a 600 s `timeout` wrapper at 99%; it showed two failures, which went unidentified because the run was cut off. The clean rerun is the one recorded.
- `specy-road file-limits` → OK.

## Added

- `worker_adapter_parsers.resume_form_note` — the A2 warning text for a launch command a resume cannot reuse (pure function, so it is unit-tested apart from delegate).
- `worker_adapter_parsers._JSON_FORMS` — per binary: the print-mode words and the JSON-stream form `output_mode_note` checks for and suggests.
- `worker_adapter_parsers._output_format` — reads `--output-format X` / `--output-format=X` from a command's words.
- `worker_adapter_parsers.output_mode_note` — the A2 note for a visible print-mode command with text output.
- `worker_ops_launch._report_cli` — prints both reports before the launch; the resume-form one only when the harness's adapter can resume (generic cannot, so nothing falls back there).
- `worker_ops_message._resume_cli` — `channels.cli_resume` when set, else the launch command (A1).
- Schema guard `channels.cli_resume.pattern` `\{session(_flag)?\}` — a `cli_resume` with no session placeholder is refused when the config loads, so it can never fall back silently itself.
- Mock: `ops.spawn` patched to record the `Launch` in the new tests (as the existing delegate tests do), so the argv is checked without running a harness.
- `tests/test_worker_resume_permissions.py`:
  - `test_codex_cli_resume_keeps_the_launch_policy` — A1, Codex launch and resume argv.
  - `test_cursor_cli_resume_keeps_the_launch_flags` — A1, Cursor launch and resume argv.
  - `test_the_documented_hands_off_claude_cli_keeps_its_settings_on_resume` — A1/A3: the documented line passes the placeholder guard and keeps `--settings` / `acceptEdits` on launch and resume.
  - `test_the_documented_settings_parse_and_deny_push_with_no_bare_edit_allow` — A4/A3/A5 (the JSON parses, deny covers `git push` and `gh pr`, no bare `Edit` / `Write` allow, the old stop wording is gone).
  - `test_cli_resume_must_name_a_session_placeholder` — the schema guard.
  - `test_delegate_warns_when_a_resume_would_fall_back_to_the_default` (5 cases) — A2 resume-form report.
  - `test_delegate_notes_a_text_only_command` — A2 text-output report through delegate.
  - `test_output_mode_note_reads_only_visible_print_mode_commands` — A2 detection, including what stays quiet.
  - `test_resume_form_note_only_for_a_launch_command_with_no_resume_form` — A2 unit test.
  - `test_codex_default_resume_repeats_every_launch_policy_flag` — A5.
