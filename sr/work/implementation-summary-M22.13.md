# Implementation summary: M22.13 (worker-cost-and-stale-presence)

## What changed

- **D8 (A1):** `WorkerAdapter.parse_events` (`specy_road/worker_adapter_base.py`) reads the launch model with
  `worker_models.launch_model` instead of `model_from_argv`. A `channels.cli` launch (`sh -c <command>`) goes
  through `command_model`'s existing rules, so a simple command with a literal `-m` / `--model` / `--model=` is
  priced from the roster profile (`cost_is_estimate`, shown `est.`). A list, a pipeline, a non-literal `-m`, an
  unsplittable string, and any `$(…)` (the documented Codex git-roots grant, rc4's actual command) stay `$?`.
  `command_model` and `model_from_argv` are unchanged (coordinator decision: the review gate shares that rule).
- **D9 (A2):** `Session.stale_reason(repo_root)` (`specy_road/session_presence.py`) returns `worktree gone` when
  the recorded worktree string is not a directory, else `branch gone` when `git show-ref --verify --quiet
  refs/heads/<branch>` exits 1. The ref check runs in the record's own worktree (when present), falling back
  to `repo_root`: `session start` records the checkout it was run from, which can be another repository than
  `--repo-root`. A non-string value, or any other git exit (128, timeout), reads as present.
  `list_sessions(live_only=True)` leaves stale sessions out; `session list --all` (`session_cli.cmd_list`) prints
  `(stale: <reason>)` (`(expired)` wins when both apply).
- **D9 (A3):** `_terminate_locked` (`specy_road/worker_ops_lifecycle.py`) derives `<user>-s<pgid>` from the
  record's `pgid` before anything clears it, and ends that agent's session only if it is live and its worktree
  resolves to the worker's worktree. No new record field. Limit: the wrapper clears `pgid` at turn end, so
  terminating an `idle` / `completed` worker ends no session by name; the worktree/branch rule or expiry retires
  it (documented).
- **Docs / changelog (A4):** `docs/orchestration-workers.md` cost cell (shell `channels.cli` rule, git-roots form
  unpriced), `terminate` row, and the presence paragraph under "Working alongside sessions and the gate";
  `CHANGELOG.md` `[Unreleased]` Fixed, two entries.
- `tests/test_session_overlap.py::test_a_removed_worktree_is_unknown_not_clean` (zone added by the coordinator):
  after `shutil.rmtree(wt)` it recreates `wt` as an empty directory, so the session stays live under A2 and the
  test still checks the "unknown (no git checkout)" overlap state.

## Final touch zones

`specy_road/session_presence.py`, `specy_road/worker_ops_lifecycle.py`, `specy_road/worker_adapter_base.py`,
`specy_road/bundled_scripts/session_cli.py`, `tests/test_worker_usage_shell_cli.py`,
`tests/test_session_presence.py`, `tests/test_session_overlap.py`, `docs/orchestration-workers.md`,
`CHANGELOG.md`. No new module; file limits satisfied.

## Verification

- `pytest -n 4` over the session, guard, orphaned-claims, doctor, hook, worker and usage test files:
  635 passed, 8 skipped.
- `ruff check` on the changed Python files; `specy-road file-limits`: OK.

## Added

- `Session.stale_reason` (session_presence.py): the A2 worktree/branch rule, shared by `list_sessions` and `session list --all`.
- Branch in `list_sessions`: live also requires no stale reason (A2).
- Branch in `cmd_list`: `(stale: <reason>)` label (A2).
- Guard in `stale_reason`: non-string worktree/branch and git exit codes other than 1 keep the session live (A2, S-RC18).
- `_end_worker_session` (worker_ops_lifecycle.py) and the `agent` derivation in `_terminate_locked`: end only the worker's own live session in its worktree (A3).
- `tests/test_worker_usage_shell_cli.py::test_a_shell_channels_cli_is_priced_from_its_literal_model` (6 params): simple `-m` and `--model=` priced at the profile's estimate; pipeline, `"$MODEL"`, git-roots `$(…)`, unsplittable stay `$?` (A1, A4).
- `tests/test_session_presence.py::test_a_session_whose_worktree_or_branch_is_gone_stops_counting` (3 params): worktree removed, branch deleted, both; a live peer still conflicts; `--all` reasons (A2, A4).
- `tests/test_session_presence.py::test_a_session_with_a_non_string_worktree_stays_live`: malformed value keeps the session live (A2).
- `tests/test_session_presence.py::test_terminate_ends_only_the_workers_own_session`: a real process in its own POSIX session runs `session start` without `SPECY_ROAD_AGENT_ID`; terminate ends it, a same-worktree peer stays byte-identical, another worktree's session stays (A3).
- Mocks: none.
