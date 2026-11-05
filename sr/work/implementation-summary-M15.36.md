# Implementation summary: `M15.36` — Claude Code workers never depend on the -p default mode

Branch `feature/rm-worker-launch-never-depends-on-claude-default-mode`, base `ffc8a729`, change commit `80028257`.

## What changed

- **A2 (explicit mode).** `ClaudeCode.launch` and `ClaudeCode.resume` (`specy_road/worker_adapter_claude.py`) no
  longer leave a non-bare worker to `claude -p`'s default. The mode comes from the entry's profile
  `access.launch_mode`, as before (`_cli_for`):
  - `full` (the default): `--setting-sources user,project,local` (`reviewer_auth.WORKER_FULL_FLAGS`). These are the
    sources an interactive session loads, so the worker keeps its hooks, project settings and subscription login.
    It never passes `--bare`. If Claude Code makes `--bare` the default for `-p`, a worker still runs with the
    account it uses today.
  - `bare`: `--bare`, plus `--settings <user settings path>` when only an `apiKeyHelper` authenticates it. This is
    the M15.2 reviewer helper `bare_settings_argv`, given the worker's environment. The helper command itself is
    never put on the argv.
  - `Launch.launch_mode` stays `full`/`bare`, so the started-mode check in `parse_events` is unchanged.
  - A `channels.cli` command is still run as written.
- **A1 (auth preflight).** `reviewer_auth.claude_worker_refusal(entry, profile_mode)` reuses M15.2's `forces_bare`,
  `has_api_key`, `has_api_key_helper` and `load_user_settings`, applied to the executor environment
  (`worker_environment()`). It returns one line: `worker auth: <id> forces bare mode and no ANTHROPIC_API_KEY or
  apiKeyHelper is available, so nothing was launched: export ANTHROPIC_API_KEY, configure apiKeyHelper, or drop
  launch_mode: bare to use the subscription login`.
  - `worker_ops_launch._auth_preflight` raises that line as a `WorkerError` for a claude-code entry that has no
    `channels.cli`.
  - `delegate` calls it immediately after resolving the roster entry. That is before the workers lock, before
    `--rework` terminates a completed record, and before any record, lease, prompt or log is written.
  - `worker_ops_message._send` (`worker message` and `worker resume`) calls it before the roster `preflight`,
    before the prompt file, and before the lease and spawn.
- **Decision.** A worker on a non-forced entry is **not** moved to bare when a key exists. Reviewers do move (M15.2)
  because a reviewer should load no repository context. A worker runs in the repository and needs its hooks and
  CLAUDE.md. Bare is still allowed when the entry forces it and a key or helper exists (A3, "API-key entry -> bare
  allowed"). A roster entry cannot carry `launch_mode` (the orchestration schema has `additionalProperties: false`),
  so in practice the profile's `access.launch_mode: bare` is what forces bare. `forces_bare` also honours an entry
  value, as it does for reviewers.

## Touch zones (final)

The zones were confirmed as accurate. The change touched `specy_road/worker_adapter_claude.py`,
`specy_road/worker_ops_launch.py`, `specy_road/worker_ops_message.py`, `specy_road/reviewer_auth.py` and `tests/`.
No file outside the zones was changed, and no new module was needed (file-limits OK).

Docs outside the zones (`docs/orchestration-workers.md`, `docs/orchestration-models.md`) do not yet describe the
worker's explicit `--setting-sources` flags or the `worker auth:` refusal. A docs follow-up may want to add them.

## Existing tests updated (behaviour changed by A2/A1, not loosened)

- `tests/test_worker_adapters.py::test_default_commands_follow_the_documented_cli_flags`: the launch argv is pinned
  as `claude -p --setting-sources user,project,local`, and the resume argv as `--setting-sources user,project,local
  --resume sid`. The old resume index `[2:4]` moved, because the mode flags now come first. Every original
  assertion is kept (`--session-id`, the session id, `stream-json`, stdin, and the instruction last). Two
  assertions were folded together to stay at the 400-line cap.
- `tests/test_models_and_prompt.py::test_models_show_prints_a_bad_launch_mode_and_delegate_reads_a_good_one`: the
  resume after switching the profile to bare now sets `ANTHROPIC_API_KEY`, because a forced-bare resume without a
  key is refused (A1/A3). Its assertions are unchanged. The test's two local imports were merged into one line to
  stay at the 400-line cap.

## Verification

- `python -m pytest -q tests/test_worker_claude_auth.py tests/test_worker_adapters.py tests/test_models_and_prompt.py tests/test_reviewer_auth.py tests/test_worker_turn_check.py tests/test_harness_launch.py`
- `python -m pytest -q -n 4 -p no:cacheprovider` (full suite)
- `specy-road file-limits`
- Red/green: with the `specy_road/` changes reverted, `tests/test_worker_claude_auth.py` fails 4 of 5. The API-key
  bare case already passed before the change.

## Added

- `reviewer_auth.WORKER_FULL_FLAGS`: the explicit non-bare worker flags, so `-p`'s default mode is never relied on (A2).
- `reviewer_auth.WORKER_FIXES`: the worker refusal's fix text (an API key, or the subscription login without bare) (A1).
- `reviewer_auth.worker_environment()`: the executor environment the auth check and `--settings` path read, the worker counterpart of `reviewer_environment()`.
- `reviewer_auth.claude_worker_refusal()`: the shared M15.2 auth check applied to a worker entry, returning one refusal line (A1).
- `worker_adapter_claude._worker_mode()`: chooses `--bare` (plus the helper's settings path) or the explicit setting sources for launch and resume (A2).
- `worker_ops_launch._auth_preflight()`: refuses a forced-bare claude-code worker before any state is written. It skips other harnesses and `channels.cli` entries, which are run as written (A1).
- Guard call in `worker_ops_launch.delegate`, right after the roster entry resolves (A1, before `--rework` and any record or lease).
- Guard call in `worker_ops_message._send`, the shared path of `worker message` and `worker resume` (A1/A3, resume follows the same rule).
- Test `tests/test_worker_claude_auth.py::test_launch_and_resume_name_their_mode`, parametrized over subscription, subscription with a key, and API-key bare: pins the delegate and message argv (A2/A3).
- Test `tests/test_worker_claude_auth.py::test_forced_bare_without_a_key_is_refused_before_any_worker_state`: one-line refusal, and no new file under `work/.workers` (A1/A3).
- Test `tests/test_worker_claude_auth.py::test_resume_follows_the_same_rule`: `worker message` and `worker resume` are refused once the key is gone, and nothing is written (A3).
- Fixture `account` in that file: isolates `HOME`, `CLAUDE_CONFIG_DIR` and `ANTHROPIC_API_KEY` from the developer's account (planning sheet).
- Mocks: `worker_ops.spawn` is stubbed to capture the `Launch` instead of starting a harness, the same pattern as `tests/test_harness_launch.py`.
