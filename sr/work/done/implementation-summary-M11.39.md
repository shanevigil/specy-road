# Implementation summary — M11.39 roster-availability

## Goal

Roster entries can be paused locally (`available: false`, `paused_until`, or legacy `unavailable_until`) via untracked `roadmap/orchestration.local.yaml`, merged at runtime onto the integration-branch roster. Routing skips paused models; delegate paths refuse with a reason; past review records still count.

## Touch zones (confirmed)

Listed on the leaf, plus three paths added with `edit-node --add` because A1 cannot land without them after M11.59 split the worker module:

- `specy_road/orchestration_config.py`, `specy_road/orchestrate_plan.py`, `specy_road/worker_ops.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/templates/project/schemas/orchestration.schema.json`, `docs/orchestration.md`, `tests/`
- `specy_road/worker_ops_launch.py`, `specy_road/bundled_scripts/role_prompt.py`, `specy_road/templates/project/.gitignore`, `specy_road/review_eligible.py`, `specy_road/agent_ignores.py`

`specy_road/worker_ops.py` is unchanged (it re-exports launch); the eligibility check lives in `worker_ops_launch`.

## Out-of-zone files

- `specy_road/worker_ops_launch.py` — A1's worker-delegate refusal: `_check_eligible` lives here after M11.59 split `worker_ops`.
- `specy_road/bundled_scripts/role_prompt.py` — A1's review-delegate refusal: `review delegate` calls `build_prompt`, which must name `available: false` / `paused_until`, not only legacy `unavailable_until`.
- `specy_road/templates/project/.gitignore` — comment-only note for the overlay; live ignore rule is in `GITIGNORE_LINES` (M11.43 pattern).
- `specy_road/agent_ignores.py` — `init project` / `refresh-stubs` write consumer `.gitignore` from `GITIGNORE_LINES` (prefixed under nested layout); overlay must not stay committable when the template seed is skipped.
- `specy_road/review_eligible.py` — Grok required restoring `review_cli.py` prose; handoff exclusion for paused models belongs in `reviewer_eligibility`, not in shortened CLI docs.
- `sr/schemas/orchestration.schema.json` — reverted; the shipped schema is the templates copy already in the original zones, and this nested project copy is not required for A1/A2.

## Acceptance

- **A1:** Overlay merge in `effective_config`; `is_available` / `unavailability_reason` in `orchestrate_plan`; planner, `worker delegate`, and `prompt` / `review delegate` (via `build_prompt`) refuse paused models.
- **A2:** `tests/test_roster_availability.py` covers `available: false`, `paused_until` past/future, overlay, and gate still met when the reviewer is paused locally after filing.
- **A3:** Not implemented — M8.2 worker paused-by-limit state is not present on this branch (`worker sync` has no usage-limit pause to attach a `paused_until` hint to).

## Verification

- `pytest tests/test_roster_availability.py tests/test_orchestrate_plan.py tests/test_orchestration_config.py tests/test_review_eligible.py tests/test_agent_ignores.py`
- `specy-road file-limits`

## Added

- `load_availability_overlay`, `apply_availability_overlay`, `orchestration_local_path` in `orchestration_config.py` — read and merge local availability without touching committed roster.
- `_paused_until_error`, extended `_date_error` / `_dates_to_iso` in `orchestration_config.py` — validate date and datetime pauses.
- `_pause_active`, `unavailability_reason`, `unavailable_prompt_error` in `orchestrate_plan.py` — shared availability rules and refuse-with-reason text.
- Availability exclusion in `review_eligible._roster_reason` — skipped when that model's approval already counts, so `handoff status` still says ``its approval counts`` (optionally ``; unavailable for new reviews``).
- Schema fields `available`, `paused_until`; `roadmap/orchestration.local.yaml` in `agent_ignores.GITIGNORE_LINES` (template `.gitignore` comment only).
- `tests/test_roster_availability.py` — behavioural coverage for A1/A2, including a counted paused reviewer under `reviewers_required: 2`.
- `tests/test_agent_ignores.py::test_orchestration_local_overlay_is_gitignored` — flat and nested gitignore for the overlay.
