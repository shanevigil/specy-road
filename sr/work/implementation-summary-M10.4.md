# Implementation summary: M10.4 — Pin harness discovery mode per profile

Branch `feature/rm-pin-harness-discovery-mode`, base `aae94d74b7f05ca8cee5a49a1ba7578110b3ce97`
(merge-base with `WIP/improvements-0-3-1`). M10.1, which also edits `run()` and `_consume`, landed
before this base (merge 3851894), so this leaf is built on top of it as the planning sheet asks.

## What changed, per acceptance item

- **A1** — `model_profiles.py`: `access.launch_mode` accepts `full` or `bare`;
  `Profile.launch_mode()` returns `full` when it is absent. Any other value is a
  profile error, `profile <name>: \`access.launch_mode\` must be full or bare, not '<value>'`,
  where `<name>` is the profile's file stem. `specy-road models show` already prints
  profile errors on its `INVALID:` line (and `--json` prints the front matter), so
  `models_cli.py` needed no change.
- **A2** — `worker_adapters.py`: `ClaudeCode.launch` and `.resume` put `--bare` right
  after `-p` only when `launch_mode == "bare"`. A custom `channels.cli` is returned
  as written; it only carries the mode for the A4 check. `worker_ops._cli_for` now
  also returns the pinned profile's `launch_mode` (`full` when there is no profile),
  and `delegate` and `message`/`resume` pass it to `launch`/`resume`. Every adapter's
  `launch`/`resume` accepts the keyword so `worker_ops` can call any of them the same
  way. Codex, Cursor and generic ignore it.
- **A3** — the `started` event from Claude's `system/init` line has a `detail` with
  `tools`, `mcp_servers` and `plugins` (names), plus `version` when the line has one
  (`claude_code_version`, the SDK's field name, falling back to `version`). It also
  has `inferred_mode`: `bare` when the tool list contains nothing outside
  `{Bash, Read, Edit}`, otherwise `full`.
- **A4** — `Launch` has a `launch_mode` field, so it travels in the wrapper payload
  (`asdict` / `Launch(**…)`). `Adapter.parse_events(line, launch)` returns a list of
  events. `ClaudeCode` overrides it to add an `error` event naming both modes
  (`detail: {inferred_mode, launch_mode}`) when they differ. `worker_runner.run()`
  passes the launch to `_consume`, which records every event that `parse_events`
  returns. The error has no `exit` key, so it does not end the turn. `worker sync`
  shows it like any other worker event.
- **A5** — `docs/orchestration-models.md` documents `launch_mode`: the vendor quote,
  its URL (code.claude.com/docs/en/headless, read 2026-11-01), the
  `ANTHROPIC_API_KEY` requirement in bare mode, and the init check. The
  model-profiles README now has an `access` fields table (`cli`, `effort_map`,
  `launch_mode`). `claude-opus-5-5.md` and `claude-fable-5-1.md` set
  `launch_mode: full` with a comment that bare needs an API key. `suggested_prompts/`
  has no list of profile fields (I grepped for `effort_map`, `access.cli` and
  `cli_verified_from`), so it is unchanged.

## Decisions

- The bare tool set comes from the vendor sentence "Bash, file read, and file edit
  tools", which I read as the tool names `Bash`, `Read` and `Edit`. The check is
  "no tool outside that set", so a deny rule that removes one of them still reads
  as bare.
- If the init line reports no `tools` list, `inferred_mode` is left out and no
  mismatch is raised. A missing list says nothing about the mode, and the existing
  fakes and older lines would otherwise raise a false error under a bare profile.
- "The two shipped Claude profiles" is taken to mean the current two (Opus 5.5 and
  Fable 5.1). The legacy `claude-opus-5` and `claude-fable-5` profiles still have no
  `launch_mode`, which means `full`.
- The date in the docs and the code comment is 2026-11-01. I re-read the vendor
  page that day and it still has both quotes, the bare tool sentence and the
  API-key paragraph. The planning sheet records an earlier reading on
  2026-10-30.

## Touch zones (final)

These are the brief's zones, and all edits stayed inside them: `specy_road/worker_adapters.py`,
`specy_road/worker_ops.py`, `specy_road/worker_runner.py`, `specy_road/model_profiles.py`,
`specy_road/templates/project/model-profiles/` (README, `claude-opus-5-5.md`,
`claude-fable-5-1.md`), `docs/orchestration-models.md`, `tests/test_worker_adapters.py`,
`tests/test_models_and_prompt.py`. `suggested_prompts/` needed no change.
`bundled_scripts/models_cli.py` was not needed (see A1).

## Verification

- `pytest tests/test_worker_adapters.py tests/test_models_and_prompt.py`: 33 passed
- `ruff check` on the changed Python files: clean
- `python scripts/check_test_private_imports.py`: 0 new. The first draft of the
  `models show` test imported `worker_ops._cli_for`, so it now drives the public
  `delegate` / `message` instead and does not touch the baseline.
- `specy-road file-limits`: OK (`worker_adapters.py` 383 / 400)
- full `pytest`: see the READY file

## Added

### Helpers
- `model_profiles.LAUNCH_MODES`: the two accepted values, used by the validation.
- `Profile.launch_mode()`: the effective mode (`full` when absent), so `worker_ops` reads it in one place.
- `worker_adapters.CLAUDE_BARE_TOOLS`: the vendor-documented bare tool set that `inferred_mode` compares against.
- `worker_adapters._bare()`: one place that builds the `--bare` argument for launch and resume.
- `worker_adapters._names()`: turns the init line's `mcp_servers` / `plugins` entries (`{name, …}`) into names.
- `worker_adapters._init_detail()`: builds the `started` detail (A3). It is a separate function so `ClaudeCode.parse` stays under the C901 cap.
- `Adapter.parse_events()` / `ClaudeCode.parse_events()`: let one line record several events (A4) while `parse()` keeps its contract.

### Branches and guards
- `_structure_errors`: the `launch_mode` value check (A1). It now takes `name` so the message names the profile.
- `ClaudeCode.launch`/`resume`: `replace(custom, launch_mode=…)`, so a custom cli stays as written but still carries the mode for the check.
- `_init_detail`: no `inferred_mode` when the line has no tool list (see Decisions).
- `_cli_for`: returns `"full"` when the roster entry has no profile.

### Fields and signatures
- `Launch.launch_mode` (default `full`): carries the mode through the wrapper payload to parse time.
- `launch_mode` keyword on every adapter's `launch`/`resume`: so `worker_ops` can call any harness the same way.
- `_consume(..., launch)`: so the adapter knows the mode the profile expects.

### Mocks
- `worker_ops.spawn` is monkeypatched in the `models show` test to capture the `Launch` that `delegate`/`message` build, without starting a harness. The other tests reuse the existing `_fake` harness script and `make_review_repo`.

### Tests
- `test_claude_passes_bare_only_when_the_profile_says_bare`: A2, covering launch and resume, `full` and absent, and a custom cli on launch and resume.
- `test_claude_init_detail_reports_what_loaded_and_the_inferred_mode`: A3, covering full and bare tool lists, both version fields, and a line with no tool list.
- `test_claude_init_mismatch_adds_an_error_naming_both_modes`: A4 at the adapter, both mismatch directions; Cursor does not check the mode.
- `test_the_wrapper_payload_carries_the_mode_and_records_the_mismatch`: A4 end to end through `worker_runner.main` and its payload file: the event order and an error with no `exit` key.
- `test_launch_mode_is_full_or_bare_and_absent_means_full`: A1 values and the error text; the two shipped Claude profiles set `full` (A5).
- `test_models_show_prints_a_bad_launch_mode_and_delegate_reads_a_good_one`: A1 through `models show`; A2 wiring: the public `delegate` launches `full` without `--bare`, and after the profile changes to `bare` the public `message` resumes with `--bare` (`spawn` is monkeypatched to capture the `Launch`).
