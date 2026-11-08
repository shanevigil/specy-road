# Implementation summary: M22.41 — ready refuses a leaf with no commits

Branch `feature/rm-ready-refuses-a-leaf-with-no-commits`, base `626649316540951569d0cbb4ce44b10cd3e2a22b`.

## What changed

- **A1.** `specy-road ready` refuses before any `--run` and again after, when no committed path in the claim's touch zones (the node's, when the claim has none) differs from the integration merge base, in this repository or in a configured nested repository those zones cover, or when an in-zone path is staged, unstaged, deleted, or untracked and not ignored. The refusal names the uncommitted paths. A `--run` that moves `HEAD` is refused too. Nothing is written, and an existing READY file is left unchanged. Matching is `finish_implementation_check.in_zones` (project-root and git-root spellings). Nested committed paths come from `nested_repos.nested_zone_paths`.
- **A2.** For a leaf whose zones cover no configured nested repository, `handoff status` appends an error to an existing READY that has no `blocked_on` and whose `commit` resolves to its `base`. The text shows INVALID, `--json` has a non-empty `errors` list, and with no independent review records the state is `waiting` (the rendered status does not suggest a reviewer prompt). A READY with `blocked_on` still reports `executor_blocked`. A leaf that covers a nested repository keeps today's reading of such a file.
- **A3.** `tests/test_ready_empty_leaf.py` drives the in-process CLI against temporary repositories from `tests.review_repo_helpers`. `CHANGELOG.md` `[Unreleased]` / `### Fixed` records the refusal. `docs/orchestration-review.md` states both the `ready` refusal and the status reading.

## Touch zones

Declared: `specy_road/review_gate_ready.py`, `specy_road/review_files.py`, `tests/test_ready_empty_leaf.py`, `docs/orchestration-review.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/review_cli.py`.

`specy_road/review_files.py` stays unchanged. The empty-READY error is applied in `handoff status` (`review_cli._node_status`), not in `load_ready`, so a `blocked_on` file and a nested-only leaf stay valid to the loader and the gate. No path outside the declared zones needed a change, and no new module was required. The roadmap zone list was not edited.

## Verification

- `python -m pytest tests/test_ready_empty_leaf.py tests/test_ready_command.py tests/test_review_evidence.py tests/test_review_cli.py -q --tb=short -p no:cacheprovider`: 94 passed, then the ready tests again after the complexity split (54 passed).
- `ruff check` on the three Python files: clean (`cmd_ready` stays at the complexity cap by moving the run bracket into `_checked_runs`).
- `python -m specy_road.cli file-limits`: OK (existing hard-alert warnings only).

## Added

### Helpers

- `_cleaned_zones` — drop blank and non-string zones before `in_zones`, the same trim the implementation gate uses.
- `_status_paths` — list `git status --porcelain -z` paths, including a rename's old path, so a spaced path stays one field and ignored files are absent.
- `uncommitted_in_zone` — in-zone staged, unstaged, deleted and untracked paths in the outer repository and in covered nested repositories.
- `committed_in_zone` — in-zone paths committed since the integration merge base, outer diff plus `nested_zone_paths`.
- `leaf_work_problem` — the refusal text for a dirty or empty leaf.
- `empty_ready_error` — the status error for an unblocked READY whose commit is its base when no nested repository is covered.
- `_checked_runs` — run `--run` only after the leaf check, then repeat the check and refuse a moved `HEAD`, so `cmd_ready` stays within the complexity cap.

### Branches or guards

- A covered nested repository that is not a checkout here is skipped, as `nested_zone_paths` skips it.
- `git status` or the outer diff returning no answer refuses, rather than reading that as a clean tree; the diff wording matches the refusal `cmd_ready` already used.
- Paths git reports for the outer repository inside a nested repository's directory are left to that repository.
- `blocked_on` keeps the READY valid for status.
- A zone that covers any configured nested repository keeps an old `commit == base` READY on today's status.
- `HEAD` after `--run` differing from `HEAD` before it refuses and does not replace READY.

### Mocks

- none

### Tests

- `test_ready_refuses_only_in_zone_dirt_and_an_empty_leaf` — one table for staged, unstaged, deleted and untracked in-zone paths (refused and named), an outside path and a `src2` sibling of zone `src` (accepted), no committed in-zone diff (refused, the outside path not named), and nested-only committed work (accepted).
- `test_a_preflight_refusal_runs_no_command` — an empty leaf's `--run` that would write a marker does not run.
- `test_a_run_that_dirties_a_zone_or_moves_head_keeps_the_existing_ready` — a `--run` that writes an in-zone file, and one that creates an empty commit, each refuse and leave the existing READY bytes unchanged.
- `test_status_rows_for_an_empty_a_blocked_and_a_nonempty_ready` — text and `--json` for an old empty READY (`waiting`, INVALID, no reviewer prompt), a `blocked_on` READY at that same commit (`executor_blocked`), and a non-empty READY (`in-review`, ok).
