# Implementation summary: M11.20 `roster-source-explained`

## What changed

- `specy_road/orchestration_pinned.py` — `roster_source` now:
  - returns the ref shortened to `<remote>/<integration>` (or `<integration>` without a remote), so `orchestrate plan` prints `roster: roadmap/orchestration.yaml at origin/dev` and `roster_ref` in `--json` is the same string;
  - words every drift as "…, where the roster is read from" and, with a remote, says the change must be "committed to <integration> and pushed to <remote>" (not only committed); without a remote, "committed to <integration>";
  - compares three copies — working tree (W), local integration branch (L, counted only when it is ahead of the remote-tracking ref) and the ref (R). W differing from both R and L is uncommitted ("commit to dev and push to origin"). Otherwise L ≠ R is unpushed, whatever W holds (including absent): added ("is committed on the local dev but not on origin/dev … until dev is pushed to origin"), deleted ("is deleted on the local dev but still on origin/dev …") or changed ("on the local dev differs from origin/dev …");
  - with no roster on the ref and none in the working tree, returns a sentence saying so (default roster: one human, no executor) and pointing at `docs/orchestration.md`. `orchestrate plan` already puts any drift in place of the may_process hint, so `orchestrate_plan.py` needed no change.
- `specy_road/bundled_scripts/validate_roadmap.py` — `validate_orchestration_contract` warns on every drift except "no roster anywhere" (so an unpushed local add or delete warns even with no working-tree file); that case stays a stdout notice, so `--strict` and validate runs in repos on the default roster are unaffected. `validate`'s no-file notice appends the no-roster line (`no_orchestration_notice`), which carries the docs pointer.

### Review round 2 (gpt-6.1-sol block, P2)

A working-tree deletion with the roster still on the ref (and on the local dev) gave no drift, and `validate`'s missing-file notice claimed the default policy applied. Now the uncommitted check covers an absent working-tree file ("is deleted in the working tree but still on origin/dev … until the deletion is committed to dev and pushed to origin"). `roster_report` returns a `RosterReport` (`ref`, `drift`, `none_anywhere`, `on_ref`), and `validate` drops the "default policy applies" notice while the ref has a roster: the warning says what routing uses.

### Every state, through the CLI

`orchestrate plan --json` and `validate`, run on a plan repo with a bare `origin` (`origin/HEAD` → `dev`), on `dev`. Copies: origin/dev holds roster A or none; local dev is the same as origin (not ahead), ahead with a changed roster B (with no roster on origin: an added B), or ahead with none (with no roster on origin, an empty commit); the working tree is *present* (A, the origin copy; with no roster on origin, A written in the working tree), *changed* (a third text C), *absent*, or *as-local* (exactly the local dev's committed copy, a distinct state whenever local dev differs). "warning (same sentence)" means `validate` printed `warning: <roster_drift>` on stderr. "default-policy notice + no-roster line" means stdout had `NO_ORCHESTRATION_NOTICE` followed by `notice: <roster_drift>`; no other row prints the default-policy notice. The script lived in the session scratchpad, not the repo.

| working tree | local dev | origin/dev | plan `roster_drift` | validate |
|---|---|---|---|---|
| present | same | present | (none — in sync) | none |
| changed | same | present | roadmap/orchestration.yaml in the working tree differs from origin/dev, where the roster is read from; routing uses the copy there until the change is committed to dev and pushed to origin | warning (same sentence) |
| absent | same | present | roadmap/orchestration.yaml is deleted in the working tree but still on origin/dev, where the roster is read from; routing uses the copy there until the deletion is committed to dev and pushed to origin | warning (same sentence) |
| present | changed | present | roadmap/orchestration.yaml on the local dev differs from origin/dev, where the roster is read from; routing uses the copy there until dev is pushed to origin | warning (same sentence) |
| changed | changed | present | roadmap/orchestration.yaml in the working tree differs from origin/dev, where the roster is read from; routing uses the copy there until the change is committed to dev and pushed to origin | warning (same sentence) |
| absent | changed | present | roadmap/orchestration.yaml is deleted in the working tree but still on origin/dev, where the roster is read from; routing uses the copy there until the deletion is committed to dev and pushed to origin | warning (same sentence) |
| as-local | changed | present | roadmap/orchestration.yaml on the local dev differs from origin/dev, where the roster is read from; routing uses the copy there until dev is pushed to origin | warning (same sentence) |
| present | absent | present | roadmap/orchestration.yaml is deleted on the local dev but still on origin/dev, where the roster is read from; routing uses the copy there until dev is pushed to origin | warning (same sentence) |
| changed | absent | present | roadmap/orchestration.yaml in the working tree differs from origin/dev, where the roster is read from; routing uses the copy there until the change is committed to dev and pushed to origin | warning (same sentence) |
| absent | absent | present | roadmap/orchestration.yaml is deleted on the local dev but still on origin/dev, where the roster is read from; routing uses the copy there until dev is pushed to origin | warning (same sentence) |
| as-local | absent | present | roadmap/orchestration.yaml is deleted on the local dev but still on origin/dev, where the roster is read from; routing uses the copy there until dev is pushed to origin | warning (same sentence) |
| present | same | absent | roadmap/orchestration.yaml is not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until it is committed to dev and pushed to origin | warning (same sentence) |
| changed | same | absent | roadmap/orchestration.yaml is not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until it is committed to dev and pushed to origin | warning (same sentence) |
| absent | same | absent | no roadmap/orchestration.yaml on origin/dev, where the roster is read from, nor in the working tree, so routing uses the default roster (one human, no executor); see docs/orchestration.md to write and commit one | default-policy notice + no-roster line |
| present | changed | absent | roadmap/orchestration.yaml is not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until it is committed to dev and pushed to origin | warning (same sentence) |
| changed | changed | absent | roadmap/orchestration.yaml is not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until it is committed to dev and pushed to origin | warning (same sentence) |
| absent | changed | absent | roadmap/orchestration.yaml is committed on the local dev but not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until dev is pushed to origin | warning (same sentence) |
| as-local | changed | absent | roadmap/orchestration.yaml is committed on the local dev but not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until dev is pushed to origin | warning (same sentence) |
| present | absent | absent | roadmap/orchestration.yaml is not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until it is committed to dev and pushed to origin | warning (same sentence) |
| changed | absent | absent | roadmap/orchestration.yaml is not on origin/dev, where the roster is read from, so routing uses the default roster (no models) until it is committed to dev and pushed to origin | warning (same sentence) |
| absent | absent | absent | no roadmap/orchestration.yaml on origin/dev, where the roster is read from, nor in the working tree, so routing uses the default roster (one human, no executor); see docs/orchestration.md to write and commit one | default-policy notice + no-roster line |
| as-local | absent | absent | no roadmap/orchestration.yaml on origin/dev, where the roster is read from, nor in the working tree, so routing uses the default roster (one human, no executor); see docs/orchestration.md to write and commit one | default-policy notice + no-roster line |

Each row is correct: routing reads origin/dev in every row. A working tree that matches neither origin/dev nor the local dev is told to commit and push. When only the local dev differs, the message names the add, delete or change and says to push dev. In sync is silent. No roster anywhere points at docs/orchestration.md as a notice, not a warning. Two rows have two causes and give one remedy that covers both. *changed / changed / present*: the working tree differs from both copies, so the remedy is commit and push. *absent / changed / absent*: the working tree deleted the unpushed local roster, and the message reports the unpushed addition, which is what routing will read once dev is pushed.

### Review round 1 (gpt-6.1-sol block, P2)

The first version returned "no roster" before looking at the local branch and ignored a local branch with no roster, so a roster added or deleted on an unpushed local dev went unreported when the working tree matched origin/dev. Fixed by the three-copy comparison above and by keying validate's warning on `roster_report`'s `none_anywhere` flag instead of working-tree presence.
- `docs/orchestration.md` — the roster-ref paragraph says commit **and push** (then fetch), mentions the unpushed-local-branch case and the no-roster case.

Touch zones confirmed: `orchestrate_plan.py` is in scope but unchanged; `orchestrate_cli.py` (prints `roster_ref`) needed no change because the shorter ref flows through.

## Verification

- `python -m pytest -q tests/test_roster_source.py tests/test_worker_cli_fixes.py tests/test_orchestration_config.py tests/test_orchestrate_plan.py tests/test_validate_roadmap.py tests/test_models_and_prompt.py tests/test_node_routing_fields.py tests/test_review_round2_routing.py tests/test_review_round6_policy.py tests/test_worker_review_round2.py tests/test_init_project.py tests/test_project_layouts.py` — 214 passed.
- `specy-road file-limits` — OK.
- Red-green, round 2: with `orchestration_pinned.py` and `validate_roadmap.py` from `21b99fb2`, `tests/test_roster_source.py` fails deleted-uncommitted (1 failed, 7 passed).
- Red-green, round 1: with `orchestration_pinned.py` and `validate_roadmap.py` from the blocked commit (`1a29580c`), `tests/test_roster_source.py` fails added-unpushed, deleted-unpushed and changed-unpushed-on-dev (3 failed, 4 passed); against the base commit the original two tests also failed.
- `ruff check` on the touched Python files — clean.
- The full `pytest` did not finish within the 10-minute foreground limit (reached 45% with no failure); not claimed as run.

## Added

### Helpers
- `orchestration_pinned.RosterReport` / `roster_report` — `(ref, drift, none_anywhere, on_ref)`; `roster_source` wraps it. Validate keeps the no-roster case a notice and warns on every other drift (`none_anywhere`), and drops the default-policy notice while the ref has a roster (`on_ref`).
- `orchestration_pinned._integration` — recovers `(remote, branch)` behind the roster ref so messages can say "pushed to <remote>"; splits the ref as a fallback if `integration_name` errors.
- `orchestration_pinned._unpushed` — true only when the local integration branch has commits the remote-tracking ref lacks, so a merely stale local branch is not reported as unpushed.
- `validate_roadmap.no_orchestration_notice` — the existing no-file notice plus the roster-source line (docs pointer) when there is one.

### Branches / guards
- `roster_source`: no-roster-anywhere branch (A1 second half).
- `roster_report`: three-copy comparison — uncommitted (W ≠ R and W ≠ L: deleted in the working tree, not on the ref, or differs), then unpushed added / deleted / changed (L ≠ R), then no roster anywhere (A1 "or the local integration branch").
- `no_orchestration_notice` returns `None` when the ref has a roster, and `main` prints the notice only when there is one.
- `validate_orchestration_contract`: warn on any drift but `none_anywhere`, which stays a stdout notice.

### Mocks
- none

### Tests (`tests/test_roster_source.py`, new: `test_worker_cli_fixes.py` would pass 400 lines)
- `_pushed` — helper giving the plan repo a bare `origin` with `origin/HEAD` → `dev`, so routing reads `origin/dev`.
- `_cli` — runs `orchestrate plan --json` and `validate` through their CLI entry points and returns plan JSON, validate stdout and stderr.
- `_arrange` / `_remedy` — set up each state on the local dev and apply the remedy the sentence names (split out to keep the test under ruff's complexity limit).
- `ROSTER_STATES` + `test_plan_and_validate_name_the_roster_source_and_remedy` — A2, parametrized over in-sync, uncommitted, deleted-uncommitted (round 2; also asserts no default-policy notice), changed-unpushed (feature branch from origin/dev, and on dev itself), added-unpushed and deleted-unpushed: plan names `origin/dev` and the exact remedy instead of the may_process hint, validate warns with the same sentence; after the named remedy (commit/push, fetch) the drift clears (a pushed deletion leaves the no-roster notice, not a warning).
- `test_no_roster_anywhere_points_at_the_docs_not_the_may_process_hint` (moved here from `test_worker_cli_fixes.py`) — A2: no roster at the ref or in the working tree: plan problem and validate notice name the ref and `docs/orchestration.md`; validate emits no stderr warning.
