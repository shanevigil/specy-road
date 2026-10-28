# Implementation summary for M3.9

## Summary

Worker and session CLI fixes from the 0.3.1rc1 triage (`docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`, rows on `{session}` resumes, roster provenance, sync gaps, `--path`, nested executor paths).

- **A1:** a roster `channels.cli` may name `{session_flag}`. On claude-code it expands to `--session-id <id>` on launch and to `--resume <id>` on `message` / `resume`, so one command, with its permission flags, serves the whole leaf. Codex, cursor and generic refuse it rather than guess. `prompt --channel cli` has no session, so there it expands to nothing. `docs/orchestration-workers.md` documents the placeholder and the `.claude/settings.json` permissions route.
- **A2:** `orchestrate plan` carries the ref the roster was read from (`roster_ref`). When the working-tree `roadmap/orchestration.yaml` is absent at that ref or differs from it, the plan carries `roster_drift`. An executor-less leaf then reports that sentence instead of the "needs a rostered executor with may_process …" hint. `validate` prints the same sentence as a warning. **Open:** in text mode, `orchestrate plan` prints the ref only inside that drift sentence; `--json` always includes `roster_ref`. A standing `roster: … at <ref>` line belongs in `render()` in `specy_road/bundled_scripts/orchestrate_cli.py`, which is outside the touch zones (see "Out-of-zone change needed").
- **A3:** `worker sync` reports sequence numbers missing between the acknowledged mark and the events it returns. They appear as `! gap: event(s) #a–#b missing from the log` in text and as `gaps` in `--json`. A gap is reported once: after `--ack` it is behind the mark.
- **A4:** `session start|touch|check --path` take several values after one flag, and the flag still repeats.
- **A5:** in the nested layout:
  - The executor prompt tells the worker to work from the git root and names the project root.
  - It gives the brief, summary, template and hand-off paths from the git root (`sr/work/...`).
  - The hand-off keeps its absolute main-checkout path and is labelled with its `sr/work/reviews/<ID>` form. An absolute path is the only one correct from both the main checkout and a linked worktree.
  - The precondition's bookkeeping excludes carry the prefix.
  - The brief gains one `Project root` line with the same paths, deterministic and with no host paths.
  - `worker delegate` copies the brief to the worktree's project root (`<wt>/sr/work/brief-<ID>.md`), not the git root's `work/`. Its own dirty check and `reconcile` match bookkeeping with the prefix stripped, so the moved brief is neither refused nor flagged.
  - The embedded layout's prompt and brief are unchanged.

## Changes

- `specy_road/worker_adapters.py`: `{session_flag}` placeholder, `Adapter.session_flag`, refusal on harnesses without one.
- `specy_road/orchestration_pinned.py`: `roster_source()`, which returns the ref plus a drift sentence.
- `specy_road/orchestrate_plan.py`: `roster_ref` / `roster_drift` on the plan; the drift replaces the executor hint.
- `specy_road/bundled_scripts/validate_roadmap.py`: the drift warning.
- `specy_road/worker_reconcile.py`: `gaps` in `sync`; prefix-aware `_bookkeeping`.
- `specy_road/bundled_scripts/worker_cli.py`: prints gaps.
- `specy_road/bundled_scripts/session_cli.py`: `--path` uses `extend` and `nargs="+"`.
- `specy_road/bundled_scripts/role_prompt.py`, `specy_road/bundled_scripts/generate_brief.py`: nested-layout paths.
- `specy_road/worker_ops.py`: brief location in a delegated worktree; prefix-aware dirty check.
- `docs/orchestration-workers.md`, `docs/orchestration.md`: A1–A5 behaviour. `orchestration.md` is at its 400-line cap, so the roster-source text joins an existing paragraph.
- `tests/test_worker_cli_fixes.py` (new); `tests/test_project_layouts.py` (see below).

Final touch zones: the ones on the integration branch (`a3ece83`). Every changed path is inside them. One more is needed for A2's text line: `specy_road/bundled_scripts/orchestrate_cli.py`.

**Test changed, not loosened:** `test_the_brief_is_identical_across_layouts` pinned byte-identical briefs across layouts, and A5 deliberately adds one line to the nested brief. The test now asserts:
- the embedded brief lacks that exact line;
- the nested brief has it exactly once;
- removing it makes the two briefs byte-identical.

Every other path difference is still caught.

## Verification

- `pytest` (full): 2255 passed, 2 skipped, 2 failed. The two failures, `tests/test_review_round6_evidence.py::test_committed_rename_into_the_zone_is_reported_on_both_sides` and `::test_rename_out_of_the_zone_keeps_the_source_inside_it`, fail identically on base `16d36ef` in a clean detached worktree. They call `review_packet._changed`, which `03f81a7` renamed to `changed_paths_section`. Not touched here.
- `pytest tests/test_worker_cli_fixes.py tests/test_worker_adapters.py tests/test_worker_review_round2.py`: 47 passed (after the last refactor).
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK. The fixture's `.specyrd/cache` written by these runs was removed afterwards.
- `specy-road file-limits`: OK. `ruff check specy_road tests scripts`: OK. `scripts/check_test_private_imports.py`: 0 new.
- `scripts/check_clones.py`: **not run**, because `pylint` is not installed in this environment.
- Live check on this checkout: `specy-road orchestrate plan --json` and `specy-road validate` both report that `roadmap/orchestration.yaml` differs from `refs/remotes/origin/WIP/improvements-0-3-1`. That is true here: this branch's roster is older than the integration branch's.

## Walkthrough

1. `tests/test_worker_cli_fixes.py::test_one_claude_command_launches_and_resumes_with_session_flag`: the same `channels.cli` gives `--session-id X` on launch and `--resume X` on resume.
2. `::test_a_roster_that_differs_from_the_integration_branch_is_named_not_the_may_process_hint`: the plan problem and the `validate` warning.
3. `::test_sync_reports_a_gap_in_event_sequence_numbers`: two lost lines produce one gap, reported once.
4. `::test_nested_prompt_and_brief_give_paths_from_the_git_root` and `::test_nested_delegate_puts_the_brief_under_the_worktrees_project_root`.

## Out-of-zone change needed

`specy_road/bundled_scripts/orchestrate_cli.py` `render()` needs one line, for example `roster: roadmap/orchestration.yaml at <plan.roster_ref>`, plus `! <plan.roster_drift>` when set. That would let text-mode `orchestrate plan` always print the ref, as A2 says. Everything it would print is already on the plan object.

## Added

- `Adapter.session_flag` / `ClaudeCode.session_flag`: what `{session_flag}` expands to per harness; `None` means unsupported.
- `Adapter._session_flag_check`: refuses `{session_flag}` on a harness without one, in `_custom` and in the generic launch (which bypasses `_custom`).
- `_SESSION` frozenset: the placeholders that make a custom command serve resume.
- `placeholder_problem` branch: refuses `<{session_flag}`, since it is arguments and not a file.
- `substitute_prompt(session_flag=…)`: values now return shell text, so `{session_flag}` can expand to several words.
- `orchestration_pinned.roster_source`: the ref plus the drift sentence; shared by the plan and `validate`.
- `OrchestrationPlan.roster_ref` / `roster_drift`, `assign_leaf(drift=…)`, `_pick_executor(drift=…)` branch: the drift replaces the misleading hint.
- `validate_orchestration_contract` drift warning: "validate warns the same way".
- `worker_reconcile._gaps` and the `gaps` key in `sync`; the gap line in `worker_cli.cmd_sync`: A3.
- `_bookkeeping(prefix=…)`: git names `sr/work/...`, and without this the moved brief would be refused by delegate and flagged by reconcile.
- `role_prompt._dirty_check(prefix)` (replaces `_DIRTY_CHECK`), `_where`, and the `prefix` parameters: A5. In the nested layout the old `:(top)work/...` excludes did not match the project's bookkeeping.
- `generate_brief._project_root_line` and the `_section_metadata(prefix=…)` parameter: A5.
- `worker_ops._brief_into` destination change and the dirty-check prefix: the brief sits where the nested prompt says.
- Mocks: none.
- Tests, all in `tests/test_worker_cli_fixes.py` (new), one per behaviour:
  - A1: `test_one_claude_command_launches_and_resumes_with_session_flag`, `test_session_flag_is_refused_where_it_has_no_meaning` (×3 harnesses), `test_session_flag_must_be_whole_arguments` (×2 shapes).
  - A2: `test_plan_names_the_roster_ref`, `test_a_roster_that_differs_from_the_integration_branch_is_named_not_the_may_process_hint`, `test_a_roster_absent_on_the_integration_branch_is_named`.
  - A3: `test_sync_reports_a_gap_in_event_sequence_numbers`.
  - A4: `test_path_takes_several_values_or_repeats` (×3 commands).
  - A5: `test_nested_prompt_and_brief_give_paths_from_the_git_root`, `test_nested_delegate_puts_the_brief_under_the_worktrees_project_root`.
  - Helper `_nested`: a two-branch nested review repo.
