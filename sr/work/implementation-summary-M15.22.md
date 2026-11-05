# Implementation summary: M15.22

## Summary

This leaf adds four project preferences. Each one is optional, and leaving it out keeps today's behaviour:

- **A1:** `decisions add --local` writes the gitignored `roadmap/decisions.local.yaml`. `decisions list` (text and `--json`) and `orchestrate plan` (`plan_preferences`) merge that file over `roadmap/decisions.yaml`, matching by id. A local entry wins over a tracked one with the same id. `list` names each entry's source: `(local)` / `(shared)` at the end of the text line, and `"source"` in JSON. `decisions close` closes an entry in the file it came from. New `D#`/`P#` ids skip ids used in either file. The path is in the managed `.gitignore` block.
- **A2:** `pr_body_footer` (a non-empty string in the schema) is added after the brief in `work/pr-body-<ID>.md`. When the key is absent, the body is byte-identical to before.
- **A3:** `implementation_summary: commit | local` chooses the summary wording in the pickup prompt (`do_next_prompt.py`) and in `prompt --role executor` (`role_prompt_rca.executor_preamble`).
  - `commit` keeps the existing wording.
  - `local` says to leave the summary uncommitted, because the review packet reads it from the worktree.
  - Neither prompt mentions `git add -f`. If `.gitignore` ignores the summary, the ignore rule wins over `commit`: the prompts use the local wording, and `validate` prints a stdout notice that names the rule (`source:line:pattern`) and says which rule wins.
- **A4:** Top-level `land: push | local` applies to the root repository in merge mode (and in auto mode's merge attempt).
  - `push` (the default) is unchanged.
  - `local` uses M14.4.1's semantics. It merges into the local integration branch (in another worktree that holds it, if that worktree is clean). Nested repos land first, bookkeeping is resolved deterministically, and the land check runs (a failure resets the branch). Nothing is fetched or pushed, and finish says so before and after.
  - The re-run path (`retry_merge_landing`) checks the local branch. Under `local`, `--delete-branch` leaves the remote copy alone.
  - Defaults are unchanged.

## Changes

- `specy_road/decisions.py`: adds `DECISIONS_LOCAL_REL`. `decisions_path(root, local=False)`. `add_entry`, `add_preference` and `close_entry` take `local`. `plan_preferences` reads the merged ledger; its message shapes are unchanged.
- `specy_road/decisions_local.py` (new): `load_merged`, `merge_ledgers`, `next_free_id`.
- `specy_road/bundled_scripts/decisions_cli.py`: `--local`, the merged `list`/`close`, and source labels.
- `specy_road/agent_ignores.py`: `roadmap/decisions.local.yaml` added to `GITIGNORE_LINES` and the note.
- `specy_road/workflow_prefs.py` (new): `pr_body_footer`, `root_land`, `implementation_summary_rule`, `summary_ignore_rule`, `summary_rule_notice` / `warn_summary_rule`, `summary_handling`.
- `specy_road/finish_pr_body.py`: `compose_pr_body(footer=)`. `write_pr_body` reads the footer from `work_dir.parent`, because `finish_task.py` (outside the zones) passes the project's `work/` dir.
- `specy_road/bundled_scripts/do_next_prompt.py` and `role_prompt_rca.py`: summary wording by rule. The executor preamble takes the project root from `reviews.parents[2]` (the main checkout's project root, where the tracked `git-workflow.yaml` lives), because its caller `role_prompt.py` is outside the zones.
- `specy_road/bundled_scripts/validate_roadmap_checks.py`: one call to `warn_summary_rule`. To stay under the 400-line cap, the multi-line `warn_registry_touch_zone_overlap(...)` call was rejoined onto 2 lines (no text was removed). The file is now 398 lines.
- `specy_road/finish_modes.py`: `apply_on_complete_mode` and `retry_merge_landing` go through `land_on_integration`. `delete_landed_branch(local_only=)`.
- `specy_road/finish_land_local.py` (**new, outside the declared zones**): `land_root_locally`, `land_on_integration` (push/local dispatch). It was created under the file-limits rule because `finish_modes.py` (351 lines) had no room for it. Please add it to the zones.
- Schema: `land`, `pr_body_footer`, `implementation_summary`.
- `docs/git-workflow-preferences.md` (new).

**Final touch zones:** the declared list plus `specy_road/finish_land_local.py`.

Not changed (outside the zones):
- `.gitignore` at the git root and `sr/schemas/git-workflow.schema.json`. `upgrade` / `refresh-stubs` refresh them.
- `review_deferral.py`, which still reads only the tracked ledger for its own deferral records.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider tests/test_project_preferences.py`: 13 passed.
- Related suites (decisions, preferences, PR body, finish modes and land check, nested land modes, merge mode, do-next prompt, agent ignores, validate, chore, cleanup, human acceptance, runtime dirs): 283 passed.
- Full suite `python -m pytest -n 4 -q -p no:cacheprovider`: 4127 passed.
- `specy-road file-limits` OK. `ruff check` (C901) OK on all changed files. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` and `specy-road validate` OK.

## Walkthrough

1. `tests/test_project_preferences.py::test_local_preference_is_merged_over_the_tracked_ledger` covers A1: merge, local-wins precedence, source labels, `plan_preferences`, and close.
2. `test_pr_body_footer_is_appended` / `test_pr_body_without_footer_is_unchanged` cover A2.
3. The three A3 tests cover pickup and executor prompts under `commit`, `local` and an ignored summary, plus the validate notice and a negated ignore rule.
4. `test_root_land_local_merges_locally_and_pushes_nothing[local|None|push]` covers A4: the bare remote is unchanged under `local` and pushed under push/default.

## Added

### Helpers
- `decisions_local._load`: reads one ledger and lists its problems, each naming the file (so `list`/`plan` say which file is broken).
- `decisions_local.merge_ledgers`: local-over-shared merge by id. This is the A1 precedence rule.
- `decisions_local.load_merged`: the one merged read used by `list`, `close` and `plan_preferences`.
- `decisions_local.next_free_id`: auto ids skip ids used in either file, so a new entry never hides one in the other file by accident.
- `workflow_prefs._value`, `pr_body_footer`, `root_land`, `implementation_summary_rule`: config accessors with defaults when the config is unreadable.
- `workflow_prefs.summary_ignore_rule`: `git check-ignore -v --no-index` on a sample summary path. It treats a negated (`!`) match as not ignored.
- `workflow_prefs.summary_rule_notice` / `warn_summary_rule`: validate's "which rule wins" notice (stdout, so `--strict` does not count it).
- `workflow_prefs.summary_handling`: prompt wording per rule.
- `role_prompt_rca._COMMIT_SUMMARY`: keeps the existing executor wording byte-identical under `commit`.
- `finish_land_local._merge_here`, `land_root_locally`, `land_on_integration`: root `land: local` and the push/local dispatch.

### Branches and guards
- `land_root_locally`: refuses when there is no local integration branch (`land: local` never creates one from the remote).
- `retry_merge_landing`: under `local`, checks `refs/heads/<ib>` and skips the fetch.
- `delete_landed_branch(local_only=)`: leaves the remote copy alone under `land: local` (deleting it would be a push).
- `executor_preamble`: `reviews` absent → `commit`. That is a defensive default; the only caller always passes `reviews`.
- `cmd_close`: refuses with the first problem when a ledger fails its schema (before, the failure came from the write instead).

### Mocks
- none

### Tests
- `test_local_preference_is_merged_over_the_tracked_ledger`: A1 merge, precedence, source, plan and close.
- `test_local_decision_and_broken_local_ledger`: `--local` for a decision, and an error that names the broken local file.
- `test_local_ledger_is_in_the_managed_ignore_block`: A1's gitignore entry.
- `test_pr_body_footer_is_appended`, `test_pr_body_without_footer_is_unchanged`: A2.
- `test_schema_checks_the_new_keys`: the three schema keys accept and refuse values as specified.
- `test_pickup_prompt_follows_implementation_summary`: A3 pickup wording; no `add -f`.
- `test_ignored_summary_wins_over_commit_and_validate_says_so`: A3 conflict notice and the negation case.
- `test_executor_role_prompt_follows_implementation_summary`: A3 for `prompt --role executor`.
- `test_root_land_local_merges_locally_and_pushes_nothing` (parametrised local / default / push): A4, one case per mode.
- `test_root_land_local_needs_a_local_integration_branch`: A4 refusal.
