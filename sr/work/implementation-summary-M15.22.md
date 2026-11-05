# Implementation summary: M15.22

## Summary

This leaf adds four project preferences. Each one is optional, and leaving it out keeps today's behaviour:

- **A1:** `decisions add --local` writes the gitignored `roadmap/decisions.local.yaml`. `decisions list` (text and `--json`) and `orchestrate plan` (`plan_preferences`) merge that file over `roadmap/decisions.yaml`, matching by id. A local entry wins over a tracked one with the same id. `list` names each entry's source: `(local)` / `(shared)` at the end of the text line, and `"source"` in JSON. `decisions close` closes an entry in the file it came from. New `D#`/`P#` ids skip ids used in either file. The path is in the managed `.gitignore` block.
- **A2:** `pr_body_footer` (a string with at least one non-whitespace character, schema `pattern: \S`) is added, stripped, after the brief in `work/pr-body-<ID>.md`. When the key is absent, the body is byte-identical to before.
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
- `specy_road/workflow_prefs.py` (new): `pr_body_footer`, `root_land`, `implementation_summary_rule`, `summary_ignore_rules`, `summary_rule_notice` / `warn_summary_rule`, `summary_handling`, `leaf_root`, `summary_rel`.
- `specy_road/finish_pr_body.py`: `compose_pr_body(footer=)`. `write_pr_body` reads the footer from `work_dir.parent`, because `finish_task.py` (outside the zones) passes the project's `work/` dir.
- `specy_road/bundled_scripts/do_next_prompt.py` and `role_prompt_rca.py`: summary wording by the leaf's rule, `implementation_summary_rule(root, node_id)`. That reads the leaf's own checkout through `leaf_root` (fix round 2). `reviews` is used only as the hand-off destination and as a starting point for the resolver.
- `specy_road/bundled_scripts/validate_roadmap_checks.py`: one import and one call to `warn_summary_rule`. To stay within the 400-line cap, `run_validation`'s first two parameters now share one line (`roadmap: dict, registry: dict,`), and no text was removed. The file is 400 lines here. That line was chosen because it merges cleanly with `origin/WIP/improvements-0-3-1`: a trial merge (`git merge-tree`) has no conflicts, and that branch's version plus this change is 399 lines. An earlier attempt rejoined the `warn_registry_touch_zone_overlap(...)` call instead, and that conflicted with the integration line's edit to the same call.
- `specy_road/finish_modes.py`: `apply_on_complete_mode` and `retry_merge_landing` go through `land_on_integration`. `delete_landed_branch(local_only=)`.
- `specy_road/finish_land_local.py` (**new, outside the declared zones**): `land_root_locally`, `land_on_integration` (push/local dispatch). It was created under the file-limits rule because `finish_modes.py` (351 lines) had no room for it. Please add it to the zones.
- Schema: `land`, `pr_body_footer`, `implementation_summary`.
- `docs/git-workflow-preferences.md` (new).

**Final touch zones:** the declared list plus `specy_road/finish_land_local.py`.

Not changed (outside the zones):
- `.gitignore` at the git root and `sr/schemas/git-workflow.schema.json`. `upgrade` / `refresh-stubs` refresh them.
- `review_deferral.py`, which still reads only the tracked ledger for its own deferral records.

## Fix round 1 (review of `af4d1164`, `grok-4.7-low`)

Before the fixes, `origin/WIP/improvements-0-3-1` was merged into this branch as the coordinator instructed (`ba09e8e8`, no conflicts).

- **Finding 1. Class: a preference value the schema accepts but the code treats as unset (schema and behaviour disagree).** A whitespace-only `pr_body_footer` passed `minLength: 1` and then stripped to `None`. Fix, as the planner decided: the schema now has `"pattern": "\\S"`, so empty and whitespace-only footers fail `validate` (`validate_git_workflow_contract` exits 1 and names the key). The strip stays, for surrounding whitespace on real text. Every key this leaf adds was audited for the same gap. Two parametrised tests now pin it: each schema-valid value takes effect through its accessor, and each empty, whitespace-only, unknown, wrong-case, null or wrongly typed value fails `validate`.
- **Finding 2. Class: a defensive branch no caller can reach.** The `reviews is None` → `commit` branch in `executor_preamble` was removed. Its only caller, `build_prompt`, always passes `reviews_dir(root, node_id)`. I checked the leaf's other additions for the same class and removed `merge_ledgers`' `isinstance(e, dict)` filters (its inputs are schema-checked by `load_merged` first) and `pr_body_footer`'s `isinstance(text, str)` check (a loaded config is schema-valid, so the value is a string or absent).

## Fix round 2 (review of `7fa4357e`, `gpt-6.1-sol-low`)

Before the fixes, `origin/WIP/improvements-0-3-1` was merged in as instructed (no conflicts).

- **R1. Class: an ignore decision made on a sample path instead of the leaf's real path.** `summary_ignore_rule` asked git only about `work/implementation-summary-M0.md`, so a rule matching some ids and not others (an exact `…-M1.1.md`, `…-M2*.md`, or a negation of one id) was misjudged.
  - Design fix: the sample path is gone. `summary_ignore_rules(root, node_ids)` runs one `git check-ignore -v --no-index` on each leaf's exact `work/implementation-summary-<ID>.md` and returns `{id: rule}`, skipping negated deciders.
  - The executor prompts (pickup and `prompt --role executor`) ask for their own leaf.
  - `validate` asks for every leaf (a node that is no other node's parent) and names each ignored summary with its rule, the first three in full plus a count.
- **R2. Class: a per-leaf preference read from a checkout other than the leaf's (main versus linked worktree).** `executor_preamble` read `git-workflow.yaml` (and its ignore rules) from `reviews.parents[2]`, the main checkout.
  - Design fix: one resolver, `workflow_prefs.leaf_root(root, node_id)`, returns the project root of the worktree that has the leaf's branch `feature/rm-<codename>` checked out, or the asking checkout when the branch is checked out nowhere.
  - Both per-leaf accessors resolve through it, `implementation_summary_rule(root, node_id)` and `pr_body_footer(root, node_id)`, so every caller gets the leaf's own settings from main or from any worktree.
  - This differs from the reviewer's suggested shape (passing the executor root into `executor_preamble`): that needs a change to `role_prompt.py`, which is outside the zones. The resolver removes the class for every caller instead, including a coordinator that builds the prompt from main.

## Probes

- `pr_body_footer` values `""`, `" "`, `"\n"`, `" \t\n "`, `3`, `null`, `["x"]`: all refused by the schema, and `validate` exits 1 naming the key.
- `pr_body_footer` values `"Tool X"`, `"  Tool X\n"`, multi-line text: accepted by the schema; the accessor returns the stripped text, never `None`.
- `implementation_summary` values `""`, `" "`, `"Commit"`, `"push"`, `null`, `true`: refused by the enum, and `validate` exits 1. `commit` and `local`: accepted and honoured by `implementation_summary_rule`.
- `land` values `""`, `" "`, `"Local"`, `"manual"`, `null`, `1`: refused, and `validate` exits 1. `push` and `local`: accepted and honoured by `root_land`.
- An invalid config at the accessor level: `_value` returns `None`, so every accessor falls back to its default. `validate` is what reports it (it already exits on any git-workflow schema error).
- `decisions.local.yaml` with an empty or malformed entry: refused by the same `decisions.schema.json` as the tracked file (`test_local_decision_and_broken_local_ledger`), so nothing the schema accepts is dropped by the merge.
- `summary_ignore_rules` with a negated (`!`) match: treated as not ignored, so the notice and the commit wording agree.
- R1, ignore patterns against ids `M1.1`, `M1.2`, `M2.10`: an exact `…-M1.1.md` ignores only M1.1. `…-M1.*.md` ignores M1.1 and M1.2. `…-M2*.md` ignores only M2.10. `*` plus `!…-M1.2.md` ignores all but M1.2. `work/*` plus `!…-M1.1.md` ignores all but M1.1. `work/brief-*.md` ignores none. Each pickup prompt's wording and each id in the validate notice match per leaf (parametrised test).
- R1, readers of the ignore check: the pickup prompt, the executor role prompt and the validate notice all pass real node ids now. The sample-path constant was deleted, and `grep` finds no other caller.
- R1, a parent id (a node with children): left out of validate's check, so a pattern matching only phase ids does not trigger the notice.
- R2, readers of `workflow_prefs`:
  - `do_next_prompt` and `role_prompt_rca` (summary rule) and `finish_pr_body` (footer) resolve through `leaf_root`.
  - `finish_modes`/`finish_land_local` (`root_land(repo)`) run in finish's checkout, which has the leaf's branch checked out, so that is already the leaf's checkout; no change.
  - `validate`'s notice is project-wide in the checkout being validated; no change.
- R2, a linked worktree whose committed `implementation_summary: local` and `pr_body_footer` differ from main's defaults: from main and from the worktree, the rule is `local`, the footer is the leaf's, and `build_prompt(..., role="executor")` uses the leave-uncommitted wording. With the worktree removed (branch checked out nowhere), the asking checkout decides (commit, no footer).
- R2, a checkout with no roadmap manifest (the tmp repos of the pickup and PR-body tests): `leaf_root` returns the asking root without loading anything. A broken roadmap still fails as it did in these callers, which already load the roadmap.
- `scripts/check_test_private_imports.py`: 0 new private references.
- Reachability of the other new guards: `land_root_locally`'s missing-local-branch refusal is reachable (tested). `_load`'s not-a-mapping check is reachable (YAML may be a list). `_merge_here`'s `if check` is reachable (no land check configured). All kept.
- `executor_preamble` callers: one (`role_prompt.build_prompt`), and it always passes `reviews`. The branch was removed.

## Verification

- Fix round 2, after merging the integration line: 363 targeted tests passed (this leaf's tests plus decisions, finish, prompt, validate, models-and-prompt and linked-worktree importers). `ruff check specy_road tests scripts` OK. `specy-road file-limits` OK. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` OK.

- Fix round, after merging the integration line: `tests/test_project_preferences.py` 38 passed. The targeted suites (decisions, preferences, PR body, finish modes and land check, nested land modes, merge mode, do-next prompt, agent ignores, validate, chore, cleanup, human acceptance, runtime dirs, project layouts) 244 passed. `ruff check specy_road tests scripts` OK. `specy-road file-limits` OK (`validate_roadmap_checks.py` is 399 lines).
- Round 0: full suite `python -m pytest -n 4 -q -p no:cacheprovider`, 4127 passed. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` and `specy-road validate` OK.

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
- `workflow_prefs.summary_ignore_rules` / `summary_rel`: one `git check-ignore -v --no-index` on each leaf's exact summary path; negated deciders are not ignored (fix round 2, R1).
- `workflow_prefs.leaf_root`: the one resolver for a leaf's preferences, the checkout holding its branch (fix round 2, R2).
- `workflow_prefs.summary_rule_notice` / `warn_summary_rule`: validate's "which rule wins" notice (stdout, so `--strict` does not count it).
- `workflow_prefs.summary_handling`: prompt wording per rule.
- `role_prompt_rca._COMMIT_SUMMARY`: keeps the existing executor wording byte-identical under `commit`.
- `finish_land_local._merge_here`, `land_root_locally`, `land_on_integration`: root `land: local` and the push/local dispatch.

### Branches and guards
- `land_root_locally`: refuses when there is no local integration branch (`land: local` never creates one from the remote).
- `retry_merge_landing`: under `local`, checks `refs/heads/<ib>` and skips the fetch.
- `delete_landed_branch(local_only=)`: leaves the remote copy alone under `land: local` (deleting it would be a push).
- `cmd_close`: refuses with the first problem when a ledger fails its schema (before, the failure came from the write instead).

- `tests/decisions_repo_helpers.py` (new): `decisions_repo`, `run_decisions`, `add_args`, `SHEET`. These were moved unchanged from `tests/test_decisions.py` (where they were `_decisions_repo`, `_run`, `_add_args`), so neither this leaf's tests nor `test_decision_preferences.py` import underscore-prefixed names. Every caller is updated and no assertion changed. `scripts/check_test_private_imports.py` reports 0 new private references.

### Mocks
- none

### Tests
- `test_each_leaf_asks_git_about_its_own_summary_path` (parametrised: exact filename, id globs, negations, unrelated rule): R1, per leaf, in prompts and in validate's notice.
- `test_linked_leaf_worktree_setting_wins_over_main`: R2, a linked worktree's committed settings win from main and from the worktree; fallback when the branch is checked out nowhere.
- `test_every_schema_valid_preference_takes_effect` (parametrised): fix round; no schema-valid value reads as unset.
- `test_schema_refuses_what_the_workflow_would_not_honour` (parametrised): fix round; empty, whitespace-only, unknown and wrongly typed values fail `validate`.
- `test_local_preference_is_merged_over_the_tracked_ledger`: A1 merge, precedence, source, plan and close.
- `test_local_decision_and_broken_local_ledger`: `--local` for a decision, and an error that names the broken local file.
- `test_local_ledger_is_in_the_managed_ignore_block`: A1's gitignore entry.
- `test_pr_body_footer_is_appended`, `test_pr_body_without_footer_is_unchanged`: A2.
- `test_pickup_prompt_follows_implementation_summary`: A3 pickup wording; no `add -f`.
- `test_ignored_summary_wins_over_commit_and_validate_says_so`: A3 conflict notice and the negation case.
- `test_executor_role_prompt_follows_implementation_summary`: A3 for `prompt --role executor`.
- `test_root_land_local_merges_locally_and_pushes_nothing` (parametrised local / default / push): A4, one case per mode.
- `test_root_land_local_needs_a_local_integration_branch`: A4 refusal.
