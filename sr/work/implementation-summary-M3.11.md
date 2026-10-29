# Implementation summary for M3.11

## Summary

All nine acceptance items are covered. Item by item:

- **A1:** done through profile `aliases`, not roster `launch_model`. A profile's front matter may list `aliases`, and a roster `id` that is one of them resolves to that profile, so `prompt` carries its notes. This works with or without `profile:`, from the working tree and from the pinned integration branch. A profile matched this way reports the alias as its `api_id`. That keeps `worker delegate` passing the harness the id it lists: Cursor only has effort-suffixed ids such as `claude-opus-5-5-high` and `gpt-5.6-sol-high`, with no bare `claude-opus-5-5` (`agent --list-models`, 2026.10.22). Before this change, such an id found no profile and launched as itself. Without that `api_id` rule it would have launched as the bare `api_id` and failed. A malformed `aliases` (not a list of strings) is a profile error, since a string would match by substring.
  - Why not `launch_model`: it would need `specy_road/templates/project/schemas/orchestration.schema.json`, where roster entries have `additionalProperties: false`, and `specy_road/worker_ops.py`. Both are outside the touch zones.
- **A2:** `review-packet -o <path>` writes the copy and also always writes `work/reviews/<ID>/PACKET.md`. That is the only path `prompt --role reviewer` reads.
- **A3:** the reviewer precondition now names the checkout to run its `git status` in: the one that has the leaf branch checked out (the registered branch, else `--ref`). That is usually the leaf's worktree, and `git worktree list` names it. If no checkout has it, the check is skipped. It leaves out only this leaf's exact brief, implementation summary, two prompt forms and review directory. Every other tracked or untracked path still counts. The executor precondition is unchanged.
- **A4:** session records now keep the `$USER` that started them. `session end <id>` retires another session's record when the same user started it, and refuses otherwise, naming the owner. `session end` with no id, and `--agent`, behave as before.
- **A5:** checked on fresh worktrees with agent 2026.10.22:
  - with neither `--trust` nor `--force`, `agent -p` exits 1 with "Pass --trust, --yolo, or -f if you trust this directory";
  - with `--trust` alone it succeeds;
  - the adapter's new default argv (`--force --trust`) succeeds on a fresh worktree.
  The old default only got past the prompt because `--force` implies trust. Launch and resume now pass `--trust` explicitly.
- **A6:** `docs/orchestration-workers.md` now has a Cursor CLI section covering:
  - the binary is `agent` (also `cursor agent`; `cursor-agent` is an older alias), not the `cursor` editor launcher;
  - login is `agent login` or `CURSOR_API_KEY`;
  - `--trust` and why it is needed;
  - a roster entry with `preflight: agent status`.
  It also notes, as measured, that `agent status` exits 0 even when logged out, and gives a variant that also stops on that.
- **A7:** no code change. `prompt --role reviewer --ref <ref>` already rendered for an unclaimed Complete node, and `test_reviewer_prompt_takes_ref_for_a_complete_node_without_a_claim` covers it. I extended that test to check that the precondition names the `--ref`.
- **A8:** `review-packet` warns on stderr when the merge-base diff is empty and explains why in the packet. `--base <ref>` diffs from the merge base with `<ref>` and leaves the commit under review unchanged. A `--base` that does not resolve exits 1.
- **A9:** `validate` prints one notice on stdout when `roadmap/orchestration.yaml` is absent, saying the default policy (one reviewer, any family, roster of one human) applies. It goes to stdout because `--strict` counts stderr lines. It is printed from `validate`'s own `main()`, not from `validate_at`, which pickup, roadmap edits, upgrade and migration also run. It is skipped when `--generate-orchestration` writes the file.

Touch zones: the listed zones were accurate. The only file outside them that A1 would have needed is the roster schema (plus `worker_ops.py`), which is why A1 uses the aliases route.

### Review round 1

Grok blocked on one correctness finding, which is fixed. `pinned_profile_for_entry`'s search without `profile:` asked `for_id` of whatever `_pinned_at` returned. A working tree that differs from the integration branch comes back with no front matter, so an alias (or an `api_id` that is not the file name) did not match and the drift error was dropped. `prompt` then wrote a prompt with no notes, and `delegate` launched. The search now matches the committed text. When that text is the roster id and the pinned copy is not ok, the not-ok profile is returned, so the drift error is kept. The alias is reported as `api_id` only when the pinned copy is ok. `test_a_dirty_alias_matched_profile_is_refused` covers an alias id and the bare `api_id` after one extra newline, and `build_prompt` returns the drift error.

`test_prerelease_s2.py::test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes` does not fail on this branch. The READY's exit 1 was a full-suite run taken while the reviewer wording had dropped the phrase "lists changes you did not make", which that test searches for. The phrase was put back in `ce265b4`, before the summary commit, and the test was re-run then (61 passed, including it). Re-run again with this fix: `tests/test_prerelease_s2.py` passes. It does not fail on `origin/WIP/improvements-0-3-1` (`87bcca`) or on this branch's base (`81d9be1`): both still contain that phrase in `role_prompt.py`, and neither changes the test. The branch caused the failure only in that uncommitted wording.

### Merge of origin/WIP/improvements-0-3-1 (M3.10 landed)

`ca77525` merges `origin/WIP/improvements-0-3-1` at `73f7b23`. The only conflict was the adapter table in `docs/orchestration-workers.md`. The resolution keeps both:
- M3.10's text: `--add-dir` for claude-code in a linked worktree, and the codex and cursor notes on where READY goes;
- this leaf's `--trust` on the cursor launch and resume.

`specy_road/worker_adapters.py` merged cleanly, with both M3.10's `--add-dir` and `--trust`.

`file-limits` fails on the integration branch itself: `specy_road/bundled_scripts/worker_cli.py` is 408 lines and `specy_road/worker_adapters.py` is 430, against a 400 cap. My `--trust` change had added 2 lines to `worker_adapters.py`. I folded the cursor notes string and the launch comment, so after the merge the file is 430 lines, the same as `origin/WIP`. I did not trim M3.10's overage. `worker_cli.py` is outside this leaf's touch zones, and taking 30 lines out of `worker_adapters.py` is a refactor this leaf did not ask for.

### Review after the WIP merge

Sol blocked A3 because the reviewer check excluded the entire project `work/` tree. That hid tracked files such as `work/README.md` and arbitrary untracked files. Fixed in `1e9793b`: the generated exclusions are now node-specific:

- `work/brief-<ID>.md`
- `work/implementation-summary-<ID>.md`
- `work/prompt-<ID>.md` and `work/prompt-<ID>-*.md`
- `work/reviews/<ID>/`

The project prefix is retained for nested layouts. The behavioral test now proves all four generated forms are ignored, while a modified tracked `work/README.md`, another leaf's untracked prompt, and an untracked source file are reported. The docs now state the narrower contract. As requested, this review fix does not address the integration branch's `worker_cli.py` / `worker_adapters.py` file-limit issue.

## Changes

- `specy_road/model_profiles.py`: `Profile.alias` field, `Profile.for_id`, an `aliases` shape check, and `profile_for_entry` matching through `for_id`.
- `specy_road/orchestration_pinned.py`: `pinned_profile_for_entry` matches through `for_id`, in both the `profile:` path and the search. The search (`_pinned_for_id`) matches a refused copy against the committed text and returns that refusal.
- `specy_road/bundled_scripts/role_prompt.py`: `_reviewer_precondition`.
- `specy_road/bundled_scripts/review_packet.py`: `--base` (`_with_base`), the empty-diff note and warning (`_empty_diff_reason`), and `-o` writing the canonical copy too.
- `specy_road/session_presence.py`: `current_user()` and the `user` field on records.
- `specy_road/bundled_scripts/session_cli.py`: `session end [ID]` (`_retire`).
- `specy_road/worker_adapters.py`: `--trust` on cursor launch and resume.
- `specy_road/bundled_scripts/validate_roadmap.py`: `NO_ORCHESTRATION_NOTICE`, printed by `main()`.
- Docs: `docs/orchestration-workers.md` (Cursor CLI section, adapter table, permissions), `docs/orchestration-models.md` (`aliases`, reviewer precondition), `docs/orchestration.md` (`review-packet --base` / `-o` / empty diff, `session end <id>`). `docs/orchestration.md` is held at its 400-line cap.

## Verification

- `python -m pytest -q` ran the whole suite before the phrase was restored: 2378 passed, 2 skipped, 1 failed (`test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes`). The phrase is back in the committed wording. After that, and again after the round-1 fix: `tests/test_prerelease_s2.py`, `tests/test_models_and_prompt.py`, `tests/test_review_round6_policy.py` — 36 passed. Earlier, `tests/test_prerelease_s2.py`, `tests/test_models_and_prompt.py`, `tests/test_project_layouts.py` (61 passed) and `tests/test_review_packet.py`, `tests/test_review_hardening.py`, `tests/test_review_round6_evidence.py` (44 passed).
- After the merge, 15 focused test files: 203 passed. They cover workers (adapters, the M3.10 reconcile/status tests, CLI, review rounds 1 and 2, prerelease), models and prompt, round-6 policy, prerelease §2, review packet, sessions, orchestration config, `validate --strict` and project layouts. After folding the cursor notes, `tests/test_worker_adapters.py`, `tests/test_worker_cli.py` and `tests/test_worker_m310_reconcile_status.py` were re-run: 25 passed.
- After the A3 review fix: `tests/test_prerelease_s2.py`, `tests/test_models_and_prompt.py`, `tests/test_project_layouts.py`, `tests/test_worker_cli_fixes.py` — 84 passed; focused `ruff` and `git diff --check` passed.
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK before the merge. After the merge it reports only `worker_cli.py` (408) and `worker_adapters.py` (430). Both counts are the same on `origin/WIP` (above).
- `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`: all OK.
- `python scripts/check_test_private_imports.py`: 0 new. Its one stale baseline entry is in `test_review_round6_evidence.py`, which this leaf does not touch.
- `python scripts/check_clones.py` could not run: `pylint` is not installed in this environment.
- Manual A5 runs against throwaway repos under `/tmp`, with `agent` 2026.10.22 logged in, as described above.

## Added

- helper `Profile.for_id` (model_profiles.py): one match rule (`api_id`, file name, `aliases`) shared by the working-tree and pinned lookups, replacing the two inline comparisons.
- helper `_pinned_for_id` (orchestration_pinned.py): the no-`profile:` search. A refused pinned copy has no front matter, so the committed text is what `for_id` sees, and the refusal is what is returned. Round-1 review finding.
- field `Profile.alias`: lets an alias-matched profile report the harness's own id as `api_id`, so worker launch keeps passing a valid id without touching `worker_ops.py`.
- guard: `aliases` must be a list of strings (`_structure_errors`). This is a profile-file boundary; `aliases: x-high` would otherwise match by substring. Tested in `test_broken_profile_reports_errors`.
- helper `_reviewer_precondition` (role_prompt.py): the reviewer's precondition differs from the executor's in checkout and uses node-specific generated bookkeeping pathspecs.
- helper `_with_base` (review_packet.py) and its guard for a `--base` that does not resolve (CLI boundary; tested).
- helper `_empty_diff_reason` (review_packet.py): one sentence used for both the stderr warning and the packet note.
- helper `current_user()` (session_presence.py), extracted from `default_agent_id`, plus the `user` record field.
- helper `_retire` (session_cli.py), with three branches, all tested: an invalid id (CLI boundary, the `ValueError` from `session_path`), no record, and a record from another user (or one that does not load).
- constant `NO_ORCHESTRATION_NOTICE` (validate_roadmap.py).
- test `test_an_effort_suffixed_roster_id_finds_its_profile_through_aliases`: A1, covering notes in the prompt, the launch id, and that the plain id is unchanged.
- test `test_a_dirty_alias_matched_profile_is_refused`: a one-newline local edit of an alias-matched profile is the drift error for the alias and for the `api_id`, and `build_prompt` returns it. Round-1 regression.
- test `test_an_empty_merge_base_diff_is_explained_and_base_sets_the_range`: A8.
- test `test_cli_end_with_an_id_retires_only_the_same_users_session`: A4.
- extended `test_main_writes_packet_file` (A2), `test_reviewer_prompt_needs_a_packet_and_embeds_it` and `test_reviewer_prompt_takes_ref_for_a_complete_node_without_a_claim` (A3, A7), `test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes` (A3: this leaf's generated files are ignored, while tracked `work/` files and another leaf's prompt remain visible), `test_default_commands_follow_the_documented_cli_flags` (A5), `test_init_writes_the_starter_and_validate_generates_it_when_missing` (A9), and `test_broken_profile_reports_errors` (the aliases guard).
- mocks: none. The tests use `monkeypatch.setenv` for `USER` and `SPECY_ROAD_AGENT_ID`.
