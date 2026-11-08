# Implementation summary: M17.2 (gui-orch-view-model)

Commit 705fd8e2 adds the orchestration snapshot contract, a mock snapshot and a pure view model under `gui/pm-gantt/src/`. No component, `api.ts`, route, server or existing type changes. The previous worker (w-0190) left no commits; this is a fresh implementation on the branch.

## Fix round 1 (gpt-6.1-sol block at c672c174)

Finding class: the key-path test merged required-key presence over every object at the same normalized path, so one complete entry hid a sibling entry that was missing the field. The class reached every object reached through a list or the `leaves` map: leaf entries, claims, workers, worktrees, reviews and leafless workers. The fix is a design change in the test's `contractProblems`. Each concrete object is now checked against the required keys whose parent is its path, and a missing key is reported at its concrete location (`leaves.k-blocked.workers[0].harness`). One bounded rule is written in the helper's docstring. Null claims and empty lists or maps have no children to check. The whole-mock check still reports a required path that never appears anywhere (for example a list that is always empty), but it skips paths under a container already reported missing. The module, the mock and the A3 view model are unchanged. Merged origin/WIP/improvements-0-3-1 first (no conflicts).

## Probes

- Reviewer's case, `k-blocked.workers[0].harness` deleted while other workers keep it: reported as exactly `leaves.k-blocked.workers[0].harness` (new it.each row).
- Same class on a second worker in the same leaf (`k-unknown.workers[1].pid_alive`): reported.
- The second of two worktrees (`k-blocked.worktrees[1].dirty`): reported.
- A review entry (`k-held-list.reviews[0].fresh_for_head`): reported.
- A claim (`k-exec-blocked.claim.branch`): reported. Null claims (`k-unknown`) are not flagged: the unchanged mock passes.
- A leaf entry with every required field gone (`leaves.k-held-gate = {}`): reports its claim, workers, worktrees and reviews.
- The only leafless worker missing `started_at`: reported once, with no duplicate from the whole-mock check.
- `leafless_workers` removed entirely: reports `leafless_workers` only, with no cascade of its children; a misspelled worker field is still unlisted.
- Optional-key coverage of the mock: still complete.
- Gate: `npm ci && npm run lint && npm test && npm run build`: lint 0 errors, 250 tests pass, build OK. `ruff check specy_road tests scripts` passes; `specy-road file-limits` is OK (one pre-existing warning on review_node.py, outside this leaf).

## Final touch zones

Unchanged and accurate: `gui/pm-gantt/src/orchestrationSnapshot.ts`, `gui/pm-gantt/src/orchestrationSnapshot.test.ts`, `gui/pm-gantt/src/fixtures/orchestration_snapshot_mock.json`. No file-limits cap applies to TypeScript.

## Acceptance

- **A1** `orchestrationSnapshot.ts` declares `OrchestrationSnapshot` (`schema`, `leaves` keyed by node_key, `leafless_workers`), the v1 required fields per M16.3.1 and the schema 2 fields as optional. `WorkerStatus` is the six-value union. Fields read from a source that can be unreadable accept the literal `"unknown"`. `claim` is `SnapshotClaim | null`, so a leaf can have a review or worker without a claim. The module exports `requiredKeys` and `optionalKeys`.
- **A2** The mock covers all six statuses, a leaf with two worktrees (`k-blocked`), a leafless worker, explicit `unknown` fields (`k-unknown`), a null account, a stale review, gate `blocked` and gate `executor_blocked` with a READY `blocked_on`, a hold-list hold with a reason, a gate hold with a null reason, a worker flagged `stalled` + `steering_changed`, and one flagged `paused_by_limit`. The key-path test fails when a mock path is in neither list or a required path is missing. It also walks into the `leaves` map and every list. I checked by hand that a misspelled `harness` inside a leaf's worker makes it fail, and that test now has a permanent row (`stauts`).
- **A3** `buildOrchestrationView(snapshot, outline, now)`: groups come in outline order, then leaf keys missing from the outline (sorted by key; the display id is the key and the title is "—"), then one "No leaf" group. The badge (`leafBadge`) follows M17.1's precedence. Blocked counts `gate.blocks` when it is above 0, otherwise the number of `ready.blocked_on` entries. Ages come from `formatRelativeAge(iso, now)`. `"unknown"` renders as "unknown", and a missing or null optional field renders as "—". The account is an empty cell when null or missing. Booleans render as dirty/clean and fresh/stale only for real booleans.
- **A4** Table-driven vitest rows with a fixed clock: each badge candidate alone, every adjacent pair in both orders, reversed worker order, numeric-looking display ids kept in outline order, a schema 1 snapshot, explicit unknown, null account, an empty snapshot and leafless workers only. `npm ci && npm run lint && npm test && npm run build` passes: lint 0 errors (41 warnings already there, none in these files), 27 files and 243 tests pass, build OK.

## Decision to review

- **READY awaiting review vs approved:** a READY counts as "awaiting review" only while `gate.state` is not `approved`. Taken literally, M17.1's order (READY above approved) would mean "approved" never shows, because an approved gate always has a READY. The ready+approved pair row therefore expects `approved`.
- **claimed:** the `claimed` badge applies when the leaf has a claim or a worker with status `claimed`.
- **Top-level names:** `leaves` and `leafless_workers` are assumed because M16.3.1's fixture has not landed. If it lands with other names, M17.6 renames both sides (its zones include this module).

## Key paths for M17.6

This list belongs on the planning sheet, which is outside this leaf's zones, so it is written here. Notation: `.` joins object keys, `*` stands for any leaf key under `leaves`, and `[]` stands for any list item.

requiredKeys:
schema, leaves, leaves.*, leaves.*.claim, leaves.*.claim.{codename,branch,registered_at}, leaves.*.workers, leaves.*.workers[].{id,harness,model,status,pid_alive,started_at,ended_at}, leaves.*.worktrees, leaves.*.worktrees[].{path,branch,dirty}, leaves.*.reviews, leaves.*.reviews[].{model,verdict,commit,fresh_for_head}, leafless_workers, leafless_workers[].{id,harness,model,status,pid_alive,started_at,ended_at}

optionalKeys:
leaves.*.workers[].{account,last_activity,flags}, leafless_workers[].{account,last_activity,flags}, leaves.*.worktrees[].{ahead,behind}, leaves.*.ready, leaves.*.ready.{commit,model,at,blocked_on}, leaves.*.ready.blocked_on[].{acceptance,reason}, leaves.*.gate, leaves.*.gate.{state,approvals,blocks,fresh_for_head}, leaves.*.holds, leaves.*.holds[].{source,id,reason}

## Added

- `orchestrationSnapshot.ts` snapshot types (`OrchestrationSnapshot`, `SnapshotLeaf`, `SnapshotWorker`, …): the A1 contract.
- `requiredKeys` / `optionalKeys`: A1 key-path lists for the A2 test and M17.6.
- `leafBadge`: A3's single badge with M17.1 precedence (exported so tests can drive it directly).
- `buildOrchestrationView` and its view types: A3 view model.
- Private helpers `text`, `yesNo`, `age`, `workerRow`, `blockedCount`, `leafGroup`: implement A3's "unknown" / "—" / empty-account rendering, age formatting and the blocked count.
- Guard `formatRelativeAge(...) || "—"`: an unparseable timestamp shows "—" rather than an empty string.
- `snapshot.leaves ?? {}` / `leafless_workers ?? []`: tolerate an empty or partial body.
- Mock `fixtures/orchestration_snapshot_mock.json`: A2 coverage.
- Test helpers `objects` / `childPath` / `keyPaths` / `contractProblems`: walk the mock's objects for A2; required keys are checked on each concrete object (fix round 1).
- Test row table "reports … missing on that one entry": fix round 1 regression, one row per object kind the class reached.
- Tests: key-path contract, misspelled nested field and dropped required field (the "done but wrong" check), status coverage, badge candidates alone, adjacent pairs, executor_blocked count, worker order, outline ordering against the mock, numeric display ids, mock row formatting, explicit unknown, schema 1, empty and leafless-only (A2-A4).
- Mocks: test factories `worker`, `emptyLeaf`, `merge`, `outlineNode` (plain data, no call mocks).
