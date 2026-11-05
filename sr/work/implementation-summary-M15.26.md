# Implementation summary: M15.26

A finished worker no longer takes a `policy.max_workers` slot. A registry claim with no live worker, no live session on its branch, and no valid READY at the branch tip is listed by `handoff status` and by `doctor` (report only). When `worker delegate` fails after the leaf is claimed, and when grind-session's implement hook fails, the error says the leaf stays claimed and names the two commands that resolve it.

## Acceptance

- **A1:** `SLOT_STATES` is `starting`, `running`, `idle`, `paused_by_limit`. `holding_slots` counts only those, and still frees an idle or `paused_by_limit` worker whose leaf is over. `completed`, `failed` and `terminated` never count, whatever the leaf. `HELD_STATES` is unchanged (`idle`, `completed`, `paused_by_limit`), so orphan detection and `finish` still see a completed worker. `slot_breakdown` lists only counted workers. `_slot_or_existing` still returns another active record on the same node (including `completed`) before the cap; the count goes through `holding_slots`. `worker_lease.slot_error` is unchanged and was not edited (outside the zones): callers pass `holding_slots` output, so the count matches the breakdown. Tests: 19 completed or failed records plus one running worker, `max_workers` 2, leave a slot free once the second running record is failed; two running workers refuse, and the refusal names only those two.
- **A2:** `specy_road/orphaned_claims.py` lists each registry claim with no record in `SLOT_STATES` on its leaf, no live session whose branch is the claim's (`session_presence.list_sessions`), and no valid READY at the tip (`review_files.latest_ready` compared with the branch tip). Age is the branch's last commit (`git log -1 --format=%cI`), else the row's `started` date (a date-only value is midnight UTC), else `unknown`. `handoff status` prints the lines and adds `orphaned_claims` to the JSON. `review_cli.py` stays 400 lines: the session and worker lines were folded to pay for the import and the print. `doctor` prints `Claims with no live worker (report only; --fix does not release them):` after the tidy sections, outside `FIX_ORDER`, so `--fix` never asks about them or removes them. A claim with a failed worker and no READY is listed; a running worker, a live session on the branch, or a valid READY at the tip is not.
- **A3:** `worker delegate` failure after the leaf is claimed (no live worker on that leaf) ends with `<ID> stays claimed with no worker: retry \`specy-road worker delegate <ID>\` or release it with \`specy-road abort-task-pickup\``. An unclaimed refusal and a non-delegate error do not. grind-session's human `hook_failed` line for `phase=implement` adds the same sentence; other phases and JSON events do not. The orchestrate command's delegate step says to resolve such a claim before the next pickup. Out of scope, and not done: rolling back the claim, removing the worktree, and claims held by another clone.

## Decisions

- The slot set is a new `SLOT_STATES`. Removing `completed` from `HELD_STATES` would have stopped orphan detection and `finish` from seeing that worker, and `chore_cli` (outside the zones) still imports `HELD_STATES`.
- The hint is applied in `worker_cli.main`'s `WorkerError` / `LeaseError` handler, only for `delegate`, so it covers a slot refusal, a usage limit and a launch error. `worker_cli.py` is 399 lines (it was 397): one import and one assignment that feeds the existing print. The file-limits cap is 1000; `specy-road file-limits` is OK.
- `specy_road/worker_lease.py` and `specy_road/worker_runner.py` still say a completed worker keeps its slot or its lease. They are outside the zones. Lease release on sync already calls `holding_slots`, so a completed record drops out of the count without those edits.

## Final touch zones

Unchanged: `specy_road/worker_orphans.py`, `specy_road/worker_ops_slots.py`, `specy_road/orphaned_claims.py` (new), `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/doctor.py`, `specy_road/bundled_scripts/worker_cli.py`, `specy_road/bundled_scripts/grind_session_events.py`, `specy_road/templates/specyrd/commands/specyrd-orchestrate.md`, `tests/`.

## Checks

- `pytest -n 4 tests/test_orphaned_claims.py tests/test_worker_orphans.py tests/test_doctor.py tests/test_worker_cli.py tests/test_session_presence.py tests/test_review_cli.py tests/test_worker_resume_failed.py tests/test_worker_turn_check.py tests/test_grind_session.py tests/test_grind_session_step.py tests/test_grind_session_claude.py`: 162 passed.
- `specy-road file-limits`: OK. `review_cli.py` is 400 lines.

## Added

### Helpers

- `worker_orphans.SLOT_STATES`: the four states `policy.max_workers` counts; finished states are not in it.
- `orphaned_claims.stays_claimed`: the sentence a failed delegate and an implement `hook_failed` line both end with.
- `orphaned_claims.append_claim_hint`: appends that sentence when the node is claimed and has no live worker.
- `orphaned_claims.orphaned_claims`: the claims with no live worker, live session or READY at the tip, each with its age.
- `orphaned_claims.report_lines`: one line per claim, with the age and the two commands.
- `orphaned_claims._entries`: registry rows that have a node id and a branch.
- `orphaned_claims._claimed`: whether that node has a registry row.
- `orphaned_claims._live_worker`: whether that node has a record in `SLOT_STATES`.
- `orphaned_claims._live_worker_in`: the same check against an already loaded record list.
- `orphaned_claims._ready_at_tip`: a valid READY whose commit is the branch tip.
- `orphaned_claims._branch_time`: the branch's last commit time, or nothing when the branch is missing.
- `orphaned_claims._parse_when`: an ISO timestamp, or a date-only `started` value at midnight UTC.
- `orphaned_claims._age`: `Nd`, `Nh`, `Nm`, or `under 1m`.
- `doctor._print_orphaned_claims`: the report-only section, printed only when the list is non-empty.
- `grind_session_events._human_hook_failed`: the `hook_failed` line, including the claim sentence for `phase=implement`, so that branch stays out of `_human`.

### Branches or guards

- `holding_slots` keeps a record only when its state is in `SLOT_STATES` and `_cause` does not free it.
- `slot_breakdown` drops any record whose state is not in `SLOT_STATES` before it groups the refusal.
- `append_claim_hint` returns the message unchanged when there is no node, the node is not claimed, or a live worker is on it.
- `orphaned_claims` skips a claim that has a live worker, a live session on its branch, or a valid READY at the tip, and uses `unknown` when neither a commit nor `started` exists.
- grind `hook_failed` adds the sentence only for `phase=implement` when the node id is set; JSON output is unchanged. The sentence is built in `_human_hook_failed`, so `_human` keeps the branch it had before this leaf.
- `cmd_doctor` prints the claim section after the tidy sections and does not put it in `FIX_ORDER`, so `--fix` never acts on it.
- `cmd_handoff_status` prints the report lines (an empty list prints nothing) and adds `orphaned_claims` to the existing JSON object.
- `worker_cli.main` passes the node id into the hint only when the command is `delegate`.

### Mocks

- `test_finished_records_leave_a_slot_and_two_running_workers_refuse` patches `specy_road.worker_ops_slots.wrapper_gone` to always return false, so a pid-less running record is not swept to `failed` before the cap is counted.

### Tests

- `test_finished_records_leave_a_slot_and_two_running_workers_refuse`: 19 finished records plus one running worker leave a slot; two running workers refuse, and the claimed leaf's error ends with the resolve sentence.
- `test_a_failed_worker_is_listed_and_a_running_worker_session_or_ready_is_not`: the failed claim and a branch-less claim with a `started` date are listed; a running worker, a live session and a READY at the tip are not; `handoff status` text and JSON agree.
- `test_implement_hook_failed_says_the_leaf_stays_claimed`: the implement human line includes the sentence; the finish line and the JSON event do not.
- `test_orchestrate_delegate_step_says_to_resolve_the_claim`: the delegate step names both commands.
- `test_an_unclaimed_or_non_delegate_failure_has_no_claim_hint`: an unclaimed delegate and a `resume` of a missing worker do not get the sentence.
- `test_doctor.py` dry-run and post-`--fix` assertions: the heading is present, `--fix` still removes only the tidy findings, and the remaining claim is still reported.
