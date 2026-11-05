# Implementation summary: M14.1 — Approvals never carry across unreviewed changes in a sibling repository

Implementation commits: `2c9aa33f`, plus a test-helper follow-up.

## What changed

- **A1** — New `specy_road/sibling_repos.py`: `sibling_repos(project_root) -> list[Sibling(path, head, dirty)]`. Walks the project root to depth 2, skipping `.git`, `work`, `node_modules`, symlinks and `nested_repos` paths (`nested_prefixes()` / `in_nested()`); a candidate has a `.git` (file or directory), `is_repo_top()` is true, and the root repository either does not track it (`git ls-files` empty) or ignores it (`git check-ignore`). It does not descend into a repository it found. HEAD comes from `git rev-parse HEAD` and dirty from `git status --porcelain`. It returns none outside a git checkout.
- **A2** — `count_at_later_commit()` in `review_bookkeeping.py`: when the range is bookkeeping-only but sibling repositories exist, the review is stale. The reason ("<model>'s <verdict> at <sha12> is stale: sibling repositories <list> are present and nested_repos does not configure them, so changes there cannot be seen") is appended to `result.carry_refused`, and `policy_line()` prints it in place of `CARRY_NOTE`. `review_gate.py` is not edited.
- **A3** — `handoff ready` (`review_gate_ready.py`) and `review record` (`review_cli.py`) add `sibling_heads: {path: sha}` through `sibling_heads_field()`, and only when siblings with a commit exist, so READY files in projects without siblings are byte-for-byte unchanged. In `review record` it goes in before signing, so a signature covers it. Both schemas gained an optional `sibling_heads`. At the same root commit, a record whose `sibling_heads` differ from the current HEADs, or whose siblings are now dirty, is stale (`heads_problem()`). A record without the field is not checked there, and because the carry never applies while siblings exist, it counts only at the same root commit.
- **A4** — `validate_roadmap.py` folds its eleven `warn_*(root)` calls into one loop and adds `warn_unconfigured_sibling_repos` (one stderr line naming the repositories and docs/git-workflow.md's "Nested repositories (`nested_repos`)" section). The file went from 359 to 354 lines. The loop lists the names inside the function, so it looks them up at call time and monkeypatching a module attribute still works.
- **A5** — `policy_line(gate)` (`review_bookkeeping.py`) renders `gate.summary()` with `(<model>@<commit12>[ carried from an older commit], ...)` after the count, followed by any carry refusals. `gate_policy_summary()` (`reviewer_run_failure.py`, used for `handoff status`'s `policy`) uses it, and `review record`'s closing `policy:` print now calls `gate_policy_summary(after, [])`.

## Notes for reviewers

- The per-process cache from the planning sheet became a per-evaluation cache: `sibling_repos()` runs once per `evaluate_gate` and is kept on `result.sibling_repos`. A process-wide cache would serve stale HEAD and dirty state to any long-lived caller, and in tests that move a sibling HEAD between gate evaluations.
- `GateResult` lives in `review_gate.py`, which is not in the touch zones (398 lines), so `carry_refused` and `sibling_repos` are set as plain attributes on the result and read with `getattr(..., None)`.
- `review_cli.py` stays at 400 lines: the two-line `review_target` import is now one line, which makes room for the `sibling_repos` import.
- A record's `problems()` line for a stale record still reads "reviewed <sha>, not the current commit"; the `policy:` line gives the real reason. Changing `problems()` would mean editing `review_gate.py`.
- Final touch zones: as listed. `docs/git-workflow.md` is cited, not edited.

## Verification

- `pytest tests/test_sibling_repo_approvals.py tests/test_sheet_edits_keep_approvals.py`: 17 passed (fix round 1).
- `pytest -n 4`: 4453 passed.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`, `specy-road file-limits`, and `ruff check` on the changed files: all OK.

## Fix round 1 (grok-4.7-low block on ce27ff63)

- Merged `origin/WIP/improvements-0-3-1` first. It merged cleanly and touched none of this leaf's files.
- Deleted `test_without_siblings_the_summary_only_carry_is_unchanged`. Without siblings, the carry is still covered by `tests/test_sheet_edits_keep_approvals.py::test_summary_only_delta_keeps_approval` (same input, same `passed and bookkeeping_carry` assertions), and that test still passes on this branch.
- `test_validate_warns_once_naming_the_siblings` no longer monkeypatches `warn_unconfigured_sibling_repos` or asserts on a call list. It runs validate and asserts only on the warning it prints.

## Probes

- Class "test duplicates existing coverage": checked each remaining test in `tests/test_sibling_repo_approvals.py` against the existing tests. `sibling_heads` appears in no other test. No existing test asserts the `policy: 1/1 approvals (<model>@...)` text or that READY omits a field. Only the deleted test was a duplicate.
- Class "test patches internals": grepped `tests/test_sibling_repo_approvals.py` for `monkeypatch`, `mock` and `patch`. The validate test had the only one, now removed. Every other test drives real git repositories through the CLI (`run_review_cli`, `handoff_status_node`) or public functions (`evaluate_gate`, `sibling_repos`, `policy_line`, `validate_at`).
- The zero-sibling validate row stays: no other test checks that validate prints no sibling warning when there are none.

## Added

### Helpers
- `specy_road/sibling_repos.py` `Sibling`: path, HEAD and dirty state for one sibling repository (A1).
- `sibling_repos()`: lists sibling repositories under the project root (A1).
- `_untracked_by_root()`: the "ignored or not tracked by the root repository" test (A1).
- `sibling_heads()`: `{path: HEAD}` for the records (A3).
- `sibling_heads_field()`: the optional `sibling_heads` field for READY and review records, empty when there are no siblings (A3), so behaviour without siblings is unchanged.
- `warn_unconfigured_sibling_repos()`: the validate warning (A4).
- `review_bookkeeping._siblings()`: finds siblings once per gate evaluation (cheap gate).
- `review_bookkeeping.heads_problem()`: says why recorded sibling HEADs no longer hold (A3).
- `review_bookkeeping._refuse()`: marks a review stale and records the reason for the policy line (A2/A3).
- `review_bookkeeping.policy_line()`: the `policy:` line with model@commit and the carried markers (A5).

### Branches and guards
- `count_at_later_commit`: at the same commit, a stale verdict when recorded sibling heads moved or a sibling is dirty (A3).
- `count_at_later_commit`: a bookkeeping-only range with siblings present is refused instead of carried (A2).
- `sibling_repos` skips `.git`, `work`, `node_modules`, symlinks and configured nested repos, does not descend into a found repository, and returns none outside a git checkout (A1).

### Schema
- An optional `sibling_heads` object in `handoff.schema.json` (`$defs.siblingHeads`) and `review-record.schema.json` (A3).

### Test helpers
- `tests/test_sibling_repo_approvals.py` `notes_file()`: writes reviewer notes at HEAD for `review record --file`. The test file imports no underscore-prefixed names; it reuses the public `run_review_cli` and `handoff_status_node` from `tests/review_delegate_helpers.py`.

### Mocks
- none

### Tests (`tests/test_sibling_repo_approvals.py`)
- `test_lists_siblings_with_head_and_dirty_and_skips_tracked_configured_and_deep`: covers A1's definition, including the exclusions.
- `test_reported_case_sibling_code_and_root_summary_only_does_not_carry`: the reported case, plus the status reason and exit 1 (A2).
- `test_recorded_sibling_heads_must_still_hold_at_the_same_root_commit`: `review record` writes `sibling_heads`; a dirty or moved sibling makes the approval stale (A3).
- `test_a_record_without_sibling_heads_counts_only_at_the_same_root_commit`: covers A3's legacy-record rule.
- `test_ready_writes_sibling_heads`: READY carries `sibling_heads` (A3).
- `test_ready_without_siblings_writes_no_sibling_heads`: READY is unchanged without siblings (A3).
- `test_policy_line_lists_each_approval_and_marks_a_carried_one`: pins a same-commit and a carried approval in the policy line and in status text and JSON (A5).
- `test_review_record_prints_the_same_policy_line`: `review record`'s closing `policy:` line (A5).
- `test_validate_warns_once_naming_the_siblings[0|2]`: runs `validate_at` on a repo with two unconfigured siblings (or none) and asserts on stderr only: exactly one warning naming both and docs/git-workflow.md, or none (A4).
