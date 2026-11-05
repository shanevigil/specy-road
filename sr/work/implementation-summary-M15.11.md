# Implementation summary: M15.11

Branch `feature/rm-working-roster-in-one-command-and-validated-profiles`. Implementation commit
`13001aa7`; registration base `54a15dc9`. Rework executor `composer-2.5` at prompt base
`970625b8` made no code changes; verification re-run below.

## What changed, by acceptance item

- **A1 — `specy-road models roster`.** New `specy_road/roster_generate.py`; a new `roster` subcommand in
  `specy_road/bundled_scripts/models_cli.py`. `--executor`, `--reviewer` and `--coordinator` (repeatable) name a
  shipped profile by file name, `api_id` or alias. The command prints one entry per profile with `id` (the file
  name), `family` (the README's roster family), `profile:` (`model-profiles/<dir>/<file>.md`), `harness` (the
  harness-facts record whose `executor_template.renders_cli_for` lists the profile family, else `generic`) and
  `roles`. `--write` adds the entries as text at the end of the `roster:` block of `roadmap/orchestration.yaml`, so
  the comments stay. It skips ids that are already rostered, re-parses the result and refuses when the new ids are
  missing. An unknown id is refused with the nearest ids (`difflib`). A profile file the repo lacks is named on
  stderr with `refresh-profiles --only <id>`. Tests round-trip the written entries through `validate_at` and write
  into the starter.
- **A2 — local profile validation.** New `specy_road/roster_profile_check.py`:
  - `profile_value_problem` returns `invalid profile: <value>, accepted form <form>` unless the value is a `.md`
    file under `model-profiles/` in the working tree. The form is the concrete path when the value's last part
    near-matches a local or bundled profile, else `model-profiles/<family-dir>/<profile-id>.md`.
  - `report_roster_profiles` replaces validate's old roster-gap loop. In `validate_roadmap_checks.py` the import
    line and the call line changed (399 → 398 lines). The new problems are warnings.
  - In `orchestration_pinned.pinned_profile_for_entry`, a `profile:` naming no file in the working tree or at the
    ref now carries that message instead of "not committed on the integration branch".
  - In `orchestrate_assign._valid`, such an entry is reported as `<id>: invalid profile: …`.
  - `_pick_executor` adds no `no eligible executor … may_process` hint when the only reason nothing is capable is
    an entry dropped for an invalid profile.
- **A3 — consistent ids.**
  - `claude-opus-5.5` → `claude-opus-5-5` in `docs/orchestration.md`, `docs/orchestration-workers.md` and the
    design note.
  - The design note's profile paths now match the shipped ones.
  - `docs/orchestration-models.md`'s `harness_model` example now uses a label (`opus-main`), because that example
    is about a roster id that is not a harness id.
  - The starter's commented example now shows `profile:` and points at `models roster`.
  - A scan test checks every roster example in `docs/orchestration*.md`, the design note and the starter. Ids
    with a version digit must match a shipped profile file name, `api_id` or alias. Example `profile:` paths must
    exist in the shipped templates. A second test proves the scan catches the old id and path. Against `HEAD~` it
    flags all five files.
- **A4 — coordinator line and `--spread`.**
  - Assignment moved to new `specy_road/orchestrate_assign.py` (leaf-field and availability helpers, `Candidate`,
    `Assignment`, the picks, `assign_leaf`). `orchestrate_plan.py` re-exports every name callers import, so no
    import site changed, and it went from 372 to 134 lines.
  - When no roster entry has the coordinator role, the leaf records `coordinator_is_session` and a note pointing
    at `docs/orchestration-roster.md`. The text output prints `coordinator: this session`, and this is not a
    problem. If coordinators are rostered but none qualifies, the leaf is still unstaffable.
  - `orchestrate plan --spread` gives the leaf at plan position *i* (batches in order, then leaves) entry
    *i* mod *n* of the capable entries, ranked as before.
  - New `docs/orchestration-roster.md` documents the generator, the local check, how to roster a model
    coordinator and `--spread`. `orchestration.md` links it by extending an existing line (it stays at 400), and
    `orchestration-models.md` mentions all three.

## Behaviour change to an existing test

`tests/test_review_round4_sol_b.py::test_a_plan_without_a_coordinator_says_so` asserted that a roster with no
coordinator is a staffing problem. A4 changes that behaviour: the plan now names this session as coordinator. The
test now asserts the new outcome: no problem, `coordinator_is_session`, and the note. The "rostered but
ineligible" case is still a problem; `tests/test_orchestrate_spread.py` pins it.

## Touch zones

All changes are inside the listed zones. Final list: as given. One file outside the zones would have helped but was
left unchanged: `specy_road/cli_usage.py`, the top-level `specy-road -h` text. It does not list `models roster` or
`orchestrate plan --spread`. Both subcommands' own `-h` and the docs cover them, and no test requires the usage
text to list them.

## Verification

Re-run by `composer-2.5` on implementation commit `13001aa7` (no code delta in this session).

- `python -m pytest -q -n 4`: 4128 passed.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests/test_roster_generate.py tests/test_orchestrate_spread.py`: clean.
- `specy-road validate` for the dogfood fixture and `sr/`: exit 0.
- `export --check` and `digest --check` on the dogfood fixture: OK.

## Added

- `specy_road/roster_generate.py`: `ROSTER_FAMILY` (profile family → roster family, from the profiles README);
  `RosterError`; `shipped_profiles`; `profile_id`; `find_profile` (refusal with the nearest ids); `harness_for`;
  `roster_entries`; `format_entries`; `missing_profile_files`; `_roster_span` (finds where the roster block ends);
  `write_entries` (text insert with a re-parse guard, so comments survive). Reason: A1.
- `specy_road/roster_profile_check.py`: `GENERIC_FORM`; `accepted_form`; `profile_value_problem`;
  `roster_profile_problems`; `report_roster_profiles` (the old validate loop moved here, plus the new warnings).
  Reason: A2, keeping `validate_roadmap_checks.py` to a call-line change.
- `specy_road/orchestrate_assign.py`: moved code plus `Assignment.coordinator_is_session`. New branches:
  - the `--spread` pick in `_pick_executor` (`spread_index`);
  - the invalid-profile drop guard that suppresses the `may_process` hint;
  - the verbatim `invalid profile:` message in `_valid`;
  - the no-coordinator-rostered branch in `_pick_coordinator`.

  Reason: A2 and A4, and the 400-line cap on `orchestrate_plan.py`.
- `specy_road/orchestration_pinned.py`: a guard in `pinned_profile_for_entry` for a `profile:` naming no file in
  the working tree or at the ref, which returns the `invalid profile` message. Reason: A2, which replaces the
  misleading "not committed" message.
- `specy_road/orchestrate_plan.py`: the `spread` parameter and the leaf-order index; re-exports from
  `orchestrate_assign`. Reason: A4.
- `specy_road/bundled_scripts/orchestrate_cli.py`: the `--spread` flag and the `this session` render. Reason: A4.
- `specy_road/bundled_scripts/models_cli.py`: `cmd_roster` and the `roster` subparser. Reason: A1.
- `tests/test_roster_generate.py`: printed entries; unknown id refused with the nearest ids; `--write` round-trips
  through validate and is idempotent; write into the starter keeps its comments; validate warning with the accepted
  form; `profile_value_problem` cases; plan reports the invalid profile with no `may_process`/"not committed" text;
  hint kept when nothing was dropped; scan self-test; docs/starter scan. Reason: A1–A3.
- `tests/test_orchestrate_spread.py`: `three_leaf_repo` helper; three leaves over two capable entries pinned for
  the default and `--spread` (deterministic); `--spread` on the CLI; `coordinator: this session` text and JSON;
  a rostered-but-unavailable coordinator still a problem. Reason: A4.
- Mocks: none.
