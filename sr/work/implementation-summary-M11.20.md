# Implementation summary: M11.20 `roster-source-explained`

## What changed

- `specy_road/orchestration_pinned.py` — `roster_source` now:
  - returns the ref shortened to `<remote>/<integration>` (or `<integration>` without a remote), so `orchestrate plan` prints `roster: roadmap/orchestration.yaml at origin/dev` and `roster_ref` in `--json` is the same string;
  - words every drift as "…, where the roster is read from" and, with a remote, says the change must be "committed to <integration> and pushed to <remote>" (not only committed); without a remote, "committed to <integration>";
  - compares three copies — working tree (W), local integration branch (L, counted only when it is ahead of the remote-tracking ref) and the ref (R). W differing from both R and L is uncommitted ("commit to dev and push to origin"). Otherwise L ≠ R is unpushed, whatever W holds (including absent): added ("is committed on the local dev but not on origin/dev … until dev is pushed to origin"), deleted ("is deleted on the local dev but still on origin/dev …") or changed ("on the local dev differs from origin/dev …");
  - with no roster on the ref and none in the working tree, returns a sentence saying so (default roster: one human, no executor) and pointing at `docs/orchestration.md`. `orchestrate plan` already puts any drift in place of the may_process hint, so `orchestrate_plan.py` needed no change.
- `specy_road/bundled_scripts/validate_roadmap.py` — `validate_orchestration_contract` warns on every drift except "no roster anywhere" (so an unpushed local add or delete warns even with no working-tree file); that case stays a stdout notice, so `--strict` and validate runs in repos on the default roster are unaffected. `validate`'s no-file notice appends the no-roster line (`no_orchestration_notice`), which carries the docs pointer.

### Review round 1 (gpt-6.1-sol block, P2)

The first version returned "no roster" before looking at the local branch and ignored a local branch with no roster, so a roster added or deleted on an unpushed local dev went unreported when the working tree matched origin/dev. Fixed by the three-copy comparison above and by keying validate's warning on `roster_report`'s `none_anywhere` flag instead of working-tree presence.
- `docs/orchestration.md` — the roster-ref paragraph says commit **and push** (then fetch), mentions the unpushed-local-branch case and the no-roster case.

Touch zones confirmed: `orchestrate_plan.py` is in scope but unchanged; `orchestrate_cli.py` (prints `roster_ref`) needed no change because the shorter ref flows through.

## Verification

- `python -m pytest -q tests/test_roster_source.py tests/test_worker_cli_fixes.py tests/test_orchestration_config.py tests/test_orchestrate_plan.py tests/test_validate_roadmap.py tests/test_models_and_prompt.py tests/test_node_routing_fields.py tests/test_review_round2_routing.py tests/test_review_round6_policy.py tests/test_worker_review_round2.py tests/test_init_project.py tests/test_project_layouts.py` — 213 passed.
- `specy-road file-limits` — OK.
- Red-green: with `orchestration_pinned.py` and `validate_roadmap.py` from the blocked commit (`1a29580c`), `tests/test_roster_source.py` fails added-unpushed, deleted-unpushed and changed-unpushed-on-dev (3 failed, 4 passed); against the base commit the original two tests also failed.
- `ruff check` on the touched Python files — clean.
- The full `pytest` did not finish within the 10-minute foreground limit (reached 45% with no failure); not claimed as run.

## Added

### Helpers
- `orchestration_pinned.roster_report` — `(ref, drift, none_anywhere)`; `roster_source` wraps it, and validate uses the flag to keep the no-roster case a notice while warning on every other drift.
- `orchestration_pinned._integration` — recovers `(remote, branch)` behind the roster ref so messages can say "pushed to <remote>"; splits the ref as a fallback if `integration_name` errors.
- `orchestration_pinned._unpushed` — true only when the local integration branch has commits the remote-tracking ref lacks, so a merely stale local branch is not reported as unpushed.
- `validate_roadmap.no_orchestration_notice` — the existing no-file notice plus the roster-source line (docs pointer) when there is one.

### Branches / guards
- `roster_source`: no-roster-anywhere branch (A1 second half).
- `roster_report`: three-copy comparison — uncommitted (W ≠ R and W ≠ L), then unpushed added / deleted / changed (L ≠ R), then no roster anywhere (A1 "or the local integration branch").
- `validate_orchestration_contract`: warn on any drift but `none_anywhere`, which stays a stdout notice.

### Mocks
- none

### Tests (`tests/test_roster_source.py`, new: `test_worker_cli_fixes.py` would pass 400 lines)
- `_pushed` — helper giving the plan repo a bare `origin` with `origin/HEAD` → `dev`, so routing reads `origin/dev`.
- `_cli` — runs `orchestrate plan --json` and `validate` through their CLI entry points and returns plan JSON, validate stdout and stderr.
- `ROSTER_STATES` + `test_plan_and_validate_name_the_roster_source_and_remedy` — A2, parametrized over in-sync, uncommitted, changed-unpushed (feature branch from origin/dev, and on dev itself), added-unpushed and deleted-unpushed: plan names `origin/dev` and the exact remedy instead of the may_process hint, validate warns with the same sentence; after the named remedy (commit/push, fetch) the drift clears (a pushed deletion leaves the no-roster notice, not a warning).
- `test_no_roster_anywhere_points_at_the_docs_not_the_may_process_hint` (moved here from `test_worker_cli_fixes.py`) — A2: no roster at the ref or in the working tree: plan problem and validate notice name the ref and `docs/orchestration.md`; validate emits no stderr warning.
