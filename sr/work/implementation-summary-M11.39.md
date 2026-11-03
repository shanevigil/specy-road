# Implementation summary — M11.39 roster-availability

## Goal

Roster entries can be paused locally (`available: false`, `paused_until`, or legacy `unavailable_until`) via untracked `roadmap/orchestration.local.yaml`, merged at runtime onto the integration-branch roster. Routing skips paused models; delegate paths refuse with a reason; past review records still count.

## Touch zones (confirmed)

Listed on the leaf, plus three paths added with `edit-node --add` because A1 cannot land without them after M11.59 split the worker module:

- `specy_road/orchestration_config.py`, `specy_road/orchestrate_plan.py`, `specy_road/worker_ops.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/templates/project/schemas/orchestration.schema.json`, `docs/orchestration.md`, `tests/`
- `specy_road/worker_ops_launch.py`, `specy_road/bundled_scripts/role_prompt.py`, `specy_road/templates/project/.gitignore`

`specy_road/worker_ops.py` is unchanged (it re-exports launch); the eligibility check lives in `worker_ops_launch`.

## Out-of-zone files

- `specy_road/worker_ops_launch.py` — A1's worker-delegate refusal: `_check_eligible` lives here after M11.59 split `worker_ops`.
- `specy_road/bundled_scripts/role_prompt.py` — A1's review-delegate refusal: `review delegate` calls `build_prompt`, which must name `available: false` / `paused_until`, not only legacy `unavailable_until`.
- `specy_road/templates/project/.gitignore` — A1's overlay is untracked so availability needs no push; `init project` must ignore `roadmap/orchestration.local.yaml`.
- `sr/schemas/orchestration.schema.json` — reverted; the shipped schema is the templates copy already in the original zones, and this nested project copy is not required for A1/A2.

## Acceptance

- **A1:** Overlay merge in `effective_config`; `is_available` / `unavailability_reason` in `orchestrate_plan`; planner, `worker delegate`, and `prompt` / `review delegate` (via `build_prompt`) refuse paused models.
- **A2:** `tests/test_roster_availability.py` covers `available: false`, `paused_until` past/future, overlay, and gate still met when the reviewer is paused locally after filing.
- **A3:** Not implemented — M8.2 worker paused-by-limit state is not present on this branch (`worker sync` has no usage-limit pause to attach a `paused_until` hint to).

## Verification

- `pytest tests/test_roster_availability.py tests/test_orchestrate_plan.py tests/test_orchestration_config.py`
- `specy-road file-limits`

## Added

- `load_availability_overlay`, `apply_availability_overlay`, `orchestration_local_path` in `orchestration_config.py` — read and merge local availability without touching committed roster.
- `_paused_until_error`, extended `_date_error` / `_dates_to_iso` in `orchestration_config.py` — validate date and datetime pauses.
- `_pause_active`, `unavailability_reason`, `unavailable_prompt_error`, `mark_handoff_unavailability` in `orchestrate_plan.py` — shared availability rules and handoff status rows.
- `mark_handoff_unavailability` call in `review_cli.py` — handoff lists paused reviewers as excluded.
- Schema fields `available`, `paused_until`; gitignore line for `orchestration.local.yaml`.
- `tests/test_roster_availability.py` — behavioural coverage for A1/A2.
