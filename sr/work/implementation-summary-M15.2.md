# M15.2 — Claude Code reviewer: bare only with a key, explicit otherwise

A Claude Code reviewer no longer always launches `--bare`. `specy_road/reviewer_auth.py` decides the mode once for `review delegate` and `prompt --channel cli`: bare only when the reviewer's environment has `ANTHROPIC_API_KEY` or the user settings bare mode reads define `apiKeyHelper`; otherwise explicit (`--setting-sources user --strict-mcp-config`, no `--mcp-config`). The RUN record and the filed REVIEW carry `launch_mode` `bare` or `explicit`. Explicit argv keeps `--disallowedTools`, `--json-schema` and `--add-dir`, and never contains `--bare`.

A profile `access.launch_mode: bare` or a roster entry `launch_mode: bare` forces bare. With neither credential, both commands refuse before launch (exit 1) and name the fixes: export `ANTHROPIC_API_KEY`, configure `apiKeyHelper`, or let specy-road choose explicit mode. `orchestrate plan` prints one `reviewer auth:` notice per such claude-code reviewer entry, on the first assignment that staffs it. The key's value is never printed or logged. There is no network authentication probe, and other harnesses are unchanged.

## Touch zones

Confirmed and used: `specy_road/reviewer_auth.py` (new), `specy_road/worker_adapter_claude.py`, `specy_road/review_delegate.py`, `specy_road/bundled_scripts/role_prompt_cli.py`, `specy_road/orchestrate_plan.py`, `docs/orchestration-reviewer-output.md`, `docs/orchestration-models.md`, `docs/orchestration-workers.md`, `tests/test_reviewer_auth.py` (new), `tests/test_review_files.py`.

Left unchanged, outside the zones:

- `specy_road/bundled_scripts/role_prompt.py` opens the RUN record before the channel returns, and M15.3 owns that file. `close_cli_review_run` deletes that file when the outcome reason starts with `reviewer auth:`, so the command ends with no RUN record.
- `specy_road/bundled_scripts/orchestrate_cli.py` already prints each assignment note. The plan notice is one of those notes.
- `specy_road/review_record_write.py` already copies `launch.launch_mode` onto the filed REVIEW. The prompt path sets the same field on the in-memory run before close.

`docs/orchestration-workers.md` is at the project file-limit (400 lines in `sr/constraints/file-limits.yaml`). The `billing_route` sentence is a comment on the existing roster line. The mode rules and when `channels.cli` is still needed are in `docs/orchestration-models.md` (next to that label) and `docs/orchestration-reviewer-output.md`.

## Added

### Helpers

- `reviewer_environment` — the reviewer harness environment the mode and the notices read, so a developer key in the process environment is the one the launch would see.
- `user_settings_path` — `CLAUDE_CONFIG_DIR/settings.json`, else `HOME/.claude/settings.json`, else `claude_config_dir()`, the file bare mode's `apiKeyHelper` comes from.
- `load_user_settings` — that file as an object, or `{}` when it is missing or not JSON, without logging it.
- `has_api_key` — a non-whitespace `ANTHROPIC_API_KEY`, without returning the value.
- `has_api_key_helper` — a non-empty string `apiKeyHelper`, without returning the command.
- `claude_reviewer_mode` — bare only with a key or helper; otherwise explicit.
- `auth_problem` — the refusal text when bare was forced and neither credential exists; `None` otherwise.
- `forces_bare` — a roster `launch_mode: bare` or a profile `access.launch_mode: bare`.
- `claude_launch_decision` — `(mode, refusal)` shared by both entry points.
- `claude_default_reviewer` — that decision plus the note `review delegate` prints.
- `launch_note` — the bare note (the previous prompt sentence) or the explicit-mode note, both of which mention the subscription login.
- `claude_reviewer_auth_notices` — one `reviewer auth:` line per forced, unauthenticated claude-code reviewer entry, skipping `channels.cli` and non-reviewers.
- `stamp_reviewer_auth_notices` — attaches each notice to the first assignment that staffs that roster id, so the existing plan renderer prints it once.
- `_run_launch_mode` — carries the decided mode from `run_default_reviewer` to `close_cli_review_run`, which writes it on the RUN record.
- `_isolate` — drops `ANTHROPIC_API_KEY` and points `CLAUDE_CONFIG_DIR` at an empty directory so the developer's login cannot flip the mode.
- `_force_bare` — sets the pinned profile's `launch_mode` to `bare` and commits it, the way a roster forces bare.
- `_fake_claude` — a `claude` on `PATH` that records argv and exits, so a launch is observable without replacing `Popen` (git still uses the real one).
- `_argv` — the argv lists that fake recorded, or none when it was never started.

### Branches and guards

- `reviewer_launch` auth flags — `mode="explicit"` adds `--setting-sources user --strict-mcp-config` and records `launch_mode` `explicit`; any other mode stays `--bare`. The default remains bare so existing direct callers keep their argv.
- `parse_events` inferred-mode check — a mismatch is reported only when `launch_mode` is `bare` or `full`. Explicit is a reviewer mode the tool list cannot infer, so a reviewer turn is not failed for it.
- `delegate` refusal — `DelegateError` before the review-run lock, the prompt files and `save_run`, so no RUN record is opened.
- `delegate` note — after preflight, prints the same bare or explicit note `prompt` prints.
- `run_reviewer_channel` refusal — for a default claude-code reviewer, refuses before preflight and before launch.
- `run_default_reviewer` refusal — the same decision again, so a direct caller does not launch either, and sets the mode the RUN record will carry.
- `close_cli_review_run` unlink — when the filed reason starts with `reviewer auth:`, removes the RUN file `role_prompt` already opened and returns without writing the log.
- `claude_reviewer_auth_notices` skip — returns nothing when a key or helper exists, and skips entries that are not a forced claude-code reviewer without `channels.cli`.

### Mocks

- PATH `claude` in `_fake_claude` — stands in for the harness process in the delegate tests. A `Popen` patch was not used: it also replaced git's `Popen`.

### Tests

- `test_bare_is_never_chosen_without_a_key_or_helper` — empty, whitespace and non-string credentials select explicit; a key or a helper string selects bare.
- `test_auth_problem_names_the_fixes_and_never_the_key` — the refusal names the three fixes and does not contain the key.
- `test_each_mode_keeps_the_restrictions_and_explicit_argv_has_no_bare` — both modes keep `--disallowedTools`, `--json-schema` and `--add-dir`; explicit argv has no `--bare` and no `--mcp-config`.
- `test_notices_are_one_per_forced_claude_reviewer` — one notice per forced claude-code reviewer, none for codex, `channels.cli`, an unforced entry, or an executor, and none once a key or helper exists.
- `test_delegate_explicit_without_a_key_records_the_mode_and_prints_the_note` — `review delegate` records `explicit`, launches without `--bare`, and prints the subscription-login note.
- `test_delegate_bare_with_a_key_prints_the_note_and_hides_the_key` — a key selects bare, the note is printed, and the key is absent from stderr, the run, the argv record and the log.
- `test_forced_bare_without_a_key_refuses_before_a_run_record` — `review delegate` and `prompt --channel cli` exit 1, name the fixes, launch nothing and leave no RUN file.
- `test_prompt_explicit_mode_is_recorded_and_a_helper_selects_bare_without_printing_it` — the prompt path records `explicit` without a key, and an `apiKeyHelper` selects bare without the helper command appearing in the output.
- `test_plan_prints_one_reviewer_auth_notice` — `orchestrate plan` prints one `reviewer auth:` line naming the entry and the fixes, and prints none once a key is set.
- `test_claude_code_reviewer_without_channels_cli_runs_bare` (extended) — sets a key and an empty config dir so the pinned bare argv stays deterministic, and asserts the key is absent from the output and the run.
