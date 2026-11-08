# Implementation summary: M17.2 (gui-orch-view-model)

Commit 705fd8e2 adds the orchestration snapshot contract, a mock snapshot and a pure view model under `gui/pm-gantt/src/`. No component, `api.ts`, route, server or existing type changes. The previous worker (w-0190) left no commits; this is a fresh implementation on the branch.

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
- Test helpers `keyPaths` / `contractProblems`: walk mock key paths for A2.
- Tests: key-path contract, misspelled nested field and dropped required field (the "done but wrong" check), status coverage, badge candidates alone, adjacent pairs, executor_blocked count, worker order, outline ordering against the mock, numeric display ids, mock row formatting, explicit unknown, schema 1, empty and leafless-only (A2-A4).
- Mocks: test factories `worker`, `emptyLeaf`, `merge`, `outlineNode` (plain data, no call mocks).
