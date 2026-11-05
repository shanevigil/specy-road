# Implementation summary: M16.69 — Cursor workers launch sandboxed without --force unless the roster opts in

Branch `feature/rm-cursor-workers-no-force-by-default`, base `7f3cc488`, change commit `62984c74`.

## What changed, per acceptance line

**A1 — default argv and the opt-in field.**
- `specy_road/worker_adapter_cursor.py`: `Cursor.launch` and `Cursor.resume` take `force: bool = False` and pass
  `permission_flags(force)`: `--trust --sandbox enabled` by default, `--trust --force` (no `--sandbox`) when
  `force` is true. A `channels.cli` / `cli_resume` command is unchanged (it keeps its own argv). The reviewer
  command (`--mode ask --trust`) is unchanged.
- Roster field `cursor_force` (boolean, default false) in
  `specy_road/templates/project/schemas/orchestration.schema.json`, documented there.
- `specy_road/worker_ops_launch.py`: `launch_options(entry, harness)` turns `cursor_force` into the adapter's
  `force` keyword for `cursor` only (the Claude and Codex adapters take no such keyword and are untouched);
  `delegate` (launch) and `worker_ops_message._send` (`message` / `resume`) both pass it, so launch and resume agree.
- `specy_road/worker_runner.py`: a Cursor worker's `launched` event has `detail.permissions`, the permission
  flags the argv actually passes (`launch_permissions`, which also reads a custom `sh -c` command's words).

**A2 — real-CLI verification (recorded here, as required).**
- Host: Ubuntu 24.04.5 LTS, `kernel.apparmor_restrict_unprivileged_userns = 1`; agent `2026.11.05-86047df`
  (`/home/savigil/.local/bin/agent`); model `composer-2.5`.
- Fresh linked worktree: `git worktree add -b smoke/m16-69-sandbox /tmp/m1669-smoke HEAD`, then
  `agent create-chat` in it. Prompt file `/tmp/m1669-prompt.md`: (1) append `# m16.69 sandbox smoke` to
  `tests/test_harness_launch.py`; (2) `python -m pytest -q -p no:cacheprovider tests/test_harness_launch.py`;
  (3) `git add tests/test_harness_launch.py && git commit -m "smoke: m16.69 sandbox commit"`.
- New default, exactly the adapter's argv shape:
  `agent -p --resume <chat> --output-format stream-json --trust --sandbox enabled --model composer-2.5 --workspace /tmp/m1669-smoke "<instruction naming the prompt file>"`
  → **exit 1 before any event; no edit, no pytest, no commit**:
  `Error: Sandbox mode is enabled but not available on this system. Sandbox failed to start, possibly due to AppArmor configuration. Visit https://cursor.com/docs/agent/terminal for troubleshooting steps.` /
  `Run 'agent sandbox disable' to switch to allowlist mode.`
- Opt-in path, same worktree and prompt, `--trust --force` instead: exit 0; edit succeeded; pytest exit 0
  (`21 passed in 1.63s`); `git commit` exit 0 (`[smoke/m16-69-sandbox f45bd3cc] … 1 file changed`).
- The smoke worktree and branch were removed afterwards.
- As A2 directs: the default stays sandboxed; the limitation and the opt-in are documented
  (docs/orchestration-workers.md, Permissions paragraph, and CHANGELOG); the toolkit's Composer/Grok executor
  entries `composer-2.5` and `grok-4.7-exec` get `cursor_force: true` in `sr/roadmap/orchestration.yaml`, and
  the temporary exception is decision **D8** in `sr/roadmap/decisions.yaml` (added with `specy-road decisions
  add`; **open**, recommendation `keep`, default `keep`, for the maintainer to confirm).
- **Coordinator note:** the toolkit's third Cursor executor, `claude-opus-5-5-high`, is not a Composer/Grok
  entry, so it was not opted in; on this host it now fails at launch with the error above until the sandbox
  works or the maintainer adds `cursor_force: true` to it too.

**A3 — warnings and visible opt-in.**
- `force_warnings(roster)` (worker_adapter_cursor.py): one `! cursor --force: <id> (...)` line per `cursor`
  entry, assigned or not, with `cursor_force: true` or with a `channels.cli` / `cli_resume` containing
  `--force` or `--yolo`; it names the entry, how it opts in, and the risk ("runs every command not explicitly
  denied, without Cursor's sandbox") with a pointer to docs/orchestration-workers.md (Permissions).
- `orchestrate plan` prints them after the reviewer-auth notices; `--json` carries `cursor_force_warnings`
  (`OrchestrationPlan.cursor_force_warnings`). `doctor` prints them on stderr from the roster launches read
  (`pinned_config`); an unreadable roster is left to validate/plan.
- The `launched` event's `detail.permissions` shows the flags actually passed (A1 above).
- Note for M16.63 (no edit here): the roster `run:` field list gains `cursor_force`.

**A4 — tests, docs, CHANGELOG.** See Added below; docs/orchestration-workers.md (example comment, Cursor CLI
paragraph, Permissions paragraph, adapter table rows) and CHANGELOG [Unreleased] → Changed.

## Touch zones (confirmed)

Edited: worker_adapter_cursor.py, orchestrate_plan.py, bundled_scripts/orchestrate_cli.py,
bundled_scripts/doctor.py, worker_ops_launch.py, worker_ops_message.py, worker_runner.py, the template
orchestration schema, docs/orchestration-workers.md, CHANGELOG.md, sr/roadmap/orchestration.yaml,
sr/roadmap/decisions.yaml, tests/. Not needed: worker_adapter_base.py (the keyword lives on the Cursor adapter
only, so the Claude and Codex adapters, outside the zones, need no change). No new module.

## Left outside the zones (follow-up, not needed by the acceptance)

- `specy_road/templates/project/model-profiles/harness-facts.yaml:299` and the READMEs generated from it
  (`specy_road/templates/project/model-profiles/README.md:201`, `sr/model-profiles/README.md:162`) still
  give the Cursor headless command as `--force --trust`.
- `sr/schemas/orchestration.schema.json` (the toolkit project's copy) was already behind the package schema
  (no `harness_bin`); validation reads the package schema, so it was left alone.

## File limits

The CI gate (`validate_file_limits.py`, sr/constraints/file-limits.yaml, 400-line cap) had
docs/orchestration-workers.md and tests/test_worker_adapters.py at exactly 400 lines. Both stay at 400: the
docs text goes into the existing one-line Permissions paragraph (the file's own style for long paragraphs), and
the opt-in argv is pinned in tests/test_worker_resume_permissions.py rather than in test_worker_adapters.py.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider`: 4990 passed and 1 failed before the last test update
  (`test_cursor_reviewer_runs_ask_mode_without_force` pinned the old executor `--force`, which A1 changes);
  that file then passed alone (39 passed). The full run is repeated by `specy-road ready`.
- `ruff check specy_road tests scripts`, `validate_file_limits.py`, `check_clones.py`,
  `check_test_private_imports.py`, `check_machine_paths.py`, dogfood validate and export --check, and
  `specy-road validate` on sr/: all exit 0.

## Added

- `SANDBOX_FLAGS`, `FORCE_FLAGS`, `permission_flags(force)` (worker_adapter_cursor.py): the one place the default and the opt-in flags are stated (A1).
- `force` keyword on `Cursor.launch` / `Cursor.resume`: carries the roster's `cursor_force` into the default command (A1).
- `FORCE_WORDS`, `_forces(cli)`: detects `--force`/`--yolo` in a custom cursor command for the warning (A3, plan review).
- `force_warnings(roster)`: the one warning text plan and doctor print (A3).
- `_words(argv)`, `launch_permissions(argv)`: the flags a Cursor launch passed, for the `launched` event (A1, A3).
- `launch_options(entry, harness)` (worker_ops_launch.py): maps `cursor_force` to the adapter keyword for cursor only, used by launch and resume (A1).
- Branch in worker_runner.run: `detail.permissions` on a cursor worker's `launched` event (A1, A3).
- `OrchestrationPlan.cursor_force_warnings` field and its `to_dict` key, and the render line in orchestrate_cli (A3).
- `_print_cursor_force(root)` (doctor.py): doctor's advisory warning (A3).
- Schema property `cursor_force` (A1).
- Roster `cursor_force: true` on composer-2.5 and grok-4.7-exec, decision D8 (A2).
- Test `test_cursor_default_command_is_sandboxed_unless_the_roster_opts_into_force` (test_worker_resume_permissions.py, parametrized absent/false/true): pins launch and resume argv through `delegate` and `message` (A4).
- Test `test_plan_and_doctor_warn_once_per_cursor_entry_that_force_allows` (same file): one warning per opted-in entry, unassigned included, custom `--yolo`/`--force` commands included, a non-cursor `cursor_force` and a `false` entry ignored, the same lines from doctor (A4).
- `_roster`/`_repo` in that file take `cli=None` and `extra`: a default-command cursor entry with roster fields (support for the two tests above).
- Extended `test_cursor_creates_the_chat_first_passes_trust_sandbox_and_never_w` (test_worker_turn_check.py, renamed from `..._passes_force_trust_...`): no `--force` by default, and the `launched` event's `permissions` for both modes through the real runner with the fake `agent` (A4).
- Updated `test_default_commands_follow_the_documented_cli_flags` (test_worker_adapters.py) and `test_cursor_reviewer_runs_ask_mode_without_force` (test_review_record_write.py): they pinned the old `--force` default, which A1 changes; now they pin the sandboxed default (and, in the latter, the opt-in).
- Mocks: none added (the fake `agent` binary and the `spawn` stub are the files' existing ones).
