# Implementation summary: `M10.15` — foreground-long-commands

## What changed

- `specy_road/bundled_scripts/role_prompt_rca.py` — step 3 of `executor_preamble` now says to run the
  verifier and tests the brief names **in the foreground**, with a long timeout if the harness has one, and
  not to end the turn while a command the executor started is still running, because a headless turn ends
  when the agent replies and nothing resumes it when a background job finishes. Harness-neutral (no tool
  names). The commit-by-explicit-path rule is unchanged. File is 222 lines (cap 400).  (A1, A3)
- `docs/orchestration-workers.md` — a **Backgrounded tests** paragraph after the worker-job description
  names the failure (`completion` with exit 0 and READY missing after a reply saying a background run is
  still going) and the coordinator's recovery: `worker message W --text` telling the executor to rerun in
  the foreground, wait, and finish its steps.  (A2)
- `tests/test_models_and_prompt.py` — new test asserting the rendered executor prompt's step 3 carries the
  foreground rule and its reason.  (A3)

## Pinned prompt text

No test pins step 3 of the executor preamble: `tests/test_context_regressions.py` asserts only the role
heading and brief header, and `tests/test_shared_checkout_guidance.py` pins the AGENTS.md block's
commit rule (different text, not in this preamble). Nothing needed updating or loosening.

## Touch zones (confirmed)

`specy_road/bundled_scripts/role_prompt_rca.py`, `docs/orchestration-workers.md`, `tests/` — accurate.
`specy_road/bundled_scripts/do_next_prompt.py` also says "Run the verifier" but is the single-agent
do-next prompt, not the headless executor preamble; left alone (outside the zones and the acceptance).

## Verification

- `pytest tests/test_models_and_prompt.py tests/test_context_regressions.py` — 27 passed.
- `specy-road file-limits` — OK.
- Full `pytest` — 2567 passed, 2 skipped (15m32s; ran past the 600s foreground limit, so I waited on it before finishing).

## Added

### Helpers
none

### Branches or guards
none

### Mocks
none

### Tests
- `test_executor_prompt_keeps_verifier_and_tests_in_the_foreground` — A3: the rendered executor prompt's
  step 3 carries the foreground rule, the don't-end-the-turn rule, and the reason (headless turn ends on
  reply), so the rule cannot silently drop out of the preamble.
