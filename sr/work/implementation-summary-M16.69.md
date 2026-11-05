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
 (`agent` from `~/.local/bin`); model `composer-2.5`.
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
- **Sandbox-enforcement probe (coordinator request, 2026-11-05).** Same agent `2026.11.05-86047df`, a second
  fresh linked worktree (`/tmp/m1669-probe`, branch `smoke/m16-69-probe`), a canary file outside it
  (`/tmp/m1669-canary-outside.txt`). The prompt asked for exactly two commands: `cat /tmp/m1669-canary-outside.txt`
  and `sh -c 'echo written > /tmp/m1669-outside-write.txt'`.
  - Headless, the adapter's default argv (`agent -p --resume <chat> --output-format stream-json --trust
    --sandbox enabled --model composer-2.5 --workspace /tmp/m1669-probe "<instruction>"`): **exit 1, the same
    "Sandbox failed to start" error, no event, no command run**; the outside file was not written.
  - Direct, `agent sandbox run <cmd>` in the worktree, for the canary read, the outside write and a write
    inside the workspace: **all three exit 1**, `SandboxUnsupportedError: Sandbox policy 'workspace_readwrite'
    is not supported on this system`; both backends fail at user-namespace setup (`Failed to write
    /proc/self/uid_map (mapping UID 0 -> 1000): Operation not permitted`, Landlock and Bubblewrap alike).
    Nothing was written in or outside the workspace.
  - **Plainly: Cursor's sandbox is not enforced on this machine with the installed version, because it does
    not run at all.** The probe could not show a refused read or write: no sandboxed command ran, so there is
    no evidence here either way that headless `-p` applies the sandbox when it does start. What it does show:
    on this host `--sandbox enabled` fails closed (the turn stops before any command; it did not fall back to
    running unsandboxed), so the new default cannot widen anything here. It only stops the worker.
  - Not verified, from the research report (sr/docs/research/agent-safety-posture-2026-11-05-claude-research.md):
    that headless `-p` honours the sandbox on a host where it starts (reported ignored before about
    2026.04.29; our version is later), and whether a failed sandboxed command reruns outside the sandbox.
    Neither could be exercised here. Treat `--sandbox enabled` as Cursor's documented intent, not a
    guarantee specy-road has checked.
  - The policy the CLI printed limits less than "sandboxed" suggests: `"readBoundary": "system"` (reads
    anywhere, so even a working sandbox would let the canary read through), writes to the workspace plus
    entries under `ignoreMapping` (which lists `/tmp`), and network `"default": "deny"`. So the sandbox
    confines writes and network, not reads.
  - The probe worktree, branch and canary were removed afterwards.
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
  `--force`, `-f` or `--yolo`; it names the entry, how it opts in, and the risk ("runs every command not explicitly
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
- A first `specy-road ready` run failed only `test_machine_paths_pass_on_this_repo`: this summary named an
  absolute home path; it now says `~/.local/bin`, and the suite is rerun by `ready`.
- `ruff check specy_road tests scripts`, `validate_file_limits.py`, `check_clones.py`,
  `check_test_private_imports.py`, `check_machine_paths.py`, dogfood validate and export --check, and
  `specy-road validate` on sr/: all exit 0.

## Fix round 1 (review of ba701596, `gpt-6.1-sol-low`)

**Finding's class.** Each custom-command check read the command with plain `shlex.split`, which is not how the
shell splits it: an unquoted operator stays in the word, so `--force; true` gave the word `--force;`. The result was
a flag that reaches `agent` while the check sees a different word.

**Fix.** One reader, `_shell_words` (`shlex.shlex` with the operators as punctuation), replaces the three
`shlex.split` calls, and one table of patterns says which words count. The bounded rule, in its docstring and in
docs/orchestration-workers.md (Permissions): words are split as the shell splits them, nothing is expanded, and every
word of the line counts. **Accepted limits:** the rule errs toward a warning (`rm -f x; agent ...` and a `# --force`
comment match, and the comment's flag would also be listed in `detail.permissions`); a flag inside `$FLAGS`, a wrapper
script or a quoted `sh -c '...'` is not seen.

**Beyond the finding.** The audit found a second spelling gap in the same checks: `agent` also takes `-f` and
clustered short switches (`-pf`, `-pw`), so these are now recognised, and the warning text says `--force/-f/--yolo`.
The `-w` refusal is stricter as a result: `-w; true`, `--worktree|cat` and `-pw` were accepted and are now refused.

## Probes

- `Cursor.launch` + `force_warnings` + `launch_permissions` on `agent -p {prompt} --force; true`: warning fired, `["--force"]` recorded (was none, `[]`).
- Same for `--yolo&& true`, `--force|cat`, `--force>log`, `(agent ... --force)`, backticks, `$(agent ... --force)`: all warn and record the flag.
- `force_warnings` on `channels.cli` and on `channels.cli_resume`, every case above: same result on both.
- `_no_worktree_flag` (same class, not named by the review): `-w; true`, `--worktree|cat`, `--worktree=mine&& true`, `-pw`, `-wmine` all refused; `-w; true` was accepted before.
- `--sandbox; true`: records `--sandbox` alone, so the new operator items are not taken as its value; `--sandbox disabled; true` records both words.
- Quoted or escaped operators: `'--force;'`, `--force\;`, `'try --force; then stop'`: no flag and no warning; `sh -c` with `printf` confirmed `--force\;` reaches the command as the literal `--force;`.
- Real `sh -c` splitting of `--force; true`, `--force&&true`, `--force|cat`, `--for\ce`: the command receives `--force` in each, as the reader says.
- `agent --help` (2026.11.05-86047df): `-f` is `--force`; `-H`, `-e` take values, `-w` an optional one. So `-Hf` is not a force flag (tested).
- Real `agent` argument parsing: `-pz` and `-fz` fail on `-z` alone, and `-pw` gets past parsing, so clusters are real; `--force=true` is an unknown option, so it stays unmatched (tested).
- Unbalanced quotes: `Cursor.launch` refuses the command, and `force_warnings` gives none; the command cannot run.
- Default (non-`sh -c`) argv: `test_cursor_default_command_is_sandboxed_unless_the_roster_opts_into_force` still gives exactly the two flag sets.
- Other `shlex.split` users: `worker_adapter_base.reviewer_cli` (agy reviewers, its `--dangerously-skip-permissions` refusal has the same shape) predates this leaf and is not Cursor; **not changed**, a candidate for intake. `tool_call_guard`, `orchestration_role_guard`, `review_pre_existing`, `worker_models`, `grind_session_implement` are outside this leaf's change and zones; not audited further.
- New tests against the ba701596 adapter: 16 of 42 in the file fail there; all 42 pass on this one.

## Added

- `SANDBOX_FLAGS`, `FORCE_FLAGS`, `permission_flags(force)` (worker_adapter_cursor.py): the one place the default and the opt-in flags are stated (A1).
- `force` keyword on `Cursor.launch` / `Cursor.resume`: carries the roster's `cursor_force` into the default command (A1).
- `_FORCE`, `_forces(cli)`: detects `--force`/`-f`/`--yolo` in a custom cursor command for the warning (A3, plan review).
- `force_warnings(roster)`: the one warning text plan and doctor print (A3).
- `_words(argv)`, `launch_permissions(argv)`: the flags a Cursor launch passed, for the `launched` event (A1, A3).
- `_shell_words(command)`, `_SHELL_OPERATORS`, `_SWITCHES`, `_PERMISSION`, `_WORKTREE` (fix round 1): the one reading of a custom command, used by the permission record, the warning and the `-w` refusal; replaces three separate `shlex.split` calls (A1, A3).
- Tests `test_a_custom_cursor_command_is_read_as_the_shell_splits_it`, `test_a_custom_cursor_command_never_asks_for_its_own_worktree`, `test_an_unbalanced_custom_cursor_command_is_refused_not_read` (test_worker_resume_permissions.py, fix round 1): the rule's clauses through `Cursor.launch` and `force_warnings` (A1, A3).
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
