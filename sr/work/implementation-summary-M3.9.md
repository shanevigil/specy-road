# Implementation summary for M3.9

## Summary

Worker and session CLI fixes from the 0.3.1rc1 triage (`docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`, rows on `{session}` resumes, roster provenance, sync gaps, `--path`, nested executor paths).

- **A1:** a roster `channels.cli` may name `{session_flag}`. On claude-code it expands to `--session-id <id>` on launch and to `--resume <id>` on `message` / `resume`, so one command, with its permission flags, serves the whole leaf. Codex, cursor and generic refuse it rather than guess. `prompt --channel cli` has no session, so there it expands to nothing. `docs/orchestration-workers.md` documents the placeholder and the `.claude/settings.json` permissions route.
- **A2:** text-mode `orchestrate plan` always prints `roster: roadmap/orchestration.yaml at <ref>` under the policy line (`in the working tree (not a git checkout)` outside git); `--json` carries `roster_ref`. When the working-tree `roadmap/orchestration.yaml` is absent at that ref or differs from it, the plan prints `! <sentence>` under that line (`roster_drift` in `--json`). An executor-less leaf then reports that sentence instead of the "needs a rostered executor with may_process …" hint. `validate` prints the same sentence as a warning.
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
- `specy_road/bundled_scripts/orchestrate_cli.py`: `render()` prints the roster line and the drift.
- `specy_road/bundled_scripts/validate_roadmap.py`: the drift warning.
- `specy_road/worker_reconcile.py`: `gaps` in `sync`; prefix-aware `_bookkeeping`.
- `specy_road/bundled_scripts/worker_cli.py`: prints gaps.
- `specy_road/bundled_scripts/session_cli.py`: `--path` uses `extend` and `nargs="+"`.
- `specy_road/bundled_scripts/role_prompt.py`, `specy_road/bundled_scripts/generate_brief.py`: nested-layout paths.
- `specy_road/worker_ops.py`: brief location in a delegated worktree; prefix-aware dirty check.
- `docs/orchestration-workers.md`, `docs/orchestration.md`: A1–A5 behaviour. `orchestration.md` is at its 400-line cap, so the roster-source text joins an existing paragraph.
- `tests/test_worker_cli_fixes.py` (new); `tests/test_project_layouts.py` (see below).
- Review round 1 (gpt-5.6-sol-high blocked `7fb5839` because the new test imported private helpers from other test modules). The helpers it needs are now public where they live, renamed in place with no aliases and no copies:
  - `tests/test_worker_cli.py`: `_roster` → `worker_roster`, `_cli` → `run_worker_cli`, `_wait` → `wait_for_worker`.
  - `tests/test_orchestrate_plan.py`: `_repo` → `plan_repo`, `_only` → `only_assignment`.
  - Every existing importer of `_cli` / `_wait` was updated to the new names: `tests/test_review_round4_sol.py`, `tests/test_worker_review_round1.py`, `tests/test_review_round6_ops.py`, `tests/test_review_round6_runner.py`, `tests/test_worker_review_round2.py`.
  - Only the names changed, so no assertion or test body changed. `test_worker_cli._repo` stays private because the new test does not use it.
  - Moving them into `tests/helpers.py` was the other option offered. It would need `make_review_repo`, and `tests/review_repo_helpers.py` already imports `tests/helpers.py`, so that path means an import cycle or a copy the clone gate counts.
- `WIP/improvements-0-3-1` (`b89715b`) merged in as `0a86214`, which brings the integration branch's fix for the two renamed-helper failures (`0f0c662`).

Final touch zones: the ones on the integration branch (`b0c6d5c`, which added `specy_road/bundled_scripts/orchestrate_cli.py`). Every path this leaf changes is inside them; the merge commit `0a86214` carries the integration branch's own changes.

**Test changed, not loosened:** `test_the_brief_is_identical_across_layouts` pinned byte-identical briefs across layouts, and A5 deliberately adds one line to the nested brief. The test now asserts:
- the embedded brief lacks that exact line;
- the nested brief has it exactly once;
- removing it makes the two briefs byte-identical.

Every other path difference is still caught.

## Verification

- `pytest` (full, after merging `WIP/improvements-0-3-1`): 2267 passed, 2 skipped, 0 failed.
- `pytest` over the renamed helpers' modules and the new tests (`tests/test_worker_cli_fixes.py`, `test_worker_cli.py`, `test_orchestrate_plan.py`, `test_review_round4_sol.py`, `test_worker_review_round1.py`, `test_review_round6_ops.py`, `test_review_round6_runner.py`, `test_worker_review_round2.py`, `test_review_round6_evidence.py`): 148 passed.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK. The fixture's `.specyrd/cache` written by these runs was removed afterwards.
- `specy-road file-limits`: OK. `ruff check specy_road tests scripts`: OK.
- `scripts/check_test_private_imports.py`: exit 0, 117 current, 118 baselined, 0 new. It also prints one stale entry, `tests/test_review_round6_evidence.py: …review_packet._changed`. The integration branch's own fix removed that reference; the baseline in `constraints/` is outside this leaf's zones and was left as is.
- `scripts/check_clones.py --pylint <scratch venv>/bin/pylint` (pylint 4.1.3, as CI pins, in a throwaway venv): 12 current, 12 baselined, 0 new.
- Live check on this checkout after the merge: `specy-road orchestrate plan` prints `roster: roadmap/orchestration.yaml at refs/remotes/origin/WIP/improvements-0-3-1` with no drift line, and `specy-road validate` prints no roster warning. That is correct: the merge brought the branch's roster level with the integration branch. Before the merge both reported the difference, which was real then.

## Walkthrough

1. `tests/test_worker_cli_fixes.py::test_one_claude_command_launches_and_resumes_with_session_flag`: the same `channels.cli` gives `--session-id X` on launch and `--resume X` on resume.
2. `::test_text_plan_always_names_the_roster_ref` (the text output, clean and drifted) and `::test_a_roster_that_differs_from_the_integration_branch_is_named_not_the_may_process_hint` (the plan problem and the `validate` warning).
3. `::test_sync_reports_a_gap_in_event_sequence_numbers`: two lost lines produce one gap, reported once.
4. `::test_nested_prompt_and_brief_give_paths_from_the_git_root` and `::test_nested_delegate_puts_the_brief_under_the_worktrees_project_root`.

## Added

- `Adapter.session_flag` / `ClaudeCode.session_flag`: what `{session_flag}` expands to per harness; `None` means unsupported.
- `Adapter._session_flag_check`: refuses `{session_flag}` on a harness without one, in `_custom` and in the generic launch (which bypasses `_custom`).
- `_SESSION` frozenset: the placeholders that make a custom command serve resume.
- `placeholder_problem` branch: refuses `<{session_flag}`, since it is arguments and not a file.
- `substitute_prompt(session_flag=…)`: values now return shell text, so `{session_flag}` can expand to several words.
- `orchestration_pinned.roster_source`: the ref plus the drift sentence; shared by the plan and `validate`.
- `OrchestrationPlan.roster_ref` / `roster_drift`, `assign_leaf(drift=…)`, `_pick_executor(drift=…)` branch: the drift replaces the misleading hint.
- `orchestrate_cli.render` roster line and `! <drift>` line: A2's "prints the ref" in text mode.
- `validate_orchestration_contract` drift warning: "validate warns the same way".
- `worker_reconcile._gaps` and the `gaps` key in `sync`; the gap line in `worker_cli.cmd_sync`: A3.
- `_bookkeeping(prefix=…)`: git names `sr/work/...`, and without this the moved brief would be refused by delegate and flagged by reconcile.
- `role_prompt._dirty_check(prefix)` (replaces `_DIRTY_CHECK`), `_where`, and the `prefix` parameters: A5. In the nested layout the old `:(top)work/...` excludes did not match the project's bookkeeping.
- `generate_brief._project_root_line` and the `_section_metadata(prefix=…)` parameter: A5.
- `worker_ops._brief_into` destination change and the dirty-check prefix: the brief sits where the nested prompt says.
- Mocks: none.
- Tests, all in `tests/test_worker_cli_fixes.py` (new), one per behaviour:
  - A1: `test_one_claude_command_launches_and_resumes_with_session_flag`, `test_session_flag_is_refused_where_it_has_no_meaning` (×3 harnesses), `test_session_flag_must_be_whole_arguments` (×2 shapes).
  - A2: `test_text_plan_always_names_the_roster_ref` (with helper `_plan_text`), `test_a_roster_that_differs_from_the_integration_branch_is_named_not_the_may_process_hint`, `test_a_roster_absent_on_the_integration_branch_is_named`.
  - A3: `test_sync_reports_a_gap_in_event_sequence_numbers`.
  - A4: `test_path_takes_several_values_or_repeats` (×3 commands).
  - A5: `test_nested_prompt_and_brief_give_paths_from_the_git_root`, `test_nested_delegate_puts_the_brief_under_the_worktrees_project_root`.
  - Helper `_nested`: a two-branch nested review repo.
  - Public test helpers (review round 1, renamed from private, not added): `worker_roster`, `run_worker_cli`, `wait_for_worker`, `plan_repo`, `only_assignment`. They are what the new tests import, so `tests/test_worker_cli_fixes.py` imports no private name from another module or from `specy_road`.
