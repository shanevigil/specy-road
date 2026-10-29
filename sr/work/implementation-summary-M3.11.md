# Implementation summary for M3.11

## Summary

All nine acceptance items are covered. Item by item:

- **A1:** done through profile `aliases`, not roster `launch_model`. A profile's front matter may list `aliases`, and a roster `id` that is one of them resolves to that profile, so `prompt` carries its notes. This works with or without `profile:`, from the working tree and from the pinned integration branch. A profile matched this way reports the alias as its `api_id`. That keeps `worker delegate` passing the harness the id it lists: Cursor only has effort-suffixed ids such as `claude-opus-5-5-high` and `gpt-5.6-sol-high`, with no bare `claude-opus-5-5` (`agent --list-models`, 2026.10.22). Before this change, such an id found no profile and launched as itself. Without that `api_id` rule it would have launched as the bare `api_id` and failed. A malformed `aliases` (not a list of strings) is a profile error, since a string would match by substring.
  - Why not `launch_model`: it would need `specy_road/templates/project/schemas/orchestration.schema.json`, where roster entries have `additionalProperties: false`, and `specy_road/worker_ops.py`. Both are outside the touch zones.
- **A2:** `review-packet -o <path>` writes the copy and also always writes `work/reviews/<ID>/PACKET.md`. That is the only path `prompt --role reviewer` reads.
- **A3:** the reviewer precondition now names the checkout to run its `git status` in: the one that has the leaf branch checked out (the registered branch, else `--ref`). That is usually the leaf's worktree, and `git worktree list` names it. If no checkout has it, the check is skipped. The check leaves out all of `work/`, so the coordinator's prompts and packets in the main checkout no longer make a reviewer report "not landed". The executor precondition is unchanged.
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

## Changes

- `specy_road/model_profiles.py`: `Profile.alias` field, `Profile.for_id`, an `aliases` shape check, and `profile_for_entry` matching through `for_id`.
- `specy_road/orchestration_pinned.py`: `pinned_profile_for_entry` matches through `for_id`, in both the `profile:` path and the search.
- `specy_road/bundled_scripts/role_prompt.py`: `_reviewer_precondition`.
- `specy_road/bundled_scripts/review_packet.py`: `--base` (`_with_base`), the empty-diff note and warning (`_empty_diff_reason`), and `-o` writing the canonical copy too.
- `specy_road/session_presence.py`: `current_user()` and the `user` field on records.
- `specy_road/bundled_scripts/session_cli.py`: `session end [ID]` (`_retire`).
- `specy_road/worker_adapters.py`: `--trust` on cursor launch and resume.
- `specy_road/bundled_scripts/validate_roadmap.py`: `NO_ORCHESTRATION_NOTICE`, printed by `main()`.
- Docs: `docs/orchestration-workers.md` (Cursor CLI section, adapter table, permissions), `docs/orchestration-models.md` (`aliases`, reviewer precondition), `docs/orchestration.md` (`review-packet --base` / `-o` / empty diff, `session end <id>`). `docs/orchestration.md` is held at its 400-line cap.

## Verification

- `python -m pytest -q` ran the whole suite: 2378 passed, 2 skipped, 1 failed. The failure was `test_prerelease_s2.py::test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes`, which finds the command by the phrase "lists changes you did not make". I restored that phrase in the reviewer wording rather than change the test's assertions, and extended the test with a coordinator prompt file under `work/`, which is A3's case. That file and the affected suites then passed: `tests/test_prerelease_s2.py`, `tests/test_models_and_prompt.py`, `tests/test_project_layouts.py` (61 passed), and `tests/test_review_packet.py`, `tests/test_review_hardening.py`, `tests/test_review_round6_evidence.py` (44 passed).
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK.
- `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`: all OK.
- `python scripts/check_test_private_imports.py`: 0 new. Its one stale baseline entry is in `test_review_round6_evidence.py`, which this leaf does not touch.
- `python scripts/check_clones.py` could not run: `pylint` is not installed in this environment.
- Manual A5 runs against throwaway repos under `/tmp`, with `agent` 2026.10.22 logged in, as described above.

## Added

- helper `Profile.for_id` (model_profiles.py): one match rule (`api_id`, file name, `aliases`) shared by the working-tree and pinned lookups, replacing the two inline comparisons.
- field `Profile.alias`: lets an alias-matched profile report the harness's own id as `api_id`, so worker launch keeps passing a valid id without touching `worker_ops.py`.
- guard: `aliases` must be a list of strings (`_structure_errors`). This is a profile-file boundary; `aliases: x-high` would otherwise match by substring. Tested in `test_broken_profile_reports_errors`.
- helper `_reviewer_precondition` (role_prompt.py): the reviewer's precondition differs from the executor's in checkout and pathspec.
- helper `_with_base` (review_packet.py) and its guard for a `--base` that does not resolve (CLI boundary; tested).
- helper `_empty_diff_reason` (review_packet.py): one sentence used for both the stderr warning and the packet note.
- helper `current_user()` (session_presence.py), extracted from `default_agent_id`, plus the `user` record field.
- helper `_retire` (session_cli.py), with three branches, all tested: an invalid id (CLI boundary, the `ValueError` from `session_path`), no record, and a record from another user (or one that does not load).
- constant `NO_ORCHESTRATION_NOTICE` (validate_roadmap.py).
- test `test_an_effort_suffixed_roster_id_finds_its_profile_through_aliases`: A1, covering notes in the prompt, the launch id, and that the plain id is unchanged.
- test `test_an_empty_merge_base_diff_is_explained_and_base_sets_the_range`: A8.
- test `test_cli_end_with_an_id_retires_only_the_same_users_session`: A4.
- extended `test_main_writes_packet_file` (A2), `test_reviewer_prompt_needs_a_packet_and_embeds_it` and `test_reviewer_prompt_takes_ref_for_a_complete_node_without_a_claim` (A3, A7), `test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes` (A3: a coordinator prompt under `work/` is ignored), `test_default_commands_follow_the_documented_cli_flags` (A5), `test_init_writes_the_starter_and_validate_generates_it_when_missing` (A9), and `test_broken_profile_reports_errors` (the aliases guard).
- mocks: none. The tests use `monkeypatch.setenv` for `USER` and `SPECY_ROAD_AGENT_ID`.
