# Implementation summary: M15.10 — try a roster before it lands

## What changed

- **A1** — `orchestrate plan --roster-from-worktree` (`specy_road/bundled_scripts/orchestrate_cli.py`) calls
  `build_orchestration_plan(..., roster_from_worktree=True)`, which loads through
  `pinned_config(root, worktree=True)` and `pinned_profile_for_entry(..., worktree=True)`
  (`specy_road/orchestration_pinned.py`). Text output starts with
  `DRY RUN: roster from the working tree, nothing may launch from this plan`; with `--json` the banner goes
  to stderr and the JSON has `roster_ref: "worktree"`. No other caller passes `worktree=True`, so `prompt`,
  `worker delegate`, `review delegate` and `grind-session` keep the integration-branch roster, and their
  parsers reject the flag.
- **A2** — `models list` (`models_cli.py`) prints `roster: roadmap/orchestration.yaml at <ref>` first. When the
  working tree's roster differs from the ref, it then prints `uncommitted roster changes` with the added,
  removed and changed ids (each with its changed fields), using the new `roster_diff()` in
  `orchestration_pinned.py`. `--json` has `roster_ref` and `uncommitted_roster_changes`.
- **A3** — new `specy_road/roster_local.py`: the `roster_add` list in `roadmap/orchestration.local.yaml` is
  checked against the roster entry schema, then merged after the pinned roster in `pinned_config`. Everything
  that routes through it (plan, prompt, worker delegate, review delegate) sees these entries. An id that is
  already in the pinned roster is refused, and so is an entry with `channels.cli`, or one whose profile has
  `access.cli`, unless the same file sets `allow_local_cli: true`. A refusal returns the default config plus
  the error, the same way an invalid availability overlay does. In `orchestrate plan`, local entries are
  tagged `[local]` in notes, and the plan gets a `local roster entries` line and `local_roster` in JSON. The
  availability overlay (`roster:`) is unchanged.
- Docs: new `docs/orchestration-roster.md` (`orchestration.md` is already at 400 lines), with pointers added to
  `docs/orchestration-models.md`.

## Touch zones (confirmed)

All edits stayed in the listed zones: `specy_road/orchestration_pinned.py`, `specy_road/roster_local.py` (new),
`specy_road/orchestrate_plan.py`, `specy_road/bundled_scripts/orchestrate_cli.py`,
`specy_road/bundled_scripts/models_cli.py`, `docs/orchestration-models.md`, `docs/orchestration-roster.md` (new),
`tests/test_roster_worktree_dry_run.py` (new). Callers outside the zones (`review_delegate`, `worker_ops_launch`,
`worker_lease`, `role_prompt` and others) were not edited. They pick up local entries through `pinned_config`'s
default arguments.

## Notes for reviewers

- The review gate (`effective_config` at the ref) still reads only the committed roster, so a review by a local
  reviewer does not count toward it. The new doc says this. Changing the gate was out of scope.
- In worktree mode, `roster_drift` is `None` because the plan reads the file the drift message is about.
- `roster_local.py` imports `_dates_to_iso` and `_semantic_error` from `orchestration_config` so the duplicate-id
  and date checks are the ones the committed roster gets.

## Verification

- `python -m pytest -n 4 -q`: 4033 passed.
- `specy-road file-limits`: OK.
- `ruff check` on the changed files: clean.

## Added

- `roster_local.load_local_roster`: reads and schema-checks `roster_add` and `allow_local_cli` from the local file (A3).
- `roster_local.merge_local_roster`: appends local entries; refuses an id clash and an un-allowed cli (`channels.cli` or a profile's `access.cli`) (A3).
- `roster_local.local_roster_ids`: the ids used for the `[local]` label in the plan (A3).
- `orchestration_pinned.WORKTREE_REF`: the `roster_ref` value `"worktree"` that marks a dry-run plan (A1).
- `pinned_config(..., worktree=False)` branch: reads the working tree's roster for the dry run only, then merges local entries (A1, A3).
- `pinned_profile_for_entry(..., worktree=False)` branch: uses the working-tree profile in a dry run, so a new uncommitted profile is shown as it would run (A1).
- `orchestration_pinned.roster_diff`: working tree vs ref, by entry id with changed fields (A2).
- `Candidate.local` field and the `[local]` tag in `describe`: labels local entries in plan notes (A3).
- `OrchestrationPlan.local_roster` field and JSON key: lists local ids in the plan (A3).
- `build_orchestration_plan(..., roster_from_worktree=False)` parameter: the dry-run switch (A1).
- `orchestrate_cli.DRY_RUN_BANNER`, the `--roster-from-worktree` flag, the banner as the first line (stderr under `--json`), and the `local roster entries` line (A1, A3).
- `models_cli._diff_lines` plus the ref line and the JSON keys `roster_ref` / `uncommitted_roster_changes` (A2).
- Guard: an invalid `allow_local_cli` (not a bool) or a non-list `roster_add` is reported, so a typo does not silently allow a cli.
- Test `test_worktree_dry_run_plans_the_uncommitted_roster_with_a_banner`: the banner comes first, the plan uses the worktree roster, JSON `roster_ref: worktree` (A1).
- Test `test_delegation_still_reads_the_integration_branch_roster`: `prompt` and `worker delegate` refuse opus, which is unavailable on dev but available in the working tree (A1).
- Tests `test_delegate_entry_points_refuse_the_flag` (worker, review) and `test_grind_session_refuses_the_flag`: no delegation entry point accepts the flag (A1).
- Test `test_models_list_names_the_ref_and_the_uncommitted_diff`: ref line, added/removed/changed with fields, JSON (A2).
- Test `test_roster_add_is_planned_labelled_local_and_used_for_delegation`: add, `[local]` label, the overlay still applies, `prompt` accepts the local id (A3).
- Test `test_roster_add_never_overrides_a_committed_id`: id clash refused (A3).
- Test `test_roster_add_cli_needs_allow_local_cli`: `channels.cli` and profile `access.cli` are refused, then allowed with `allow_local_cli: true` (A3).
- Test `test_roster_add_entries_are_schema_checked`: a malformed local entry is reported (A3).
- Mocks: none.
