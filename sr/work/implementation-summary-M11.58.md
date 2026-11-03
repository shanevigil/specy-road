# Implementation summary: M11.58 — session routing preferences

Base `018615c8`, with the zone change `e3176b58`. Code commit `1733e3d2`.

## Final touch zones

The brief's zones plus the two added in `e3176b58`:

- `specy_road/decisions.py`
- `specy_road/bundled_scripts/decisions_cli.py`
- `specy_road/templates/project/schemas/` (`decisions.schema.json` only)
- `specy_road/templates/specyrd/commands/specyrd-orchestrate.md`
- `specy_road/bundled_scripts/role_prompt.py`: **unchanged**. The coordinator prompt gets its new
  text from `coordinator_decision_lines()` in `decisions.py`, which `role_prompt.py` already calls.
- `specy_road/bundled_scripts/orchestrate_cli.py`
- `specy_road/orchestrate_plan.py`
- `docs/orchestration.md`
- `tests/` (new file `tests/test_decision_preferences.py`)

No new module was needed. `decisions.py` is now 391 lines and `docs/orchestration.md` is exactly 400,
the cap. The next addition to either file needs a split.

## What changed, by acceptance item

**A1.** The ledger schema now allows `kind: preference`. The base required fields are `id`, `kind`,
`summary`, `asked` and `status`. A conditional block keeps the two shapes apart:

- `decision` and `human-action` entries still need `node`, `why_now`, `options`, `recommendation`,
  `recommendation_reason` and `default_if_unanswered`, and may not carry preference fields.
- A preference may not carry `options`, `recommendation*`, `default_if_unanswered` or `needed_by`.

A preference can also carry `role` (coordinator, executor or reviewer), `models` (roster ids, most
preferred first, unique), `applies_to` (leaf kinds, free words), `expires` (a date, inclusive, or a
datetime), and an optional `node` and `why_now`.

The CLI side:

- `decisions add --kind preference --summary …` takes `--role`, repeated `--model`, repeated
  `--applies-to`, `--expires`, `--why` and `--supersedes`.
- NODE is optional for a preference, and ids default to `P#`.
- For each kind, `add` refuses the flags that kind does not take and names any required flag that
  is missing.
- `decisions list` (text and `--json`) prints active preferences first, oldest first, then open
  decisions in needed-by order. Expired preferences are dropped from the output but stay in the file.
- `decisions close` on a preference needs only `--answer`, with no planning-sheet record.
  `--supersedes` closes the old preference with `answer: superseded by P#`.

There are no availability fields on a preference. `orchestrate plan` reads availability from the
roster (`unavailability_reason`) and notes any preferred model the roster does not have.

**A2.** `coordinator_decision_lines()` gains a `## Routing preferences` section, which the
coordinator prompt picks up, and the orchestrate skill gains a matching paragraph. Both say to:

- read the active preferences at the start of every session and before each `worker delegate` or
  reviewer launch;
- record a preference whenever the human states one;
- use `--supersedes` when the human changes one and `close` when they drop it;
- set availability in the roster, never as a preference.

The skill's plan, delegate and review steps also mention this. The "Decisions waiting on you" line
now covers decision and human-action entries only.

`orchestrate plan` ends its text output with `preferences not applied automatically …`, listing each
active preference and a `! <id>: <reason> (roster)` line for each preferred model that is
unavailable or not in the roster. The JSON output gains `preferences_not_applied` (each preference
plus `roster_notes`) and `preferences_error`. If the ledger can't be read or fails its schema, the
plan prints a `! preferences:` warning and its exit code doesn't change. The plan never applies a
preference itself.

**A3.** `docs/orchestration.md` gains a paragraph in the decisions section, and the tests are listed
below. The paragraph says preferences are per project and session-durable (they survive a context
reset, an account switch or a different agent taking over), are not roster config, and that a
project with its own `schemas/decisions.schema.json` should run `refresh-schemas` first.

## Behaviour changes worth a reviewer's eye

- For `decision` / `human-action`, a missing `--why`, `--option`, `--recommendation`,
  `--recommendation-reason`, `--default` or NODE used to be an argparse error (exit 2). It is now a
  named error with exit 1, because argparse can't make those flags required for some kinds only.
- `close_entry(..., sheet_text=None)` is new. The CLI passes `None` only for preferences, and the
  function refuses `None` for any other kind.
- A consumer whose own `schemas/decisions.schema.json` predates this change will reject preference
  entries until it runs `specy-road refresh-schemas`. The docs say so.

## Verification

- `python -m pytest tests/test_decision_preferences.py tests/test_decisions.py tests/test_orchestrate_plan.py -q`: 41 passed
- `python -m pytest -n auto -q -p no:cacheprovider`: 3390 passed, 2 skipped
- `specy-road file-limits`: OK
- `python scripts/check_test_private_imports.py`: 0 new. It reports one stale baseline entry for
  `test_review_round6_evidence.py`, which predates this leaf and which I left alone.
- `ruff check` on the changed Python files: clean
- Not run: `python scripts/check_clones.py` stops because `pylint` is not installed in this
  environment.

## Added

- `decisions.PREFERENCE`: the kind name, shared by the module, the CLI and the plan.
- `decisions.open_questions`: open non-preference entries in needed-by order, so preferences stay
  out of the question list and the "waiting on you" block.
- `decisions.preference_active`: open and not expired. It reuses `orchestrate_plan._pause_active`
  through a lazy import (avoiding an import cycle) so `expires` follows the same date/datetime rule
  as `paused_until`.
- `decisions.active_preferences`: the list order for A1 (oldest first, expired dropped).
- `decisions.plan_preferences`: reads the ledger for the plan and turns a read or schema failure
  into a warning string, so a broken ledger never fails `orchestrate plan`.
- `decisions.format_preference`: one text shape, shared by `decisions list` and the plan notice.
- `decisions.add_preference`: writes a preference, checks `expires` with
  `orchestration_config._paused_until_error` (the same check as `paused_until`), and handles
  `--supersedes`.
- Guard in `decisions.close_entry`: `sheet_text=None` is allowed only for a preference, so
  decisions still need their sheet record.
- `next_decision_id(prefix=…)`: gives preferences `P#` ids without disturbing the `D#` sequence.
- `decisions_cli._kind_flag_error` with `_QUESTION_FLAGS`, `_QUESTION_ONLY` and `_PREFERENCE_ONLY`:
  per-kind required and refused flags, which argparse can't express.
- `decisions_cli._add_preference`: the preference branch of `cmd_add`.
- Branch in `decisions_cli.cmd_close`: a preference skips the planning-sheet lookup (it may have no
  node).
- `orchestrate_plan.preference_notice`: adds `roster_notes` from roster availability, so a
  preference and the roster never disagree.
- `OrchestrationPlan.preferences_not_applied` and `preferences_error`, plus their `to_dict` keys:
  the A2 `--json` field.
- `orchestrate_cli.preference_lines`: the text notice and the `! preferences:` warning.
- Schema conditionals in `decisions.schema.json`: keep the decision shape and the preference shape
  apart.
- Mocks: none.
- Tests, all in `tests/test_decision_preferences.py`:
  - `test_add_preference_writes_structured_fields_without_a_node`: A1 add, `P#`/`D#` sequences.
  - `test_add_refuses_flags_the_kind_does_not_take` (5 cases): per-kind flags, bad `expires`.
  - `test_decision_refuses_preference_flags`: the reverse direction.
  - `test_schema_keeps_the_two_shapes_apart`: the schema conditionals.
  - `test_expiry_is_inclusive_through_the_date_and_exact_for_a_datetime`: expiry rule.
  - `test_list_shows_active_preferences_first_and_drops_expired`: listing order (text and JSON),
    expiry drops without closing.
  - `test_supersede_and_close_a_preference_without_a_sheet_record`: update and close.
  - `test_plan_prints_active_preferences_with_roster_availability`: plan notice, roster notes,
    JSON field, expiry by `--today`.
  - `test_plan_without_preferences_or_with_a_broken_ledger`: no notice when empty, warning on a bad
    ledger with the exit code unchanged.
  - `test_coordinator_prompt_and_skill_name_the_preference_routine`: A2 text in the prompt and the
    skill.
