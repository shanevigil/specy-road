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

- `pytest tests/test_sibling_repo_approvals.py tests/test_sheet_edits_keep_approvals.py`: 28 passed (fix round 3); with the gate, review CLI, ready, delta, resumed-delta and milestone-review tests, 122 passed.
- `pytest -n 4`: 4453 passed.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`, `specy-road file-limits`, and `ruff check` on the changed files: all OK.

## Fix round 1 (grok-4.7-low block on ce27ff63)

- Merged `origin/WIP/improvements-0-3-1` first. It merged cleanly and touched none of this leaf's files.
- Deleted `test_without_siblings_the_summary_only_carry_is_unchanged`. Without siblings, the carry is still covered by `tests/test_sheet_edits_keep_approvals.py::test_summary_only_delta_keeps_approval` (same input, same `passed and bookkeeping_carry` assertions), and that test still passes on this branch.
- `test_validate_warns_once_naming_the_siblings` no longer monkeypatches `warn_unconfigured_sibling_repos` or asserts on a call list. It runs validate and asserts only on the warning it prints.

## Fix round 2 (gpt-6.1-sol-low block on ddf61043, F1)

- Merged `origin/WIP/improvements-0-3-1` first. It merged cleanly and touched no zoned file.
- Class: **a recorded sibling map was compared on only one path.** `count_at_later_commit` checked `sibling_heads` only at the same root commit. A record whose sibling was removed (so no sibling remained) then reached the bookkeeping carry on a summary-only root commit and still counted.
- Fix (design, no new branch): `heads_problem(recorded, current)` now runs first, before the same-commit, carry and stale paths. An approval counts or carries only while the current sibling map (which siblings, each HEAD, all clean) equals the recorded one exactly. Records without `sibling_heads` are not checked (the legacy rule): they count at the same root commit, and they carry only when no sibling exists (A2 unchanged).
- Red-green: with the pre-fix `review_bookkeeping.py`, `[removed-summary-only]` passed the gate (the hole). `[added|moved|renamed-summary-only]` were already stale under A2 and failed only on the reason text.

## Fix round 3 (gpt-6.1-sol-low block on 20168981, F1 and F2)

- Merged `origin/WIP/improvements-0-3-1` first. It merged cleanly and touched no zoned file.
- F1 class: **a filesystem path passed to git as a pathspec** (glob characters match other paths). Fix: one helper, `sibling_repos.literal_pathspec()` (`:(literal)<path>`), used for `ls-files`. `check-ignore` takes paths, not pathspecs (it refuses `:(literal)`, checked by hand), so its argument was already literal. It now passes `--no-index`: without it, `check-ignore` never reports a tracked path, so A1's "ignores" case for a tracked-and-ignored repository could never fire.
- F2 class: **a stored commit compared or shown without resolving it.** Fix: one resolver, `review_bookkeeping.review_commit()` (`full_sha`, i.e. `git rev-parse --verify <sha>^{commit}`), runs once per record per gate evaluation and is kept on the result. The same-commit test, the bookkeeping range, the carried marker and every displayed commit (`policy_line`, refusal reasons through `_shown()`) use it. A record whose commit does not resolve is refused and says so: "<model>'s <verdict> at <sha> (not a commit in this repository) is stale: re-review".
- Red-green: all seven new tests fail with the round-2 `sibling_repos.py` and `review_bookkeeping.py` and pass with the fix.

## Probes

- Pathspec uses in this leaf's diff: `sibling_repos._untracked_by_root` (`ls-files`, now literal; `check-ignore`, which takes plain paths). There are none in `review_bookkeeping.py`, whose `diff_paths` and `rev-list` take commit ranges, now resolved, or in the READY, review-record and validate changes, which only call `sibling_heads_field()` and `warn_unconfigured_sibling_repos()`. Result: one place, fixed.
- Sibling names with `[ ]`, `*` and `?` beside a tracked path they would glob-match (`app[1]`/`app1`, `app*`/`appx/kept.txt`, `app?`/`appz`, `[ab]`/`a`): each is detected, recorded in `sibling_heads`, named once by validate, and refuses the carry after sibling-only rework. All four rows failed before the fix.
- A directory the root tracked, then made its own repository and ignored: listed as a sibling (it failed before `--no-index`).
- Stored-commit uses in this leaf: the same-commit test, the `only_planning_or_review_bookkeeping_since` range, the carried marker, the `policy_line` display and the refusal reasons all go through `review_commit()`.
- A 7-character legacy record counts and shows 12 characters in `policy_line` and `handoff status`.
- A record whose commit does not resolve (`deadbee`): stale, and the policy line says it is not a commit in this repository.
- Recorded `sibling_heads` values are written as full shas from `rev-parse HEAD` and compared as strings. A hand-abbreviated value would not match, so the approval is refused (fails closed). Accepted.
- `delta_from` and `prior_approvals` (in `review_gate.py`, outside the zones) already resolve with `full_sha`. Not changed.

- Every path in `count_at_later_commit` (same commit, bookkeeping carry, plain stale): the map check now runs before all three. Covered by the 5×2 parametrized test (unchanged, added, removed, head moved, renamed × same root commit, summary-only root commit); only unchanged at the same commit counts.
- A sibling removed so that none remain, plus a summary-only root commit (the reported hole): stale.
- A record without `sibling_heads`, its sibling removed, plus a summary-only root commit: carries (legacy rule kept; new test).
- A record without `sibling_heads` at the same commit while siblings exist: counts (existing test).
- A sibling renamed: the key differs, so the map differs: stale.
- A sibling with no commit: neither `sibling_heads()` nor the current map lists it. If it holds files, `git status` makes it dirty, so `heads_problem` refuses; an empty one has nothing to review. Accepted, not changed.
- A dirty sibling at a later root commit: refused by the same check (previously only at the same commit).
- Other consumers of recorded heads: `review_gate.prior_approvals` and `delta_basis` (outside the zones) do not read `sibling_heads`. A delta approval still has to pass `count_at_later_commit` for its own record at the gate, so the map check applies to it too.
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
- `sibling_repos.literal_pathspec()`: the single way this leaf hands a filesystem path to git as a pathspec (F1, round 3).
- `review_bookkeeping.review_commit()`: the single resolver for a record's stored commit, cached per gate evaluation (F2, round 3).
- `review_bookkeeping._shown()`: twelve characters of the resolved sha, or the record's value marked as not a commit (F2, round 3).
- `review_bookkeeping.policy_line()`: the `policy:` line with model@commit and the carried markers (A5).

### Branches and guards
- `count_at_later_commit`: a record whose commit does not resolve is refused with a reason (F2, round 3).
- `count_at_later_commit`: on every path (same commit or later), a stale verdict when the recorded sibling map differs from the current one or a sibling is dirty (A3, fix round 2).
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
- `test_an_approval_counts_only_while_the_recorded_sibling_map_holds[change×root]`: unchanged, added, removed, moved or renamed × same or summary-only root commit (F1).
- `test_a_sibling_named_with_glob_characters_beside_a_tracked_match[4 rows]`: covers detection, `sibling_heads`, the validate warning and the carry refusal for glob-character names (F1, round 3).
- `test_a_tracked_and_ignored_directory_repository_is_a_sibling`: A1's "ignores" case (F1 audit, round 3).
- `test_a_seven_character_legacy_commit_shows_twelve_characters`: F2 (round 3).
- `test_a_record_whose_commit_does_not_resolve_says_so`: F2's "if it can't be resolved, say so" (round 3).
- `_glob_escaped()` (test helper): writes a `.gitignore` pattern that matches only the sibling's own name.
- `test_a_record_without_sibling_heads_carries_when_no_sibling_remains`: the legacy rule holds after the F1 reordering.
- `_change_siblings()` (test helper): applies one sibling-map change for the parametrized test.
- `test_ready_writes_sibling_heads`: READY carries `sibling_heads` (A3).
- `test_ready_without_siblings_writes_no_sibling_heads`: READY is unchanged without siblings (A3).
- `test_policy_line_lists_each_approval_and_marks_a_carried_one`: pins a same-commit and a carried approval in the policy line and in status text and JSON (A5).
- `test_review_record_prints_the_same_policy_line`: `review record`'s closing `policy:` line (A5).
- `test_validate_warns_once_naming_the_siblings[0|2]`: runs `validate_at` on a repo with two unconfigured siblings (or none) and asserts on stderr only: exactly one warning naming both and docs/git-workflow.md, or none (A4).
