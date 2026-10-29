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
- `tests/test_lean_gates.py`, the private-import gate: passes. The tests that patch
  `do_next_task` privates sit in `tests/test_do_next_task_pickup.py`, which already
  had those references in its baseline. The baseline file is unchanged.

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
- `tests/test_do_next_task_pickup._baseline_harness`: the existing pickup monkeypatch pattern, recording the order of sync, the on-base check and git calls, so the tests can show where the gate runs.
- The grind step test reuses `tests.test_grind_session._Harness` with `pickup_rc=1` to stand in for a refused baseline.

### Tests
- `tests/test_baseline_gate.py`:
  - `test_schema_accepts_baseline_cmd`: A2 schema.
  - `test_yaml_sets_the_default`, `test_cli_wins_over_yaml`, `test_empty_cli_turns_the_yaml_default_off`, `test_no_config_means_no_baseline`: A2 precedence.
  - `test_passing_baseline_returns`, `test_failing_baseline_refuses`, `test_baseline_warn_downgrades_a_failure`: A1 refuse and warn, in a real git repo.
  - `test_baseline_that_writes_is_refused_even_when_warned`, `test_baseline_may_write_under_work`: the tree part of the git-state guard; the message names `working tree`.
  - `test_baseline_that_commits_is_refused`: a passing baseline that commits leaves the tree clean and is still refused, naming the HEAD move (review round 1).
  - `test_baseline_that_switches_ref_is_refused` (`checkout -b`, `checkout --detach`): a branch switch is refused even with `--baseline-warn`, naming the old and new ref (review round 1).
  - `test_yaml_baseline_runs_without_a_flag`: A2 end to end through the gate.
  - `test_grind_passes_baseline_flags_to_pickup`, `test_grind_forwards_an_empty_baseline_to_turn_the_default_off`, `test_grind_without_baseline_flags_forwards_none`: grind pass-through.
  - `test_grind_step_pickup_passes_baseline_through`: `--step pickup` forwards the flag, and a refused pickup gives exit 5.
- `tests/test_do_next_task_pickup.py`:
  - `test_pickup_runs_baseline_on_base_before_registering`: the gate runs after the sync and on-base check, before `git add`, and receives the CLI values.
  - `test_pickup_refused_by_baseline_claims_nothing`: a refusal leaves no git calls and the registry unchanged.
