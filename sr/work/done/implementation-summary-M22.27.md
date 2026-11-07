# Implementation summary: M22.27 — The old-log review usage test asserts on the run, not on a substring

Branch `feature/rm-old-log-test-asserts-on-the-run`, base `48f5c86ff2ead390c22a5fc88744ab12656ba4f7`.

## What changed

- `tests/test_review_usage.py::test_delegate_after_prompt_cli_does_not_append_to_the_old_log` records the
  prompt-cli `RUN-<model>.log` bytes before `review delegate`, then after delegate asserts the log no longer
  begins with that exact byte sequence. The old `"900" not in` check could fail when an unrelated part of the
  log (for example a commit hash) contained the substring `900` while the prompt-cli usage line was already gone.

## Acceptance

- **A1:** met. Usage totals unchanged (`input_tokens` 10, one turn). The log assert fails when the delegate run
  leaves the pre-delegate bytes as a prefix (append-to-old-log bug) and passes when delegate replaces the log.
  Test-only; no CHANGELOG entry.

## Touch zones (final)

- `tests/test_review_usage.py` — confirmed accurate; no other modules import this file at HEAD.

## Verification

- `pytest tests/test_review_usage.py -q`: 10 passed.

## Added

- none
