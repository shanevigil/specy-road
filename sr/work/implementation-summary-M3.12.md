# Implementation summary: M3.12 — a baseline gate runs on the integration branch before pickup

## What changed

- **A1 — `--baseline-cmd` / `--baseline-warn`.**
  `do-next-available-task` (the script behind the `/specyrd-do-next-task` slash
  command) gets both flags. After the integration-branch sync (or the clean-tree check
  under `--local`) and the "HEAD is the integration branch" check, and before any leaf
  is picked or registered, `run_baseline_gate` runs the command in the repo root:
  - It exits non-zero → pickup exits 1 with `baseline failed on '<base>' (exit N); no leaf was claimed`. No brief is written, no registry row is added, no branch is created.
  - `--baseline-warn` turns that refusal into a warning, and pickup continues.
  - The command changes git state → pickup refuses even with `--baseline-warn`, and
    the message names what moved. The gate records HEAD (`rev-parse HEAD`), the
    symbolic ref (`symbolic-ref -q HEAD`, else `(detached)`) and whether the tree is
    clean outside `work/`, before and after the command. Any difference means the
    command moved HEAD, switched branch or wrote files, and pickup would otherwise
    register and push from that state. (Review round 1, Sol at `fff671f`: a
    passing baseline could commit or check out another ref while leaving the tree
    clean.)

  `grind-session` accepts both flags and forwards them to every pickup it runs,
  including `--step pickup`. A refused baseline is a refused pickup: exit 5 and
  `hook_failed phase=pickup`. A resumed in-flight claim does no pickup, so it runs no
  baseline.
- **A2 — `baseline_cmd` in `roadmap/git-workflow.yaml`.** The key is a string in the
  bundled schema and the `sr/` copy. `resolve_baseline_cmd` picks the command in this
  order: CLI first, then the yaml, then none. An empty `--baseline-cmd ''` turns a
  configured baseline off for one run.

  Note: `git-workflow.yaml` has no `pre_finish_cmd` key, and the acceptance text
  mentions one. I read "mirroring pre_finish_cmd" as "a command hook shaped like
  `--pre-finish-cmd`" and added only `baseline_cmd`.
- **A3 — docs.**
  - `docs/grind-session.md`: the "Pre-finish hook" section is now "Baseline and
    pre-finish hooks", with the reason: a red base is caught before a leaf inherits
    it. Also updated: the loop diagram, the exit-5 row and the quickstart pointer.
  - `docs/dev-workflow.md`: a new "Baseline gate" paragraph in the automated pickup
    path, presented as the start-of-leaf counterpart of `--pre-finish-cmd`. The
    grind-session paragraph now names it too.
  - `grind-session.md` was already at its 500-line cap. To stay inside it without
    raising the limit, I moved the `--plan --json` example's empty-list fields onto
    one line.

## Touch zones (final)

Used: `specy_road/bundled_scripts/do_next_task.py`, `do_next_task_args.py`,
`do_next_available.py`, `grind_session.py` (docstring only),
`grind_session_args.py`, `specy_road/git_workflow_config.py`,
`specy_road/templates/project/schemas/git-workflow.schema.json`,
`schemas/git-workflow.schema.json`, `docs/dev-workflow.md`,
`docs/grind-session.md`, `tests/`.

- I read the zone `schemas/git-workflow.schema.json` against the project root `sr/`,
  because no `schemas/` exists at the checkout root. I edited
  `sr/schemas/git-workflow.schema.json`, and it stays byte-identical to the bundled
  template.
- `grind_session_step.py` needed no change: `--step pickup` builds its argv through
  the same `pickup_args`.
- `do_next_task.py` was at 397 of 400 lines, so the gate lives in
  `do_next_available.py` and costs `do_next_task.py` 2 lines.

Not touched, though it may want follow-up outside this leaf's zones:
- `specy_road/cli_usage.py`: the grind-session one-line flag list.
- `specy_road/templates/specyrd/commands/specyrd-grind-session.md` and
  `specyrd-do-next-task.md`.

## Verification

- Round 2: focused tests (`test_baseline_gate`, `test_baseline_gate_cli`,
  `test_do_next_task_pickup`, `test_grind_session`, `test_grind_session_step`,
  `test_lean_gates`, `test_do_next_queue`, `test_unauthored_leaf_guard`): 118 passed,
  2 skipped.
  - `python scripts/check_test_private_imports.py`: exit 0, 0 new references. Its one
    stale baseline entry, `test_review_round6_evidence.py`, predates this leaf.
  - `file-limits` and `ruff` pass.
  - To check the new CLI tests can fail, I temporarily made `run_baseline_gate`
    return before it ran anything: 7 of the 8 CLI tests failed. The one that passed
    is the passing-baseline grind step test, which is expected.
- Round 1: focused tests (`test_baseline_gate`, `test_do_next_task_pickup`,
  `test_grind_session`, `test_grind_session_step`, `test_lean_gates`,
  `test_do_next_queue`): 102 passed, 2 skipped. `file-limits` passes
  (`do_next_available.py` is at 399 of 400 lines), and so does `ruff`.
- `python -m pytest -q` (round 0), after merging `origin/WIP/improvements-0-3-1` (`09b722c`):
  2337 passed, 2 skipped. Before the merge, one test failed:
  `tests/test_roadmap_crud.py::test_list_nodes_json_is_the_full_untruncated_list`
  (`NameError: _fixture_repo`). That was a WIP-side bug, fixed upstream; this branch
  never touched the file.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests scripts`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `tests/test_lean_gates.py`, the private-import gate: passes. The baseline file is unchanged.

## Added

### Helpers
- `git_workflow_config.resolve_baseline_cmd`: returns the CLI value if set, then the yaml `baseline_cmd`, else none. An empty CLI value disables the yaml one. It is how A2 reaches the CLI.
- `do_next_available.run_baseline_gate`: runs the command on the integration branch. It refuses on failure unless `warn_only`, and refuses if `_git_state` differs before and after the command. This is A1's gate.
- `do_next_available._git_state`: HEAD SHA, symbolic ref (or `(detached)`) and clean-outside-`work/` status, the state a read-only baseline must leave unchanged (review round 1).
- `do_next_task_args._add_baseline_args`: the `--baseline-cmd` and `--baseline-warn` flags for pickup (A1).

### Branches or guards
- `do_next_task.main` calls `run_baseline_gate` after `_assert_current_branch_equals(base)` and before `_pick_node`, so the gate always runs on the synced base and before anything is claimed.
- `run_baseline_gate` compares git state before and after the command and refuses, naming each field that moved. A baseline that commits, switches ref or writes files cannot change what pickup registers and pushes. This replaces the round-0 clean-tree-only check.
- `grind_session_args.pickup_args` forwards `--baseline-cmd` (an empty value too, so it can switch the yaml default off) and `--baseline-warn`, so grind-session supports A1.
- Schema key `baseline_cmd`, in the bundled template and in `sr/schemas` (A2).

### Mocks
- none. Review round 2 removed the monkeypatch harness from `tests/test_do_next_task_pickup.py`; that file is back to its base content. It also removed the reuse of `tests.test_grind_session._Harness`. Every gate behaviour is now tested through the real CLIs.

### Tests
- `tests/test_baseline_gate_cli.py`, end to end. Each test builds a disposable one-leaf project with a bare `origin`, runs `python -m specy_road.cli`, and checks only what a user can see: exit code, stdout and stderr text, the registry row on `main` and `origin/main`, whether `feature/rm-leaf-one` exists or is checked out, and HEAD.
  - `test_passing_baseline_lets_the_pickup_through`: the claim is pushed and the feature branch is checked out (A1).
  - `test_failing_baseline_refuses_and_claims_nothing`: exit 1 and the refusal text; HEAD, `main` and `origin/main` are unchanged; no row, no branch (A1).
  - `test_baseline_warn_picks_up_from_a_red_base`: the warning text, and the claim lands (A1, `--baseline-warn`).
  - `test_baseline_that_commits_is_refused`: the tree is clean, but HEAD moved. The refusal names `HEAD <old> -> <new>`, nothing is pushed, no row, no branch (review round 1).
  - `test_baseline_that_moves_git_state_is_refused_even_when_warned`, parametrised over `checkout -b`, `checkout --detach` and a tracked-file write: the message names the moved field; HEAD is unchanged; nothing is claimed (review round 1).
  - `test_baseline_may_write_under_work`: output under `work/` does not count as a change.
  - `test_git_workflow_baseline_applies_and_an_empty_flag_turns_it_off`: the yaml `baseline_cmd` refuses with no flag, and `--baseline-cmd ''` claims (A2).
  - `test_grind_step_pickup_refused_by_the_baseline_exits_5`: exit 5, a `hook_failed` event for `pickup`/`M1`, and nothing claimed.
  - `test_grind_step_pickup_with_a_passing_baseline_claims`: a `picked` event and the branch is created.
- `tests/test_baseline_gate.py`, configuration only, all through public functions:
  - `test_schema_accepts_baseline_cmd`: the A2 schema.
  - `test_yaml_sets_the_default`, `test_cli_wins_over_yaml`, `test_empty_cli_turns_the_yaml_default_off`, `test_no_config_means_no_baseline`: A2 precedence.
  - `test_grind_passes_baseline_flags_to_pickup`, `test_grind_forwards_an_empty_baseline_to_turn_the_default_off`, `test_grind_without_baseline_flags_forwards_none`: the argv grind-session forwards to pickup.
