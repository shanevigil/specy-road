## Summary

M22.19: the review gate's inputs are now read cleanly.

- **A1 READY identity.** `review_eligible.Identity` applies one rule to READY `agent` and review-record `model` values. A name stands for the set of every roster entry whose `id`, `harness_model`, or pinned profile `api_id`, file name or alias equals it, case-folded. Exact ids and aliases are pooled: since fix round 1, an exact id has no precedence. A READY author is keyed under every entry it may be. A record is excluded when its set meets an author's. A READY name with more than one entry is always a gate problem. A record name with more than one entry is a gate problem when it meets an author. `evaluate_gate` adds the problem to `verifier_problems`, which closes the gate. `reviewer_eligibility` and `review_delegate` get the rule through `writers`.
- **A2 acceptance presence.** `read_acceptance` does `lstat` inside `_unreadable_as`. Only `FileNotFoundError` means absent. A `PermissionError` on the parent, or any other `OSError`, is an invalid acceptance. A dangling link counts as present and is refused by `check_handoff_read`, which was already the behaviour after M21.38. The new case is a regression guard.
- **A2 worker record.** `worker_state.load_record` reads through a new `_read_regular`: `os.open` with `O_NONBLOCK`, then `fstat` must show a regular file, else `OSError`. That becomes a `WorkerError`, which `review_caller.caller` turns into `CallerError` straight away. `review_caller.py` is unchanged because the fix sits in the reader it calls.
- **A3 canonical names.** `write_rejected` and `write_human_approval` now write through `review_files.write_review`, so they share its case-variant unlink, which does not follow links. `unreadable_rejected_lines` matches `REJECTED-*.md` in any case. `review_gate_ready` no longer imports `safe_write` and `project_of`, which it no longer uses.
- **A7 non-UTF-8 READY.** `review_files._read` also catches `UnicodeDecodeError` (as `cannot read: …`). `writers` adds `<file> is unreadable (…); its author cannot be excluded` for such a READY, so the gate stays closed and finish and `handoff status` name the file. Without this, an unreadable executor READY would have let the executor's own approval count.
- Docs: `docs/orchestration-review.md` (READY identity paragraph, acceptance presence sentence, FIFO worker record). CHANGELOG `[Unreleased]` Fixed entry.

## Touch zones

Final list: the same as the brief. `specy_road/review_caller.py` and `tests/test_review_eligible.py` are unchanged; the fix and its test live in the other zoned files. Nothing outside the zones was changed.

## Fix round 1 (gpt-6.1-sol P1)

Class: a name that is one entry's exact id and another entry's alias. The first version let the exact id win and hid the collision, on both the READY side and the record side. The fix removes precedence entirely: `Identity` keeps one name -> entries map, and every comparison works on sets, so no lookup order can hide an alias. The bounded rule is stated in the `Identity` docstring and in `docs/orchestration-review.md`. Its limit: entries that share a name cannot be told apart, so the gate stays closed for such a READY until the roster names differ.

## Probes

- READY names an id that is another entry's `harness_model` (COLLIDE roster, READY `opus`): gate closed, problem names opus and sonnet. Before the fix it passed.
- Record side (READY `sonnet`, record `opus`, where opus is sonnet's alias): record excluded, gate closed with the problem. Before the fix the record counted.
- Record whose name collides but meets no READY author (READY `astra`): judged by its exact id, gate passes, no problem.
- Alias shared by two entries (SHARED roster, READY `claude-opus-x`): gate closed.
- Case variant and single alias on the READY side and on the record side (4 rows): executor excluded, other models still count.
- `writers` callers: `reviewer_eligibility` and `review_delegate` look up by roster id in the dict now keyed by every candidate entry, so an ambiguous author is excluded under each entry.
- `writers` fix-vs-executor timing (`first`): keyed by each candidate entry of a record's model, so the timing comparison sees the same sets.
- Other comparisons of record models against READY authors (`_rejected`, `_count`, `prior_approvals`): none compare against READY authors; they use the record's exact model, as the gate always has.
- Pinned `sr/` roster under the new rule: the colliding names are listed below.
- After merging origin/WIP/improvements-0-3-1: `ruff check specy_road tests scripts` clean; `specy-road file-limits` OK; full suite `python -m pytest -q -n 4`: 6815 passed, 8 skipped. That includes `tests/parity/`, so no golden transcript changed (A6).

## For the maintainer (sheet: "If this fails")

With no exact-id precedence, these exact roster ids on the `sr/` roster are now ambiguous, because another entry answers to them through its `harness_model` or profile alias: `gpt-6.1-sol` (with gpt-6.1-sol-low), `grok-4.7-high` (with grok-4.7-exec and grok-4.7-low), and `gpt-5.6-sol-high`, `-low` and `-medium` (with each other). A READY that `specy-road ready --model <one of these>` writes keeps that leaf's gate closed. Decide whether harness names and profile aliases stop counting as aliases, or rename the roster entries. The shared-alias groups are:
- `claude-opus-5-5`: claude-opus-5-5-high, claude-opus-5-5-review, claude-opus-5.5 (no exact id collides)
- `grok-4.7`, `grok-4.7-high`: grok-4.7-exec, grok-4.7-high (and grok-4.7-low for `grok-4.7`)
- `gpt-6.1-sol`: gpt-6.1-sol, gpt-6.1-sol-low
- `gpt-5.6-sol` and every effort variant: gpt-5.6-sol-high, -low, -medium

## Verification

- `python -m pytest -q -n 4` (whole suite): 6577 passed, 8 skipped in round 0; 6815 passed, 8 skipped after fix round 1 and the merge.
- The new tests with the package files at HEAD: 11 failed (all except the dangling-link case, which M21.38 already covered).
- `specy-road file-limits`: OK. `ruff check`: clean.

## Added

- `specy_road/review_eligible.py` `Identity`: the single READY-author and record-model rule (A1), returning each name's set of candidate entries. It also collects ambiguity and unreadable-READY problems.
- `Identity.ambiguous`: the one place an ambiguity problem is added, called for every READY author and for a record that meets an author (fix round 1).
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
- Test: `test_review_gate_ready_author.py::test_a_name_two_roster_entries_answer_to_closes_the_gate`, with four rows: a shared alias, an exact id that is another entry's alias (READY side), the same on the record side, and a colliding record that meets no author (A1, A4, fix round 1; replaces the round-0 single-case test).
- Test: `test_review_record_caller.py::test_a_fifo_worker_record_is_refused_at_once`: the CLI is a subprocess with a 5 s timeout, the FIFO has no writer, and nothing is written (A2, A4).
- Test: `test_review_file_case.py::test_rejected_marker_and_human_approval_replace_a_case_variant`, with two rows: canonical names, found by `rejected_state` and `list_reviews` (A3, A4).
- Test: `test_review_file_case.py::test_an_unreadable_rejected_marker_is_listed_whatever_its_case` (A3).
- Test: `test_review_file_case.py::test_a_ready_that_is_not_utf8_is_refused_naming_the_file`, covering the gate, `handoff status`, `mark-implementation-reviewed` and `finish-this-task` (A7).
