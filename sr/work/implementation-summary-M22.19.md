## Summary

M22.19: the review gate's inputs are now read cleanly.

- **A1 READY identity.** `review_eligible.Identity` applies one normalization to READY `agent` and review-record `model` values. It case-folds the name. An exact roster `id` wins. Otherwise a roster `harness_model`, or the pinned profile's `api_id`, file name or alias, maps to the roster `id`. `writers` and `reviews_to_judge` compare after it, and `reviewer_eligibility` and `review_delegate` (default, pinned roster) get it through `writers`. A name two or more entries answer to stays unmapped, and the gate gets a problem naming the entries (`evaluate_gate` adds it to `verifier_problems`, which closes the gate).
- **A2 acceptance presence.** `read_acceptance` does `lstat` inside `_unreadable_as`. Only `FileNotFoundError` means absent. A `PermissionError` on the parent, or any other `OSError`, is an invalid acceptance. A dangling link counts as present and is refused by `check_handoff_read`, which was already the behaviour after M21.38. The new case is a regression guard.
- **A2 worker record.** `worker_state.load_record` reads through a new `_read_regular`: `os.open` with `O_NONBLOCK`, then `fstat` must show a regular file, else `OSError`. That becomes a `WorkerError`, which `review_caller.caller` turns into `CallerError` straight away. `review_caller.py` is unchanged because the fix sits in the reader it calls.
- **A3 canonical names.** `write_rejected` and `write_human_approval` now write through `review_files.write_review`, so they share its case-variant unlink, which does not follow links. `unreadable_rejected_lines` matches `REJECTED-*.md` in any case. `review_gate_ready` no longer imports `safe_write` and `project_of`, which it no longer uses.
- **A7 non-UTF-8 READY.** `review_files._read` also catches `UnicodeDecodeError` (as `cannot read: …`). `writers` adds `<file> is unreadable (…); its author cannot be excluded` for such a READY, so the gate stays closed and finish and `handoff status` name the file. Without this, an unreadable executor READY would have let the executor's own approval count.
- Docs: `docs/orchestration-review.md` (READY identity paragraph, acceptance presence sentence, FIFO worker record). CHANGELOG `[Unreleased]` Fixed entry.

## Touch zones

Final list: the same as the brief. `specy_road/review_caller.py` and `tests/test_review_eligible.py` are unchanged; the fix and its test live in the other zoned files. Nothing outside the zones was changed.

## For the maintainer (sheet: "If this fails")

On the `sr/` roster, exact ids always resolve, because an exact id beats an alias. These shared aliases would now close the gate if a READY or record used them instead of a roster id:
- `claude-opus-5-5`: claude-opus-5-5-high, claude-opus-5-5-review, claude-opus-5.5
- `grok-4.7`: grok-4.7-exec, grok-4.7-high, grok-4.7-low
- `grok-4.7-high` as an alias: grok-4.7-exec and grok-4.7-high (the exact id `grok-4.7-high` still wins)
- `gpt-6.1-sol` as an alias: also gpt-6.1-sol-low (the exact id wins)
- `gpt-5.6-sol` and its effort variants (`-none`, `-low-fast`, `-xhigh`, `-max`, …): gpt-5.6-sol-high, -low, -medium

`specy-road ready --model` writes the roster id, so these only matter for a hand-written READY or record.

## Verification

- `python -m pytest -q -n 4` (whole suite): 6577 passed, 8 skipped.
- The new tests with the package files at HEAD: 11 failed (all except the dangling-link case, which M21.38 already covered).
- `specy-road file-limits`: OK. `ruff check`: clean.

## Added

- `specy_road/review_eligible.py` `Identity`: the single READY-author and record-model normalization (A1), which also collects ambiguity and unreadable-READY problems.
- `review_eligible.writers` optional `identity` parameter: so the gate and the eligibility rows reuse one `Identity` over the gate's config.
- `review_eligible.reviews_to_judge` optional `config` and `problems` parameters: the gate's roster, and where its authorship problems are returned.
- `review_eligible.writers` unreadable-READY branch: a READY whose author cannot be read closes the gate (A7).
- `review_gate.evaluate_gate` `authorship` list, prepended to `verifier_problems`: the ambiguous or unreadable authorship problems close the gate (A1, A7).
- `review_policy_pin.read_acceptance` `lstat` / `FileNotFoundError` branch inside `_unreadable_as`: presence is checked inside the boundary (A2).
- `worker_state._read_regular`: a non-blocking open plus an `fstat` regular-file guard for worker records (A2).
- `review_files._read` `UnicodeDecodeError` catch: a non-UTF-8 READY or record is unreadable rather than a traceback (A7).
- `review_rejected.unreadable_rejected_lines` case-insensitive filter: replaces the case-sensitive glob (A3).
- Mock: `tests/test_review_policy_pin.py` `_plant_acceptance` stubs `Path.stat` / `Path.lstat` to raise `PermissionError` for `POLICY-ACCEPTED.yaml` only, which simulates an unreadable parent (A4).
- Test: `test_review_policy_pin.py` two new rows (`dangling link`, `unreadable parent`) in the existing unreadable-input table (A2, A4).
- Test: `test_review_gate_ready_author.py::test_ready_author_and_record_model_are_compared_after_case_folding_and_roster_aliases`, with four rows: a case variant and an alias, each on the READY side and on the record side; another model still counts (A1, A4).
- Test: `test_review_gate_ready_author.py::test_a_ready_author_two_roster_entries_answer_to_closes_the_gate` (A1, A4).
- Test: `test_review_record_caller.py::test_a_fifo_worker_record_is_refused_at_once`: the CLI is a subprocess with a 5 s timeout, the FIFO has no writer, and nothing is written (A2, A4).
- Test: `test_review_file_case.py::test_rejected_marker_and_human_approval_replace_a_case_variant`, with two rows: canonical names, found by `rejected_state` and `list_reviews` (A3, A4).
- Test: `test_review_file_case.py::test_an_unreadable_rejected_marker_is_listed_whatever_its_case` (A3).
- Test: `test_review_file_case.py::test_a_ready_that_is_not_utf8_is_refused_naming_the_file`, covering the gate, `handoff status`, `mark-implementation-reviewed` and `finish-this-task` (A7).
