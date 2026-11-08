# Implementation summary: M22.41 — ready refuses a leaf with no commits

Branch `feature/rm-ready-refuses-a-leaf-with-no-commits`, base `626649316540951569d0cbb4ce44b10cd3e2a22b`.

## What changed

- **A1.** `specy-road ready` refuses before any `--run` and again after, when no committed path in the claim's touch zones (the node's, when the claim has none) differs from the integration merge base, in this repository or in a configured nested repository those zones cover, or when an in-zone path is staged, unstaged, deleted, or untracked and not ignored. The refusal names the uncommitted paths. A `--run` that moves `HEAD` is refused too. Nothing is written, and an existing READY file is left unchanged. Matching is `finish_implementation_check.in_zones` (project-root and git-root spellings). Nested committed paths are listed by the same rule that refuses a checkout it cannot read; `nested_zone_paths` is not used, because a missing base or an unreadable diff becomes no paths there.
- **A2.** For a leaf whose zones cover no configured nested repository, `handoff status` appends an error to an existing READY that has no `blocked_on` and whose `commit` resolves to its `base`. The text shows INVALID, `--json` has a non-empty `errors` list, and with no independent review records the state is `waiting` (the rendered status does not suggest a reviewer prompt). A READY with `blocked_on` still reports `executor_blocked`. A leaf that covers a nested repository keeps today's reading of such a file.
- **A3.** `tests/test_ready_empty_leaf.py` drives the in-process CLI against temporary repositories from `tests.review_repo_helpers`. `CHANGELOG.md` `[Unreleased]` / `### Fixed` records the refusal. `docs/orchestration-review.md` states both the `ready` refusal and the status reading.

## Touch zones

Declared: `specy_road/review_gate_ready.py`, `specy_road/review_files.py`, `tests/test_ready_empty_leaf.py`, `docs/orchestration-review.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/review_cli.py`.

`specy_road/review_files.py` stays unchanged. The empty-READY error is applied in `handoff status` (`review_cli._node_status`), not in `load_ready`, so a `blocked_on` file and a nested-only leaf stay valid to the loader and the gate. No path outside the declared zones needed a change, and no new module was required. The roadmap zone list was not edited.

## Fix round (gpt-6.1-sol, `7012b169`)

Class: a covered nested repository that is checked out here, but whose git evidence is missing (no integration base, no merge base, or a committed diff or status listing git cannot produce). `nested_zone_paths` turns that into no paths, so committed outer work wrote READY.

One rule, in `_nested_in_zone`, used by `committed_in_zone` and therefore by both the preflight and the postflight (`_checked_runs` calls `leaf_work_problem` twice). A checkout is assessed only when its integration base resolves and, when the leaf branch exists there, the merge base and the committed diff can be listed. Any of those missing refuses and names the repository and the missing evidence. No leaf branch means no commits. The same sentence is the `ready` command description. `specy_road/nested_repos.py` is outside the touch zones, so the caller stopped using `nested_zone_paths` rather than changing that helper.

Broader than the review, and stopped there: a covered repository that is not a checkout is still not read. Inventing a checkout is a different problem; the review's case is a checkout whose base does not resolve.

`cmd_ready` was not given another branch. A branch count of `cmd_ready` matches the merge base (`origin/WIP/improvements-0-3-1`). No `noqa: C901`.

## Probes

- `nested_zone_paths` on an unresolved `integration_branch`: returns no paths (`branch_diff_range` is `None`, then `diff_paths(...) or []`). Result: the ready path no longer calls it.
- `committed_in_zone` and `leaf_work_problem` on that same input: result: the refusal is returned before any write; the CLI test with `integration_branch: typo-dev` and a committed outer `src/a.py` exits 1, names `src/engine`, `typo-dev` and `integration base`, and writes no READY.
- Postflight: the only second pass is the same `leaf_work_problem` inside `_checked_runs`. Result: the typo is refused before `--run`, and a later pass cannot treat the missing base as an empty diff.
- READY schema / `load_ready`: does not re-read nested git. Result: left unchanged; the refusal is not writing the file, which also leaves an existing READY byte-for-byte.
- `empty_ready_error` / `handoff status`: result: unchanged, so an old nested-only READY is still not marked INVALID from missing live git evidence (A2).
- `uncommitted_in_zone` when a nested `git status` fails: still returns `None` with no repository name. Result: `leaf_work_problem` asks `_nested_in_zone` first, and that names the repository and "git cannot list uncommitted paths" before the generic dirt message.
- No leaf branch, integration base `dev` resolves, outer `src/a.py` committed: result: exit 0 and READY is written (the parametrized partner of the typo row).
- Covered `src/engine` configured but not checked out, outer `src/a.py` committed: result: exit 0 and READY is written. Documented limit; not widened.
- Existing nested-only row (leaf branch with `core.py`, no outer in-zone commit): result: still accepted (56 ready tests passed, including the 14 from the first round).

## Verification

- `python -m pytest tests/test_ready_empty_leaf.py tests/test_ready_command.py tests/test_review_evidence.py tests/test_review_cli.py -q --tb=short -p no:cacheprovider`: 94 passed on the first commit; after this fix, `tests/test_ready_empty_leaf.py` and `tests/test_ready_command.py`: 56 passed.
- `ruff check specy_road tests scripts`: clean.
- `python -m specy_road.cli file-limits`: OK (existing hard-alert warnings only).

## Added

### Helpers

- `_cleaned_zones` — drop blank and non-string zones before `in_zones`, the same trim the implementation gate uses.
- `_status_paths` — list `git status --porcelain -z` paths, including a rename's old path, so a spaced path stays one field and ignored files are absent.
- `uncommitted_in_zone` — in-zone staged, unstaged, deleted and untracked paths in the outer repository and in covered nested repositories.
- `committed_in_zone` — in-zone paths committed since the integration merge base, or a refusal naming a covered nested repository that cannot be assessed. Returns `(None, None)` when the outer diff cannot be listed.
- `_nested_gap` — the refusal sentence: repository path plus the missing git evidence.
- `_nested_in_zone` — the one nested rule: list in-zone commits in covered checkouts, or refuse when the integration base, the merge base, the committed diff or the status listing cannot be read. No leaf branch is no commits. A repository that is not checked out is skipped.
- `leaf_work_problem` — the refusal text for a dirty or empty leaf.
- `empty_ready_error` — the status error for an unblocked READY whose commit is its base when no nested repository is covered.
- `_checked_runs` — run `--run` only after the leaf check, then repeat the check and refuse a moved `HEAD`, so `cmd_ready` stays within the complexity cap.

### Branches or guards

- A covered nested repository that is not a checkout here is skipped. A checkout whose integration base does not resolve, or whose merge base, committed diff or status listing cannot be read, is refused by name. No leaf branch is an empty nested diff.
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
- `test_ready_names_a_covered_nested_repo_it_cannot_assess` — `integration_branch: typo-dev` with committed outer in-zone work exits 1, names the repository and the missing base, and writes no READY; a resolved base with no leaf branch still writes READY.
