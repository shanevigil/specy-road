# Implementation summary: `M15.36` — Claude Code workers never depend on the -p default mode

Branch `feature/rm-worker-launch-never-depends-on-claude-default-mode`, base `ffc8a729`, change commit `80028257`, fix-round commits `7166d20c` and the fix-round-2 commit that carries this text (after merging `origin/WIP/improvements-0-3-1`).

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
  - A roster command is still run as written; a resume that falls back to the default command takes these flags.
- **A1 (auth preflight).** `reviewer_auth.claude_worker_refusal(entry, profile_mode)` reuses M15.2's `forces_bare`,
  `has_api_key`, `has_api_key_helper` and `load_user_settings`, applied to the executor environment
  (`worker_environment()`). It returns one line: `worker auth: <id> forces bare mode and no ANTHROPIC_API_KEY or
  apiKeyHelper is available, so nothing was launched: export ANTHROPIC_API_KEY, configure apiKeyHelper, or drop
  launch_mode: bare to use the subscription login`.
  - `worker_ops_launch._auth_preflight` raises that line as a `WorkerError` for a claude-code turn that runs the
    default command (`_selected_cli`, fix round 2).
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

## Fix round 1 (`gpt-6.1-sol-low` block on `29e9ce50`)

**Finding.** On `worker message`/`resume` the auth check ran after `_wrapper_gone`. For a forced-bare worker whose
wrapper had died, a refusal still left the record marked `failed`, an `error` event appended and the lease released.

**Class.** On a launch or resume path, a refusal-capable check ran after a write to worker state (record, events,
mailbox, lease, `--rework` termination).

**Design change.**
- `worker_ops_launch._launch_checks` is the one place for every refusal that comes from the roster entry, the
  leaf, the profile and the environment: eligibility, a broken profile, the Claude Code auth check, and the roster
  `preflight` command.
- `_send` (`worker message` and `worker resume`) resolves the entry and runs `_launch_checks` once, before the first
  write on each of its paths:
  - before `_wrapper_gone` when that would write (a `running`/`starting` record whose wrapper is not alive);
  - before a message is queued for a live worker;
  - before the slot sweep in `_slot_or_existing`.
  State-only refusals that write nothing keep their earlier precedence: terminated, the usage-limit gate, a live
  turn with `--no-queue`, branch, session id. Existing tests pin that order.
- In `delegate`, the environment-only auth check still runs before anything, including the lock file.
  - `--rework` no longer terminates a completed worker in the first lock sections (`_existing_unless_rework` skips
    it). It is terminated only in the last lock section, after `_launch_checks` and the prompt build.
  - The `max_workers` cap and existing-worker answers keep their precedence over the leaf checks, as
    `test_delegate_refusals` pins.

## Fix round 2 (`gpt-6.1-sol-low` block on `72370625`)

**Finding (R1).** `_auth_preflight` skipped any entry with `channels.cli`. On `message`/`resume`, a command with no
session placeholder falls back to the default command, so a forced-bare worker with no credentials launched
unauthenticated `--bare` after writing worker state.

**Class.** The auth check read the entry's configuration while the adapter chose the command, so the two could
disagree about which command a turn runs. It failed both ways: the fallback above skipped the check, and an entry
with only `cli_resume` was refused on a resume that would run the roster's command.

**Design change.**
- `worker_ops_launch._selected_cli(entry, cli, resuming=...)` replaces `_resume_cli` and is the one answer to "which
  roster command does this turn run, or `None` for the default". `_auth_preflight` asks it, and `_send` passes its
  result to the adapter, so the command checked is the command run.
- The session-placeholder test is the existing `resume_form_note` rule, not a new parser. `worker_adapter_base.py`
  is outside the touch zones, so `Adapter._custom` keeps its own guard; on this path it now only sees commands that
  already passed `_selected_cli`.
- `_launch_checks` takes `resuming`; `_send`'s single `entry_checked()` passes `True`, so the dead-wrapper, queue and
  resume paths all use the resume rule.

**Bounded rule and limit (in `_auth_preflight`'s docstring).** The default command is checked. A roster command is
run as written and never parsed, so a `--bare` written into it is the adopter's to authenticate.

## Probes

- `_send`, dead wrapper plus forced bare with no key: refused before `_wrapper_gone`. The record, events, mailbox
  and lease refs are byte-identical, and the state stays `running`. Covered by the new assertion in
  `test_resume_follows_the_same_rule`, which fails on `29e9ce50`.
- `_send`, idle worker and forced bare with no key: refused, nothing written (unchanged test).
- `_send`, live worker and queued message: `_launch_checks` now runs before `queue_worker_message`, so a refused
  message is not queued. Before this change the queue path ran no checks.
- `_send`, slot sweep (`_slot_or_existing` closes dead wrappers on any leaf): the checks now run before it. Before
  this change, eligibility and preflight ran after it.
- `_send`, `_cli_for` profile error after the prompt file is written: a broken profile is now refused earlier by
  `_launch_checks`.
- `_send`, terminated, usage limit, session-id metacharacters: no write precedes them, so their order is kept
  (`test_review_round6_ops`, `test_worker_turn_check` pass).
- `delegate`, auth: runs before `work/.workers/.lock` is created (`test_forced_bare_without_a_key_is_refused_before_any_worker_state`).
- `delegate --rework`, failing roster preflight: the completed record and its files are unchanged. Covered by the
  new `test_a_refused_rework_leaves_the_completed_worker_as_it_was`, which fails on `29e9ce50`.
- `delegate`, dead-wrapper sweep in the early lock sections: still runs before the leaf checks. The cap and
  existing-worker refusals depend on it, and their precedence over the claim check is pinned by
  `test_worker_cli.py::test_delegate_refusals`. It records only processes that are already dead, which is the same
  write `worker status` and `sync` make. It is not a write this launch causes.
- `_launch_locked`: worktree, nested-repo and env setup, and the dirty-tree refusal all come before the prompt,
  record, lease and spawn. `_cli_for`'s profile refusal is now pre-empted by `_launch_checks`.
- Reviewer launch paths (M15.2) and other harnesses: out of scope, not changed.

Fix round 2:

- `message`/`resume`, `channels.cli` with no session placeholder, forced bare, no key: refused, worker files and lease refs byte-identical, for an idle worker and a dead wrapper. Fails on `72370625`.
- Same worker once the key is back: the turn runs `claude -p --bare ... --resume`, so the refused command is the default one.
- `message`, `channels.cli` naming `{session_flag}`, forced bare, no key: runs the roster command, no refusal.
- `message`, `cli` with no session plus `cli_resume` naming one: runs `cli_resume`, no refusal.
- `message`, `cli_resume` only: runs it, no refusal. Fails on `72370625`, which refused it (the opposite direction of R1).
- `delegate`, `cli_resume` only, forced bare, no key: refused, since the launch runs the default command.
- `delegate`, `channels.cli`, forced bare, no key: runs as written.
- `cli_resume` with no session placeholder: the schema refuses it at config load (`orchestration config: ...does not match`), so it never reaches a launch. `_selected_cli` called directly returns `None` for it.
- Queued message to a live worker: uses the same `entry_checked()` call, so it takes the resume rule. By reading only; no test drives a live wrapper.
- Other `adapter.resume` / `adapter.launch` callers: only `review_delegate.py` (reviewers, out of scope) and `_send` / `_launch_locked`. The queue delivers through `_send`.
- Codex and Cursor resumes: `_custom` returned `None` for the same commands, so they get the default command as before.
- One change on Cursor: a session-less command with `-w`, added to the roster after the launch, used to be refused on resume; it now takes the default fallback. That command is not run and the default passes `--workspace`, so nothing unsafe runs. `delegate` still refuses it.
- Not fixed: an unrunnable roster command (`placeholder_problem`, oversized argv) is still refused by the adapter after `_wrapper_gone` and the prompt write on resume. It launches nothing and predates this leaf; moving it would change `worker_adapter_base.py`, outside the touch zones.
- `forces_bare` also reads an entry `launch_mode`, which `_cli_for` does not; the schema refuses that key on a roster entry, so the two cannot differ.

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
  bare case already passed before the change. Fix round: on `29e9ce50`'s `specy_road/`, the two fix-round tests fail
  and the other 4 pass. Fix round 2: on `72370625`'s `specy_road/`, 2 of the 11 tests fail (`test_resume_follows_the_same_rule[channels1]`, `test_a_resume_on_a_roster_command_is_run_as_written[channels2]`).

## Added

- `reviewer_auth.WORKER_FULL_FLAGS`: the explicit non-bare worker flags, so `-p`'s default mode is never relied on (A2).
- `reviewer_auth.WORKER_FIXES`: the worker refusal's fix text (an API key, or the subscription login without bare) (A1).
- `reviewer_auth.worker_environment()`: the executor environment the auth check and `--settings` path read, the worker counterpart of `reviewer_environment()`.
- `reviewer_auth.claude_worker_refusal()`: the shared M15.2 auth check applied to a worker entry, returning one refusal line (A1).
- `worker_adapter_claude._worker_mode()`: chooses `--bare` (plus the helper's settings path) or the explicit setting sources for launch and resume (A2).
- `worker_ops_launch._auth_preflight()`: refuses a forced-bare claude-code turn on the default command. It skips other harnesses and roster commands, which are run as written (A1).
- `worker_ops_launch._selected_cli()` (fix round 2): replaces `worker_ops_message._resume_cli`; the one answer to which command a launch or resume runs, read by the auth check and the adapter call (A1).
- `resuming` keyword on `_auth_preflight` and `_launch_checks` (fix round 2): a resume is checked on its own command.
- `worker_ops_launch._launch_checks()` (fix round): eligibility, a broken profile, auth and the roster preflight in one place, run before any worker-state write on delegate and resume.
- `worker_ops_launch._existing_unless_rework()` (fix round): the early lock sections ignore a completed worker under `--rework` without terminating it, so the termination waits for the last section, after every refusal.
- Guard call in `worker_ops_launch.delegate`: `_auth_preflight` right after the roster entry resolves, before the lock file; `_launch_checks` before the prompt build and the last lock section (A1).
- `entry_checked()` closure in `worker_ops_message._send` (fix round): resolves the entry and runs `_launch_checks` once, before the dead-wrapper close, the queue or the slot sweep, whichever comes first (A1/A3).
- Branch in `_send` (fix round): `rec.state in (running, starting) and not wrapper_alive(...)` runs the checks before `_wrapper_gone` would write.
- Test `tests/test_worker_claude_auth.py::test_launch_and_resume_name_their_mode`, parametrized over subscription, subscription with a key, and API-key bare: pins the delegate and message argv (A2/A3).
- Test `tests/test_worker_claude_auth.py::test_forced_bare_without_a_key_is_refused_before_any_worker_state`: one-line refusal, and no new file under `work/.workers` (A1/A3).
- Test `tests/test_worker_claude_auth.py::test_resume_follows_the_same_rule`: `worker message` and `worker resume` are refused once the key is gone, for an idle worker and for one whose wrapper died. Record, events and lease are byte-identical (A3, fix round).
- Test `tests/test_worker_claude_auth.py::test_a_resume_on_a_roster_command_is_run_as_written` (fix round 2): a resume on a roster command needs no key.
- Test `tests/test_worker_claude_auth.py::test_a_launch_is_checked_on_its_own_command` (fix round 2): `cli_resume` does not exempt a launch; `channels.cli` does.
- Helpers `_channels` and `_delegated` in that test file (fix round 2): the roster YAML, and an idle worker whose key is gone. `test_resume_follows_the_same_rule` is now parametrized over the default command and a session-less `channels.cli`.
- Test `tests/test_worker_claude_auth.py::test_a_refused_rework_leaves_the_completed_worker_as_it_was` (fix round): a `--rework` refused by the roster preflight leaves the completed worker untouched.
- Helper `_files` in that test file: snapshots every file under `work/.workers` byte for byte, plus local and remote lease refs (fix round: "byte-identical").
- Fixture `account` in that file: isolates `HOME`, `CLAUDE_CONFIG_DIR` and `ANTHROPIC_API_KEY` from the developer's account (planning sheet).
- Mocks: `worker_ops.spawn` is stubbed to capture the `Launch` instead of starting a harness, the same pattern as `tests/test_harness_launch.py`.
