# Implementation summary: M11.20 `roster-source-explained`

## What changed

- `specy_road/orchestration_pinned.py` — `roster_source` now:
  - returns the ref shortened to `<remote>/<integration>` (or `<integration>` without a remote), so `orchestrate plan` prints `roster: roadmap/orchestration.yaml at origin/dev` and `roster_ref` in `--json` is the same string;
  - words every drift as "…, where the roster is read from" and, with a remote, says the change must be "committed to <integration> and pushed to <remote>" (not only committed); without a remote, "committed to <integration>";
  - flags a local integration branch that is ahead of the remote-tracking ref with a roster that differs from it ("on the local dev differs from origin/dev … until dev is pushed to origin"), even when the working tree matches the ref;
  - with no roster on the ref and none in the working tree, returns a sentence saying so (default roster: one human, no executor) and pointing at `docs/orchestration.md`. `orchestrate plan` already puts any drift in place of the may_process hint, so `orchestrate_plan.py` needed no change.
- `specy_road/bundled_scripts/validate_roadmap.py` — `validate_orchestration_contract` warns only when the working-tree file exists (a missing file stays a stdout notice, so `--strict` and every validate run in a repo without a roster are unaffected); `validate`'s no-file notice now appends the drift line (`no_orchestration_notice`), which carries the docs pointer.
- `docs/orchestration.md` — the roster-ref paragraph says commit **and push** (then fetch), mentions the unpushed-local-branch case and the no-roster case.

Touch zones confirmed: `orchestrate_plan.py` is in scope but unchanged; `orchestrate_cli.py` (prints `roster_ref`) needed no change because the shorter ref flows through.

## Verification

- `python -m pytest -q tests/test_worker_cli_fixes.py tests/test_orchestration_config.py tests/test_orchestrate_plan.py tests/test_validate_roadmap.py tests/test_models_and_prompt.py tests/test_node_routing_fields.py tests/test_review_round2_routing.py tests/test_review_round6_policy.py tests/test_worker_review_round2.py tests/test_init_project.py tests/test_project_layouts.py` — 208 passed.
- `specy-road file-limits` — OK.
- Red-green: with `orchestration_pinned.py` from the base commit, both new tests fail.
- The full `pytest` did not finish within the 10-minute foreground limit (reached 45% with no failure); not claimed as run.

## Added

### Helpers
- `orchestration_pinned._integration` — recovers `(remote, branch)` behind the roster ref so messages can say "pushed to <remote>"; splits the ref as a fallback if `integration_name` errors.
- `orchestration_pinned._unpushed` — true only when the local integration branch has commits the remote-tracking ref lacks, so a merely stale local branch is not reported as unpushed.
- `validate_roadmap.no_orchestration_notice` — the existing no-file notice plus the roster-source line (docs pointer) when there is one.

### Branches / guards
- `roster_source`: no-roster-anywhere branch (A1 second half).
- `roster_source`: local-integration-branch-differs branch (A1 "or the local integration branch").
- `validate_orchestration_contract`: warn only when the working-tree file exists, keeping the no-file case a stdout notice.

### Mocks
- none

### Tests (`tests/test_worker_cli_fixes.py`)
- `_pushed` — helper giving the plan repo a bare `origin` with `origin/HEAD` → `dev`, so routing reads `origin/dev`.
- `test_a_committed_but_unpushed_roster_says_to_push` — A2: roster committed on local dev but not pushed: plan and validate name `origin/dev` and say commit and push, not the may_process hint; on a branch matching origin the local-dev-ahead message appears; after push and fetch the drift clears.
- `test_no_roster_anywhere_points_at_the_docs_not_the_may_process_hint` — A2: no roster at the ref or in the working tree: plan problem and validate notice name the ref and `docs/orchestration.md`; validate emits no stderr warning.
