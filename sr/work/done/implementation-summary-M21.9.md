# Implementation summary: M21.9 init-passes-own-checks

## What changed

- `specy_road/init_project.py`: `run_init_project` calls the new `_write_generated` after the templates, AGENTS.md, ignore blocks and manifest. It reuses `generated_files.regenerate_generated_files` (skipped under `--dry-run`) and lists `roadmap.md` and `roadmap-context.md` with the nested-layout prefix.
- `specy_road/model_profiles.py`: `roster_profile_gaps` leaves out a non-launchable entry whose id is `STARTER_PLACEHOLDER_ID`; `closest_profile` returns a profile only at `CLOSEST_MIN_RATIO` (0.6) or higher; the hint text moved into `_profile_hint`.
- Below the cutoff the hint reads "no profile under model-profiles/ has a close name; add one or give the entry `profile:`". With no profiles at all, the text is unchanged.
- `docs/install-and-usage.md`: the new-project line and code block put the first commit before `validate` and drop `export`; the `init project` paragraph names both generated files and the skip rule.
- `CHANGELOG.md`: [Unreleased] Fixed entry.

## Decisions for review

- Skip-existing (coordinator confirmed): if either generated file exists without `--force`, neither is written and the existing ones are reported as skipped. `regenerate_generated_files` always writes both, so this is what protects a hand-written `roadmap.md`. The missing file then stays missing until `export` or `digest` is run.
- Hint text (coordinator decided): the shorter wording, with `tests/test_refresh_profiles_roster.py` updated to match. That test is renamed from `test_unrelated_roster_id_keeps_todays_text` to `test_unrelated_roster_id_names_no_profile`, since its text is no longer today's, and it also asserts no closest profile is named.
- `tests/upgrade_repo_helpers.py`: `old_repo` removes both generated files, because a 0.2.x scaffold had neither and init now writes them.
- `specy-road models list` still lists `my-executor` as an unmatched id: A2 covers the validate notice only.

## Known limits

- With `roadmap/manifest.json` missing and a broken leftover chunk file, init exits 1 from `load_roadmap` before printing its file list. Left as is: out of scope.
- `tests/test_worker_faults.py::test_output_clears_a_stall_shorter_than_the_write_window` failed once in a full run at load average about 37, then passed 5 of 5 alone. It is wall-clock dependent and this leaf does not touch it.

## Final touch zones

`specy_road/init_project.py`, `specy_road/model_profiles.py`, `tests/test_init_project_first_run.py`, `tests/test_init_project_reports.py`, `tests/test_model_profile_aliases.py`, `tests/test_refresh_profiles_roster.py`, `tests/upgrade_repo_helpers.py`, `docs/install-and-usage.md`, `CHANGELOG.md`

## Verification

Manual init into a scratch repo, flat and `sr/` layouts, first commit, then `validate`, `validate --strict`, `export --check` and `digest --check`: all exit 0 with no mention of `my-executor` or `vision.md`. This ran before the hint wording change, which does not affect that path.

The new tests in `tests/test_init_project_first_run.py` and `tests/test_init_project_reports.py` were run over the base source in a detached worktree: 7 failed, 6 passed.

## Added

- `init_project._write_generated`: writes and lists the two generated files (A1).
- Branch in `_write_generated` for an existing file without `--force`: keeps a hand-written `roadmap.md` from being overwritten.
- `model_profiles.STARTER_PLACEHOLDER_ID`: the one place the placeholder id lives (A2).
- `model_profiles.CLOSEST_MIN_RATIO`: the fixed 0.6 cutoff (A2).
- Guard in `closest_profile`: returns `None` below the cutoff (A2).
- `model_profiles._profile_hint`: holds the three hint texts, including the new below-cutoff one (A2).
- Filter in `roster_profile_gaps`: drops the non-launchable placeholder (A2).
- `test_a_new_project_passes_each_check_with_nothing_about_the_scaffold`, with helpers `_argv_main`, `_exit_code`, `_first_commit`: the four first-run checks in-process (A4).
- `test_generated_files_are_listed_and_only_the_real_run_writes_them`: dry run adds nothing and real files equal the list, flat and `sr/` (A1).
- `test_an_existing_roadmap_md_survives_unless_forced`: the skip-existing branch.
- `test_roster_profile_gaps_reports_and_hints_by_id_and_launchability`: the A3 table through public `roster_profile_gaps`.
- `test_the_template_roster_uses_the_placeholder_id_nothing_can_launch`: keeps the constant and the template from drifting (A2).
- Mocks: none.
