# M15.2 — Claude Code reviewer: bare only with a key, explicit otherwise

A Claude Code reviewer no longer always launches `--bare`. `specy_road/reviewer_auth.py` decides the mode once for `review delegate` and `prompt --channel cli`: bare only when the reviewer's environment has `ANTHROPIC_API_KEY` or the user settings bare mode reads define `apiKeyHelper`; otherwise explicit (`--setting-sources user --strict-mcp-config`, no `--mcp-config`). When the helper is the only credential, bare mode passes `--settings` with that file's path, never the helper command. The RUN record and the filed REVIEW carry `launch_mode` `bare` or `explicit`. Explicit argv keeps `--disallowedTools`, `--json-schema` and `--add-dir`, and never contains `--bare`.

A profile `access.launch_mode: bare` or a roster entry `launch_mode: bare` forces bare. With neither credential, both commands refuse before launch (exit 1) and name the fixes: export `ANTHROPIC_API_KEY`, configure `apiKeyHelper`, or let specy-road choose explicit mode. `orchestrate plan` prints one `reviewer auth:` notice per such claude-code reviewer entry, on the first assignment that staffs it. The key's value is never printed or logged. There is no network authentication probe, and other harnesses are unchanged.

## Touch zones

Confirmed and used: `specy_road/reviewer_auth.py` (new), `specy_road/worker_adapter_claude.py`, `specy_road/review_delegate.py`, `specy_road/bundled_scripts/role_prompt_cli.py`, `specy_road/bundled_scripts/role_prompt.py` (the only caller of `open_reviewer_cli_run`; the refusal has to run before that call), `specy_road/orchestrate_plan.py`, `docs/orchestration-reviewer-output.md`, `docs/orchestration-models.md`, `docs/orchestration-workers.md`, `tests/test_reviewer_auth.py` (new), `tests/test_review_files.py`, `tests/review_repo_helpers.py`.

Left unchanged, outside the zones:
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
- `bare_settings_argv` — `--settings` plus the user-settings path when bare auth is a helper and not a key; never the helper command, and never a JSON `--settings` value.
- `claude_reviewer_mode` — bare only with a key or helper; otherwise explicit.
- `reviewer_launch_block` — the forced-bare authentication refusal only. It writes nothing and runs before the lock. The roster preflight is not part of it.
- `auth_problem` — the refusal text when bare was forced and neither credential exists; `None` otherwise.
- `forces_bare` — a roster `launch_mode: bare` or a profile `access.launch_mode: bare`.
- `claude_launch_decision` — `(mode, refusal)` shared by both entry points.
- `claude_default_reviewer` — that decision plus the note `review delegate` prints.
- `launch_note` — the bare note (the previous prompt sentence) or the explicit-mode note, both of which mention the subscription login.
- `claude_reviewer_auth_notices` — one `reviewer auth:` line per forced, unauthenticated claude-code reviewer entry, skipping `channels.cli` and non-reviewers.
- `stamp_reviewer_auth_notices` — attaches each notice to the first assignment that staffs that roster id, so the existing plan renderer prints it once.
- `_run_launch_mode` — carries the decided mode from `run_default_reviewer` to `close_cli_review_run`, which writes it on the RUN record.
- `claude_code_reviewer_repo` — public fixture in `tests/review_repo_helpers.py` (moved from a `_`-prefixed function in `tests/test_review_files.py`) so both the launch-argv tests and the reviewer-auth tests share it without importing a private name.
- `_isolate` — drops `ANTHROPIC_API_KEY` and points `CLAUDE_CONFIG_DIR` at an empty directory so the developer's login cannot flip the mode.
- `_force_bare` — sets the pinned profile's `launch_mode` to `bare` and commits it, the way a roster forces bare.
- `_fake_claude` — a `claude` on `PATH` that records argv and exits, so a launch is observable without replacing `Popen` (git still uses the real one).
- `_argv` — the argv lists that fake recorded, or none when it was never started.
- `_reviews` — the reviews directory's file bytes, so a refusal is compared against the directory it started with.

### Branches and guards

- `reviewer_launch` auth flags — `mode="explicit"` adds `--setting-sources user --strict-mcp-config` and records `launch_mode` `explicit`. Any other mode is `--bare`, plus `bare_settings_argv()` when the helper is the only credential. The default remains bare so a caller that does not pass a mode stays bare.
- `parse_events` inferred-mode check — a mismatch is reported only when `launch_mode` is `bare` or `full`. Explicit is a reviewer mode the tool list cannot infer, so a reviewer turn is not failed for it.
- `delegate` auth refusal — `DelegateError` before the review-run lock, the prompt files and `save_run`.
- `delegate` preflight — `_preflight` after the lock and before `save_run`, where M8.3 left it.
- `delegate` note — after the prompt is built, prints the same bare or explicit note `prompt` prints.
- `prompt` auth refusal — `reviewer_launch_block` in `main`, before the lock and before `open_reviewer_cli_run`.
- `prompt` preflight — `preflight` inside `run_reviewer_channel`, after the RUN record is open, so a failure is closed as an incomplete `prompt-cli` run.
- `run_reviewer_channel` auth — a direct caller hits the same block before `write_schema` or a launch. `prompt` passes `prechecked` so that check does not run again after the record exists.
- `run_default_reviewer` refusal — the same decision again, so a direct caller does not launch either, and sets the mode the RUN record will carry.
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
- `test_forced_bare_without_a_key_refuses_before_a_run_record` — `review delegate` and `prompt --channel cli` exit 1, name the fixes, launch nothing, and leave a planted RUN record and the rest of the reviews directory byte for byte.
- `test_prompt_explicit_mode_is_recorded_and_a_helper_selects_bare_without_printing_it` — the prompt path records `explicit` without a key. With only an `apiKeyHelper`, `reviewer_launch` and the launched argv pass `--settings` and that file's path, and the helper command is absent from the argv, the displayed `running:` line, and the log.
- `test_a_forced_bare_auth_refusal_leaves_the_reviews_dir_unchanged` — forced bare with no key refuses `review delegate` and `prompt --channel cli` without changing a planted RUN record or any other file in the reviews directory. A roster preflight is not this case.
- `test_plan_prints_one_reviewer_auth_notice` — `orchestrate plan` prints one `reviewer auth:` line naming the entry and the fixes, and prints none once a key is set.
- `test_claude_code_reviewer_without_channels_cli_runs_bare` (extended) — sets a key and an empty config dir so the pinned bare argv stays deterministic, and asserts the key is absent from the output and the run.

## Probes

R1 class: bare mode was selected because user settings define `apiKeyHelper`, but the launched argv did not pass that helper through `--settings`, so Claude never received it. Passing the helper as a JSON `--settings` value would also print the command.

- `ClaudeCode.reviewer_launch` is the only builder of that argv, and both `review delegate` and `run_default_reviewer` call it. Result: `--settings` plus the user-settings path is added there, so both entry points get it.
- Explicit mode, and bare mode when `ANTHROPIC_API_KEY` is set. Result: no `--settings`. The key is the environment; explicit mode uses `--setting-sources user`. The pinned bare argv test still matches.
- A `channels.cli` reviewer. Result: the command runs as written. It is not this launcher, so it gets no `--settings` from the mode decision.
- The displayed command (`_shown` / `running:`) and the RUN log. Result: both print the argv. The argv holds the path, not the helper command. The prompt test asserts the command is absent from the argv, stderr, stdout and the log.
- `--settings`'s JSON-string form. Result: not used.

R2 class: a forced-bare authentication refusal ran after a reviews-directory file was written.

- `open_reviewer_cli_run` has one caller, `role_prompt._run`. Result: `reviewer_launch_block` runs in `main` before the lock and before that call. An auth refusal returns without creating or replacing a file. The test plants a RUN record and compares the directory.
- `close_cli_review_run` used to unlink a RUN opened before the auth check. Result: removed. Auth never opens the record, so nothing is deleted.
- A direct `run_reviewer_channel` caller. Result: the same auth block runs first, before `write_schema` or a launch. `prompt` passes `prechecked` so the check does not run again after the record exists.
- `review delegate` auth. Result: `DelegateError` before the lock and before `save_run`.
- Prompt building writes `PACKET-<model>.md` only for a delta review. Result: that write is after the auth block has allowed the launch. A non-delta auth refusal does not reach it.

R3 class: an existing refusal that already filed an incomplete `prompt-cli` RUN was moved before the record was opened. A failed roster preflight is that case. Forced-bare auth is not.

- `prompt --channel cli` roster preflight. Result: it runs in `run_reviewer_channel` after `open_reviewer_cli_run`. `close_cli_review_run` still files `source` `prompt-cli`, `state` `incomplete`, `outcome` `rerun`, and a `reviewer-failure` event. `test_prompt_cli_that_sends_nothing_stays_incomplete_beside_an_older_record_of_the_commit` is unchanged and covers the preflight parameter.
- The same test's interrupt parameter. Result: the interrupt still closes the record `role_prompt` opened. That path was not moved.
- A missing or malformed cli, and `reviewer_cli` refusing the command, on the prompt path. Result: they stay in `run_reviewer_channel` and `run_custom_reviewer`, after the record is open, as M8.3 had them.
- `review delegate` roster preflight. Result: `_preflight` is after the lock and before `save_run`, its M8.3 place. It raises before a RUN json is saved. The incomplete-record behaviour the closure test pins is the prompt path.
- `review delegate` `reviewer_cli`. Result: only the call inside `launch`, after `save_run`. The earlier check before the lock was removed.
- `run_cli_channel` for a non-reviewer. Result: unchanged. It never opened a reviewer RUN; its preflight still returns before the process starts.
- Forced-bare auth on both entry points. Result: still before the lock and before any RUN. The retargeted test compares the reviews directory for that refusal only.
