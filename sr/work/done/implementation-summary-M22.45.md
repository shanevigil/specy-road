# Implementation summary: M22.45 — integration refs stay put during a turn

## Touch zones (confirmed)

Call sites of `specy_road/worker_turn_check.py` at the base commit: `worker_ops_message.py` (`limit_gate`), `worker_runner.py` (`TurnWatch`, `close_turn`), `tests/test_headless_limits_denials.py`, `tests/test_worker_sandbox.py` (`PAUSED_BY_LIMIT`). None of them read `GitState` or the post-run finding list in a way this leaf changes. No zone added or removed.

Final touch zones: `specy_road/worker_turn_check.py`, `tests/test_worker_turn_check.py`, `CHANGELOG.md`.

## Change

`TurnWatch` records the integration branch's local ref and its remote-tracking ref when the turn starts. The names come from `resolve_integration_defaults` (the existing `roadmap/git-workflow.yaml` / env resolution): `refs/heads/<branch>` and `refs/remotes/<remote>/<branch>`. At the end, `git_findings` re-reads those same two names, not whatever the config says after the turn. A different sha, including absent to present or present to absent, is one `integration_ref` finding with `ref`, `before`, `after`, and a summary that names the ref and both values. A ref missing at both ends adds nothing. A read that is not a quiet "no such ref" (broken ref, not a repository, timeout) is a `check_error` finding, and the turn is not clean. A commit that moves only the worker's own branch does not move either watched ref.

## Added inventory

### Helpers

- `RefTip` — one ref's name, sha, and read error, so "absent" is not stored as a failure.
- `_integration_refs` — the local and remote-tracking ref names from `resolve_integration_defaults`.
- `_ref_tip` — one `git rev-parse --verify --quiet`; quiet exit 1 with no output is absence, any other failure is an error.
- `_integration_findings` — the post-run findings for the two watched refs.

### Branches or guards

- `git_state`'s `refs` argument — unset at turn start, so the names are resolved then; the end passes those names back, so editing the integration branch name during the turn cannot hide a move of the refs the turn began with.
- `_ref_tip` success, quiet absence, and any other status — a broken ref or a git failure is an error, not absence.
- `_ref_tip` message fallback (`exit <code>` when git reports no text) — a failed read with an empty message still has a non-empty error, so it cannot compare as absent.
- `_integration_findings` error versus sha change versus equal tips — equal tips include a ref that is absent at both ends, which stays clean.

### Mocks

- none

### Tests

- `test_an_integration_ref_move_is_a_finding_and_the_workers_own_branch_is_not` — through `wr.run`, local move, remote-tracking move, absent to present, present to absent, and an empty commit on the worker's own branch.
- `test_a_failed_read_of_an_integration_ref_is_a_check_error` — a broken `refs/heads/dev` written during the turn is a `check_error`, not a clean result.
