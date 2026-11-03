# Implementation summary: `M11.76` — Every roster model reaches its profile notes

## What changed

- **validate reports unmatched roster ids (A1).** `run_validation` reports each
  working-tree roster entry with an `executor` or `reviewer` role that matches no
  model profile by `api_id`, file name or alias. An entry with a `profile:` path
  counts as matched, as it does for routing. Each report names the entry and the
  closest profile (by string similarity over each profile's `api_id`, file name and
  aliases), and says to list the id in that profile's `aliases` or give the entry
  `profile:`. `family: human` and coordinator-only entries are not reported.
  Matching reuses `unmatched_roster_ids` + `profile_for_entry`, so it is
  `Profile.for_id` over the roster, the same rule `models list` already reports.
  - **Launchable entry** (has a `harness` or a `channels.cli`): a `warning:` on
    stderr, which `validate --strict` counts.
  - **Entry nothing can launch** (neither key): a `notice:` on stdout, which
    `--strict` does not count.
- **How A1 is read, and why (coordinator decision).** A1's "warns" means a stderr
  warning for an unmatched entry that can be launched. That entry is the case the
  evaluation found: a running worker whose prompt lacked its profile's notes. An
  entry with neither `harness` nor `channels.cli` cannot be started by
  `worker delegate`, so no prompt is missing anything yet. The starter roster's
  placeholder `my-executor` is that case, and the toolkit requires a fresh scaffold
  to pass `validate --strict` with empty stderr (`tests/test_validate_strict.py`).
  Such an entry still gets the same text, naming the closest profile, as a stdout
  notice, like the unauthored-leaf notice. The coordinator ruled out changing the
  starter roster and relaxing those tests.
- **Shipped profiles alias the Cursor ids they cover (A1).** Each id in the shipped
  Cursor capture (`model-profiles/harness-captures/cursor/inventory-models.txt`)
  that is a profile's `api_id` or file name plus a suffix (a leading `cursor-`
  aside) is now in that profile's `aliases`. `cursor-grok-4.6-high`,
  `gpt-5.6-sol-high`, `grok-4.7-*` and `composer-2.5-fast` were already there; this
  adds the Claude Opus 5.5, Opus 5, Fable 5.1, Fable 5, Gemini 4 Argon,
  Gemini 3.8 Flash, Muse Spark 1.3 and Muse Wonder 1.0 ids (for example
  `claude-opus-5-5-high`, a Cursor executor in the toolkit's own roster that got no
  model notes).
- **Not aliased:** DeepSeek's Cursor ids (`deepseek-v41-flash-1017-*`) do not
  share the profile's `api_id` (`deepseek-flash`) or file-name form
  (`deepseek-v4.1-flash-1017`), so the rule does not tie them to a profile; I left
  them out rather than guess. Dotted ids like `claude-opus-5.5` are also not
  aliased: an alias becomes the id the harness is launched with, and the Claude
  Code profile documents `claude-opus-5-5`. validate now reports such ids and
  names `claude-opus-5-5.md` as the closest profile.

## Files

- `specy_road/model_profiles.py`: `closest_profile`, `roster_profile_gaps`; imports
  `load_orchestration_config` (no cycle: `orchestration_config` does not import
  `model_profiles`).
- `specy_road/bundled_scripts/validate_roadmap_checks.py`: calls
  `roster_profile_gaps` in `run_validation`. The file was at 399/400 lines, so
  the two function-local `from collections import Counter` imports became one
  top-level import to make room. No docstrings or comments were removed; the file
  is still 399 lines.
- `specy_road/templates/project/model-profiles/{anthropic-claude/claude-opus-5-5,claude-opus-5,claude-fable-5-1,claude-fable-5;google-gemini/gemini-4-argon,gemini-3.8-flash;meta-muse/muse-spark-1.3,muse-wonder-1.0}.md`:
  `aliases:` lists, placed after `api_id:`.
- `tests/test_model_profile_aliases.py`: three tests.

**Touch zones:** confirmed as listed; nothing outside them changed. The call site
`specy_road/bundled_scripts/validate_roadmap.py` (outside the zones) did not change,
because the warning is raised inside `run_validation`.

## Verification

- `pytest -n 4` (full suite): 3498 passed, 2 skipped, including
  `tests/test_validate_strict.py` and `tests/test_roster_source.py`.
- Red-green: with the source and profile changes reverted, the alias, warning and
  notice tests fail. With only the warning/notice split reverted (every gap a
  warning), the notice test and the 4 `test_validate_strict.py` scaffold tests fail.
- `specy-road file-limits` passes, and `ruff check` passes on the touched Python files.
- The warning text starts with `roster entry …`, not with the file path, so it does
  not collide with the `warning: roadmap/orchestration.yaml …` roster-drift
  warning that `tests/test_roster_source.py` checks for.

## Added

### Helpers
- `model_profiles.closest_profile`: picks the profile to name in the warning, by
  similarity over `api_id`, file name and aliases.
- `model_profiles.roster_profile_gaps`: `(launchable, message)` for each
  executor/reviewer roster entry no profile matches. It reuses
  `unmatched_roster_ids` and `profile_for_entry`.
- `model_profiles._launchable`: an entry has a `harness` or a `channels.cli`. This
  decides between a warning and a notice (coordinator's reading of A1).

### Branches / guards
- `roster_profile_gaps` returns `[]` when `orchestration.yaml` is absent or invalid.
  An invalid one already fails earlier in `validate_orchestration_contract`, and an
  absent one means the default roster, which is one human.
- `roster_profile_gaps` gives a "no profiles under model-profiles/" hint when the
  repo has no profiles at all.
- The `validate_roadmap_checks.run_validation` loop prints a launchable gap as
  `warning:` on stderr and any other gap as `notice:` on stdout, so a fresh
  scaffold's placeholder does not fail `--strict`.

### Mocks
- none

### Tests
- `test_validate_warns_for_an_unmatched_launchable_roster_id_and_names_the_closest_profile`:
  A1, unmatched entries with a `harness` (`claude-opus-5.5`) and with a
  `channels.cli` (`claude-opus-5.5-rev`) are stderr warnings that name the closest
  profile. A `profile:` entry, an alias-matched id (`claude-opus-5-5-high`), a human
  and a coordinator-only id are not reported.
- `test_validate_notes_an_unmatched_roster_id_nothing_can_launch_on_stdout`: A1,
  unmatched entries with neither key (`claude-opus-5.5`, `sol`) are stdout notices,
  not on stderr, and name the closest profile.
- `test_shipped_profiles_alias_every_cursor_id_that_extends_their_api_id`: A1,
  keeps the shipped aliases in line with the shipped Cursor capture, and checks
  that `closest_profile` maps a dotted id to its profile.
