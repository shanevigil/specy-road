# Implementation summary: M22.24 `guidance-exclusion-closes-three-bypasses`

Base `4a1a8674`. Fix commit `fc3a691b`. Touch zones unchanged and accurate. All changes are in the five zoned files; no caller changed.

## What changed

- **A1, human exemption** (`orchestrate_assign._guidance_hit`, `_is_person`). `family: human` is exempt only when the entry sets none of `harness`, `harness_model`, `harness_bin`, `profile`, `channels.cli` or `channels.cli_resume`, and the caller resolved no profile for it. Any other human entry, committed or `roster_add`, is judged like a model entry. That includes the integration-branch read-error refusal. `channels.paste`, `channels.subagent` and `preflight` do not remove the exemption. The configuration-boundary alternative was not taken, because `roster_local.py` and the schema are outside the zones.
- **A2, `access.cli`** (`_launch_models`). Adds `command_model(copy.cli())` for each profile copy given, meaning the routed profile and `src.committed(profile)`. The committed `access.cli` therefore counts even when the working tree's copy sets `access.cli: none`.
- **A3, quoted paths** (`orchestration_pinned._committed_source`). Runs `git_stdout(["ls-tree", "-r", "-z", "--name-only", …])` and splits on `\0`. The `.md` filter drops the empty tail. A failed listing still returns `_failed`.
- **A5, unreadable flags** (`_model_unreadable`, `_unreadable_field`). A command is split the way `bypass_problem` splits it. It counts as unreadable when:
  - it cannot be split; or
  - it has a model-flag word (`--model`, `--model=…`, `-m`, `-m<value>`) and `command_model` returns `None`; or
  - it has more than one model-flag word.

  The fields checked are `channels.cli`, `channels.cli_resume` and each copy's `access.cli`. While signed reviews are on, such an entry gets the brief's refusal text, or the opted-in warning when the committed roster opts in. Precedence is: read error, then flagged name, then unreadable field. `validate` and `doctor` print `warning: <id> (model unreadable in <field>) is excluded…` / `opted in at its own risk` through `guidance_bypass_lines`.
- **A5, normalised names** (`_flagged`). An exact key match is tried first, then `model_names.same_model(name, key)`. The record comes from the matched key, and the label shows the name as the entry spells it. `composer-2` stays unflagged.
- **A4, docs and CHANGELOG.** `docs/orchestration-roster.md` gets the bounded-rule paragraph, and the launch-name list now names the roster id and `access.cli`. The existing `[Unreleased]` Security bullet in `CHANGELOG.md` is extended; no version heading was added.
- **Not changed, noted for reviewers:**
  - `orchestration_pinned._committed_profile_paths` (profile lookup by id, not the flag map) still uses the quoted plain listing. A by-id profile at a quoted path is routed as no profile, but its id is still a launch name and the flag map now holds its flag. The brief scopes A3 to `_committed_source`.
  - A non-UTF-8 listing still fails through the existing path.

## Verification

- `pytest -n 4 -q`: 6230 passed. `-n 4` was used instead of `-n auto` because the brief asks to cap workers on a shared machine.
- `pytest -n 4 -q tests/test_guidance_bypass_roles.py`: 65 passed.
- Red/green: with the two source files reverted to base, 28 of the new rows in that file fail and 37 pass, the 37 being the existing rows plus passing controls. With the fix, all pass.
- `specy-road file-limits`: OK. `orchestrate_assign.py` is 501 lines and the test file 561, both under the 1000 cap.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.

## Added

### Code (`specy_road/orchestrate_assign.py`)
- `LAUNCH_KEYS`, `LAUNCH_CHANNELS`: the roster keys that make a human entry a model launch (A1), shared with `_launch_models`.
- `_channels(entry)`: the entry's `channels` dict or `{}`. The existing inline expression is now shared by three helpers.
- `_copies(entry, profiles)`: the profile copies resolved by id. The existing inline expression is now shared by `_launch_models` and `_unreadable_field`.
- `_launch_models` branch: `command_model(prof.cli())` per copy (A2).
- `_model_unreadable(command)`: the unreadable-model-flag rule (A5).
- `_unreadable_field(entry, *profiles)`: the first unreadable field, for the refusal text (A5).
- `_is_person(entry, profile)`: the narrowed human exemption guard (A1).
- `_Hit` NamedTuple: replaces the 4-tuple so the unreadable case can carry `field`; readers use names, not indexes.
- `_flagged(names, flags)`: exact-then-normalised flag lookup through `same_model` (A5).
- `guidance_bypass_refusal` branch: the unreadable-field refusal text (A5).
- `guidance_bypass_warning` branch: the unreadable-field opted-in warning (A5).

### Code (`specy_road/orchestration_pinned.py`)
- `_committed_source`: `-z` listing split on NUL, plus a docstring (A3). This is a change to the listing, not a new guard.

### Tests (`tests/test_guidance_bypass_roles.py`; public CLI only, no `_`-prefixed imports, no mocks)
- `roster()` gains `cli=None` (omit `channels`) and `resume` (`channels.cli_resume`), as the brief asks.
- `test_unchanged_unless_a_flagged_model_meets_signed_reviews`: an unreadable-command row with signed reviews off, which launches unchanged (A5).
- `test_every_model_an_entry_launches_is_matched`: rows for `COMPOSER-2.5`, `cursor-composer-2.5` and `--model Composer_2.5`. The assertion now names the expected model per row (A5).
- `test_an_unreadable_integration_branch_profile_refuses`: extended so `handoff status --json` shows the key-holding `human` row eligible while `my-model` is refused. A person keeps the exemption (A1).
- `test_a_human_entry_that_launches_a_model_is_judged_like_one`: three launch configurations × committed/local × `worker delegate`/`prompt`, all refused with nothing launched (A1).
- `test_a_profile_access_cli_model_is_matched`: `access.cli` model through `worker delegate` and `prompt --run --channel cli`, with and without a working-tree drift to `access.cli: none` (A2).
- `test_a_flag_on_a_profile_at_a_quoted_path_is_found`: `café.md` with `core.quotePath=true` forced through `GIT_CONFIG_COUNT` (A3).
- `test_an_unreadable_model_flag_is_refused`: substitution, list, variable, attached `-m`, two flags, unbalanced quote, and `cli_resume` only, each refused (A5).
- `test_an_unreadable_local_command_is_refused_and_a_committed_opt_in_admits_it`: the review's `roster_add` case is refused. A committed opt-in launches and warns once, and `validate`/`doctor` print the opted-in line (A5).
- `test_no_shipped_profile_is_refused_but_the_flagged_one`: one generic executor per bundled profile; `validate` excludes only composer-2.5 and reports nothing unreadable.
- Helpers `PERSON`, `SAFE`, `safe_profile`, `UNREADABLE`: fixture text for the rows above.

### Mocks
- none
