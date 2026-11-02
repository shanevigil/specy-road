# Implementation summary: `M10.5` — Per-role effort in model profiles

Branch `feature/rm-per-role-effort-in-model`, base `6bd6fc8` (fast-forwarded to `18b6db0` for the widened touch zones), implementation commit `d9bf465`, review-round fixes `4fd47f8` (gpt-6.1-sol round 2: F1, F2) and `2eaefa5` (gpt-6.1-sol round 3: F1).

## Touch zones (final)

As widened after the first stop report (`18b6db0`):
`specy_road/model_profiles.py`, `specy_road/worker_adapters.py`, `specy_road/worker_adapter_parsers.py`,
`specy_road/worker_ops.py`, `specy_road/worker_runner.py`, `specy_road/bundled_scripts/role_prompt.py`,
`specy_road/bundled_scripts/models_cli.py`, `specy_road/templates/project/model-profiles/`,
`docs/orchestration-models.md`, `tests/test_models_and_prompt.py`, `tests/test_worker_adapters.py`.
I touched all of them except `specy_road/worker_sessions.py`. The brief's Approach put the placeholder set there, but it lives in `worker_adapter_parsers.py`.

## Per acceptance item

- **A1:** `access.effort_by_role` maps `coordinator`/`executor`/`reviewer` to an `effort_map` key.
  - `model_profiles._effort_errors` rejects four cases, each with an error starting `profile <name>:`: a value that is not a mapping, an unknown role, a key not in `effort_map`, and a key whose level is `unknown`.
  - `Profile.effort(role)` returns the model's own level, or `None` when the role is unset.
  - `models show` prints `- effort_by_role: role=key (level), …`.
- **A2:** `{effort}` is now in `PLACEHOLDERS` and gets the same whole-argument rule as the others, so `--effort={effort}` is refused. Like `{session_flag}`, it cannot sit behind a `<` redirect.
  - Each adapter's `effort_flag(level)` turns the level into the harness's arguments: Claude Code `--effort <level>`, Codex `-c model_reasoning_effort=<level>`, Cursor and generic nothing.
  - `prompt --channel cli` uses the roster entry's `harness` and the role's level. `rca` uses the reviewer's level.
  - `worker delegate`, `message` and `resume` use the executor's level, read in `_cli_for`.
  - Both paths print one note (`effort_note`) when the profile sets a level but the command names no `{effort}`.
- **A3:** The default Claude Code launch and resume commands carry `--effort`, and the Codex `exec` and `exec resume` commands carry `-c model_reasoning_effort=…`, whenever the profile sets an executor level. `worker_runner.run` removes `CLAUDE_CODE_EFFORT_LEVEL` from the harness's environment.
- **A4:**
  - `docs/orchestration-models.md` has a section on `effort_by_role`, the per-harness flag table and `{effort}`. It also mentions `{effort}` in the `prompt --channel cli` paragraph.
  - The model-profiles README's access-field table lists `effort_by_role`.
  - The shipped Claude profiles are set as follows:

    | Profile | Coordinator | Executor | Reviewer |
    |---|---|---|---|
    | Opus 5.5 (default medium) | low | medium | medium |
    | Opus 5 (default high) | medium | high | high |
    | Fable 5.1 and Fable 5 (default high) | medium | high | high |

    Round 2 (F1) changed Fable. Anthropic's effort page (https://platform.claude.com/docs/en/build-with-claude/effort, fetched 2026-11-01) lists all five levels for Fable 5.1 and Fable 5, with `high` the default and "step down to `medium` or `low`". It is cited as S11 in the Fable 5.1 profile and S12 in the Fable 5 profile. Both profiles' `effort_controls` now name the levels, `effort_map` has `medium: medium`, and the coordinator is `medium`. `low` and `max` stay `unknown` in `effort_map`: the same page confirms them, but the coordinator asked only for `medium`.
  - Each of those `effort_by_role` lines has a comment pointing at M10.6.
  - Tests cover A1 to A3; see the list below.

## Notes for reviewers

- **Round 3 (F1).** The known-levels list in `_effort_errors` joined `effort_map` keys as strings. A YAML key such as `true` or `2` raised `TypeError` there, so the profile-named rejection was lost; the keys are now passed through `str()`. I checked the other effort diagnostics for the same assumption:
  - The unknown-role error formats its role with `!r` and checks the mapping shape first.
  - The key check tests `isinstance(key, str)` before the `in` check.
  - `Profile.effort` does the same.
  - The `models show` line and `effort_note` only format values in f-strings.

- **The M10.6 comment ships.** The acceptance text requires it, but `model-profiles/` is scaffolded into adopter repos, where "M10.6" is a toolkit-internal id. Someone may want to reword it before promotion to `main`.
- **Precedence is unverified.** I have not checked whether `CLAUDE_CODE_EFFORT_LEVEL` outranks `--effort` in Claude Code. The env var is removed either way, as A3 asks.
- **One doc left alone.** `docs/orchestration-workers.md` documents `{session_flag}` but not `{effort}`. It is outside the touch zones, so I did not edit it.
- **Fixture copies not synced.** The copies of the profiles in `tests/fixtures/specy_road_dogfood/model-profiles/` and `sr/model-profiles/` are unchanged. They are outside the touch zones, and no test compares them with the templates.
- **Line cap.** `worker_adapters.py` is exactly 400 lines (the cap). Per-harness flags live in an `EFFORT_FLAGS` dict instead of method overrides to fit.
- **Tests moved.** `tests/test_models_and_prompt.py` would have gone over its cap, so the prompt and delegate effort tests live in `tests/test_worker_adapters.py`.
- **F2.** The helpers that `tests/test_worker_adapters.py` imports are now public in `tests/test_models_and_prompt.py`: `make_profile_repo`, `commit_profile` and `run_main`, formerly `_repo`, `_commit_profile` and `_run`. Other test modules already import public names from that module (`ROSTER`, `TEMPLATE_PROFILES`, `OPUS`). A separate helper module would have been outside the touch zones. Only the names changed; no assertion did.

## Verification (foreground)

- `pytest tests/test_models_and_prompt.py tests/test_worker_adapters.py` → 43 passed (again after `4fd47f8` and `2eaefa5`).
- `specy-road file-limits` → OK.
- `ruff check specy_road tests/test_models_and_prompt.py tests/test_worker_adapters.py` → all checks passed.
- `python scripts/check_test_private_imports.py` → 0 new.
- Full `pytest` not run, as the coordinator asked.

## Added

- `Profile.effort(role)` (model_profiles.py): resolves `effort_by_role` through `effort_map` for prompts and adapters.
- `_effort_errors` (model_profiles.py): A1 validation, kept outside `_structure_errors` so its complexity baseline does not grow.
- Guard: a key mapped to `unknown` is an error, since otherwise the harness would be sent `--effort unknown`.
- Guard: a non-string key is an error, since an unhashable YAML value would raise in the `in` check.
- `str(k)` in the known-levels list of `_effort_errors` (round 3): non-string `effort_map` keys no longer crash the diagnostic.
- `{effort}` in `PLACEHOLDERS` and `_ARGS` (worker_adapter_parsers.py): A2 placeholder; `_ARGS` lets the redirect refusal cover `{effort}` as well as `{session_flag}`.
- `effort` parameter of `substitute_prompt`: carries the flag words into the substitution.
- `effort_note(cli, level)` (worker_adapter_parsers.py): the one note A2 asks for, shared by `prompt` and `worker_ops`. It returns nothing for a command that cannot run, which is refused with its own reason elsewhere.
- `EFFORT_FLAGS` and `Adapter.effort_flag` (worker_adapters.py): each harness's token for a level (A2, A3).
- `effort` keyword on every adapter `launch`/`resume` and on `_custom`: threads the level into the default and custom commands (A3).
- Fourth value returned by `worker_ops._cli_for`, plus the note print there: gives delegate, message and resume the executor's level (A2, A3).
- `env.pop("CLAUDE_CODE_EFFORT_LEVEL")` in `worker_runner.run`: A3.
- `harness` and `role` keywords on `role_prompt.run_cli_channel`: pick the harness's flag and the role's level (A2).
- `effort_by_role` line in `models_cli` show: A1.
- Tests in tests/test_models_and_prompt.py:
  - `test_effort_by_role_names_effort_map_keys_and_rejects_the_rest`: A1 validation and resolution. Since round 3 it also feeds an `effort_map` with non-string keys (`true`, `2`) and asserts the exact profile-named unknown-key error.
  - `test_shipped_claude_profiles_set_default_effort_and_coordinator_one_below`: A4 shipped levels and the M10.6 comment. After F1 it expects `medium` for the Fable coordinator.
  - `test_models_show_prints_effort_by_role`: A1 show output.
- Tests in tests/test_worker_adapters.py:
  - `test_default_claude_and_codex_commands_carry_the_effort_flag_and_cursor_none`: A3 default commands.
  - `test_custom_cli_effort_placeholder_becomes_each_harness_flag`: A2 substitution per harness and refusal of embedded or redirected `{effort}`.
  - `test_effort_note_only_when_a_level_is_set_and_the_command_names_no_effort`: A2 note condition.
  - `test_the_worker_child_environment_has_no_claude_code_effort_level`: A3 environment.
  - `test_prompt_cli_channel_substitutes_the_roles_effort_or_notes_its_absence`: A2 for `prompt --channel cli`.
  - `test_delegate_passes_the_executor_effort_to_default_and_custom_commands`: A2 and A3 for `worker delegate`.
- `make_profile_repo`, `commit_profile`, `run_main` (F2): public names for the existing private helpers, so `tests/test_worker_adapters.py` imports no private test names.
- `_harness` test helper: rosters `opus` on `claude-code` with an optional `channels.cli`.
- `ENV_PROBE` test script: lets the harness report its own environment.
- Mocks: `ops.spawn` is monkeypatched in the delegate test to capture the `Launch`, the same pattern as the existing launch_mode test.
