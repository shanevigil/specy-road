# Implementation summary — M10.19 (`no-foreign-kills`)

## What changed

- **A1** — `specy_road/bundled_scripts/role_prompt_rca.py`, `executor_preamble`: the "You may not" list now ends with
  "or kill a process by name or pattern (`pkill`, `killall`, `kill` on `pgrep` output)", then gives the reason (other
  sessions share the machine and their runs match the same pattern) and the one allowed case: stop only a process you
  started, by the pid you recorded when you started it. The wording names no harness. File: 228 → 231 lines.
- **A2 (docs)** — `docs/orchestration-workers.md`: a new **Killing by pattern** paragraph next to the **Backgrounded
  tests** note from M10.15. It records the failure (`pkill -f "pytest -q"` ended the coordinator's and other leaves'
  pytest runs with SIGTERM and no failure reported) and the prompt rule. The file was exactly at its 400-line cap,
  so I put the Backgrounded-tests paragraph on one line (the same style as the **Waiting** paragraph above it); the
  wording did not change. File: 400 → 395 lines.
- **A2 (test)** — `tests/test_models_and_prompt.py`: I added one assertion to
  `test_executor_prompt_has_precondition_boundary_rules_and_brief`, so the rendered executor prompt must carry the
  rule. File: 399 → 400 lines (at the cap; `file-limits` passes).

## Touch zones

Confirmed as declared: `specy_road/bundled_scripts/role_prompt_rca.py`, `docs/orchestration-workers.md`, `tests/`.
Only one other place has the old may-not wording: `docs/design-notes/model-aware-orchestration-proposal.md`. It is a
byte-for-byte copy of the original proposal (see `constraints/file-limits.yaml`), so I left it unchanged.

## Verification

- `python -m pytest tests/test_models_and_prompt.py -q` → 25 passed
- `specy-road file-limits` → `OK: file limits satisfied.`
- The 15 test files that import or render the role prompt or name `orchestration-workers` (`grep -rlE "role_prompt|build_prompt|executor_preamble|orchestration-workers" tests | xargs python -m pytest -q`) → 194 passed
- I could not finish the full suite (`python -m pytest -q -x`). It ran longer than the harness allows (10 minutes in the foreground, then 10 in the background), and the harness stopped it before it printed a result. I don't know whether it passes; the coordinator's pre-landing run should cover it.

## Added

### Helpers
none

### Branches or guards
none

### Mocks
none

### Tests
- One assertion in `test_executor_prompt_has_precondition_boundary_rules_and_brief`: the rendered executor prompt has
  the no-pattern-kill rule and the pid-only exception (A2).
