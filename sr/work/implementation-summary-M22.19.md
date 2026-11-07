## Summary

M22.19: the review gate's inputs are now read cleanly.

- **A1 READY identity.** `review_eligible.Identity` applies one rule to READY `agent` and review-record `model` values. A name stands for the set of every roster entry whose `id`, `harness_model`, or pinned profile `api_id`, file name or alias equals it, case-folded. Exact ids and aliases are pooled: since fix round 1, an exact id has no precedence. A READY author is keyed under every entry it may be. A record is excluded when its set meets an author's. Any READY or record name with more than one entry is a gate problem (since fix round 2, records too, whether or not they meet an author). An entry's names come from its roster `id` and `harness_model` and its pinned profile's declared `api_id`, file name and aliases. An entry whose pinned profile is refused is a gate problem, because its names cannot be known (fix round 2). `evaluate_gate` adds the problem to `verifier_problems`, which closes the gate. `reviewer_eligibility` and `review_delegate` get the rule through `writers`.
- **A2 acceptance presence.** `read_acceptance` does `lstat` inside `_unreadable_as`. Only `FileNotFoundError` means absent. A `PermissionError` on the parent, or any other `OSError`, is an invalid acceptance. A dangling link counts as present and is refused by `check_handoff_read`, which was already the behaviour after M21.38. The new case is a regression guard.
- **A2 worker record.** `worker_state.load_record` reads through a new `_read_regular`: `os.open` with `O_NONBLOCK`, then `fstat` must show a regular file, else `OSError`. That becomes a `WorkerError`, which `review_caller.caller` turns into `CallerError` straight away. `review_caller.py` is unchanged because the fix sits in the reader it calls.
- **A3 canonical names.** `write_rejected` and `write_human_approval` now write through `review_files.write_review`, so they share its case-variant unlink, which does not follow links. `unreadable_rejected_lines` matches `REJECTED-*.md` in any case. `review_gate_ready` no longer imports `safe_write` and `project_of`, which it no longer uses.
- **A7 non-UTF-8 READY.** `review_files._read` also catches `UnicodeDecodeError` (as `cannot read: …`). `writers` adds `<file> is unreadable (…); its author cannot be excluded` for such a READY, so the gate stays closed and finish and `handoff status` name the file. Without this, an unreadable executor READY would have let the executor's own approval count.
- Docs: `docs/orchestration-review.md` (READY identity paragraph, acceptance presence sentence, FIFO worker record). CHANGELOG `[Unreleased]` Fixed entry.

## Touch zones

Final list: the same as the brief. `specy_road/review_caller.py` and `tests/test_review_eligible.py` are unchanged; the fix and its test live in the other zoned files. Nothing outside the zones was changed.

## Fix round 1 (gpt-6.1-sol P1)

Class: a name that is one entry's exact id and another entry's alias. The first version let the exact id win and hid the collision, on both the READY side and the record side. The fix removes precedence entirely: `Identity` keeps one name -> entries map, and every comparison works on sets, so no lookup order can hide an alias. The bounded rule is stated in the `Identity` docstring and in `docs/orchestration-review.md`. Its limit: entries that share a name cannot be told apart, so the gate stays closed for such a READY until the roster names differ.

## Fix round 2 (gpt-6.1-sol: two P1, one P2)

Class: the sources of an entry's names, and what happens when one is missing. Three shapes were reported:
- P1: `Profile.api_id` returns the matched alias, which hid the declared `api_id`.
- P1: a refused (drifted) profile silently contributed no names.
- P2: a record name's ambiguity was checked only when it met an author.

This keeps reappearing as new input shapes, so the `Identity` docstring now states one bounded rule:
- The names are fixed: roster `id` and `harness_model`, plus the pinned profile's front matter `api_id`, file name and `aliases`. The declared `api_id` is now read from the front matter directly.
- Names that cannot be known close the gate: a refused profile is a gate problem naming the entry and the refusal.
- Any READY or record name with two or more entries closes the gate.

Its limit is the one A1 implies: entries that share a name cannot be told apart. Each clause has a test row. The round-1 `astra` row, which asserted the gate passes, now asserts it closes, as the review required. `reviews_to_judge` calls `ambiguous` for every record before the author check.

## Probes

Round 2:
- READY names the profile's declared `api_id` (`vendor-model`) when the file name (`custom-model`) and the matched alias (`opus`) differ: executor excluded, sonnet and sol still count. On the round-1 code it failed (opus counted).
- Record names the profile file name (`custom-model`): executor excluded. It already passed on round 1, because the stem was included.
- Working-tree copy of the pinned profile differs (dispatch refuses it): gate closed, with problem `roster entry 'opus': its profile's names cannot be known (...)`. On the round-1 code the gate passed.
- A colliding record name (`opus` is also sonnet's `harness_model`) with READY `astra`: gate closed with the problem. On the round-1 code the gate passed.
- Other readers of profile names in this change: only `Identity.__init__` reads them, and it no longer uses `Profile.api_id`.
- A profile that is absent (`None`, no profile pinned): the entry contributes only its `id` and `harness_model`, and no problem is raised. That is not a refusal.
- `review_delegate` and `reviewer_eligibility` build their own `Identity`. They key authors under every candidate entry, but ignore its problems; the gate reports them.
- Pinned `sr/` roster: no refused profiles today, so no new problems. The ambiguous exact ids are unchanged; see the maintainer section, which is now broader.
- After merging origin/WIP/improvements-0-3-1: `ruff check specy_road tests scripts` clean; `specy-road file-limits` OK; full suite `python -m pytest -q -n 4`: 6834 passed, 8 skipped (including `tests/parity/`).

Round 1:

- READY names an id that is another entry's `harness_model` (COLLIDE roster, READY `opus`): gate closed, problem names opus and sonnet. Before the fix it passed.
- Record side (READY `sonnet`, record `opus`, where opus is sonnet's alias): record excluded, gate closed with the problem. Before the fix the record counted.
- Record whose name collides but meets no READY author (READY `astra`): judged by its exact id, gate passes, no problem. Changed in round 2: now gate closed.
- Alias shared by two entries (SHARED roster, READY `claude-opus-x`): gate closed.
- Case variant and single alias on the READY side and on the record side (4 rows): executor excluded, other models still count.
- `writers` callers: `reviewer_eligibility` and `review_delegate` look up by roster id in the dict now keyed by every candidate entry, so an ambiguous author is excluded under each entry.
- `writers` fix-vs-executor timing (`first`): keyed by each candidate entry of a record's model, so the timing comparison sees the same sets.
- Other comparisons of record models against READY authors (`_rejected`, `_count`, `prior_approvals`): none compare against READY authors; they use the record's exact model, as the gate always has.
- Pinned `sr/` roster under the new rule: the colliding names are listed below.
- After merging origin/WIP/improvements-0-3-1: `ruff check specy_road tests scripts` clean; `specy-road file-limits` OK; full suite `python -m pytest -q -n 4`: 6815 passed, 8 skipped. That includes `tests/parity/`, so no golden transcript changed (A6).

## For the maintainer (sheet: "If this fails")

With no exact-id precedence, these exact roster ids on the `sr/` roster are now ambiguous, because another entry answers to them through its `harness_model` or profile alias: `gpt-6.1-sol` (with gpt-6.1-sol-low), `grok-4.7-high` (with grok-4.7-exec and grok-4.7-low), and `gpt-5.6-sol-high`, `-low` and `-medium` (with each other). A READY that `specy-road ready --model <one of these>` writes keeps that leaf's gate closed. Since fix round 2, **a review record filed under one of these ids also keeps the gate closed**, on any leaf. In practice, `gpt-6.1-sol` (a main reviewer here) cannot supply a counting review until `gpt-6.1-sol-low` stops sharing its `harness_model` / profile `api_id`. The same applies to `grok-4.7-high` and `gpt-5.6-sol-*`. A1's literal rule requires this; the impact needs a maintainer decision before this lands. Decide whether harness names and profile aliases stop counting as aliases, or rename the roster entries. The shared-alias groups are:
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
- `Identity.ambiguous`: the one place an ambiguity problem is added, called for every READY author and every record (fix rounds 1 and 2).
- `Identity.__init__` refused-profile problem: an entry whose pinned profile is refused closes the gate, because its names cannot be known (fix round 2).
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
- Test: `test_review_gate_ready_author.py::test_ready_author_and_record_model_are_compared_after_case_folding_and_roster_aliases`, with six rows: a case variant and a `harness_model`, each on the READY side and on the record side, plus the profile's declared `api_id` and its file name (round 2); another model still counts (A1, A4).
- Test helper: `_profiled_repo` commits a custom profile (file name, `api_id` and alias all different) on the integration branch only (round 2).
- Test: `test_review_gate_ready_author.py::test_authorship_that_cannot_be_decided_closes_the_gate`, with five rows, one per clause: a shared alias; an exact id that is another entry's alias on the READY side; the same on the record side; a colliding record with any author; a refused profile (A1, A4; renamed in round 2 from `test_a_name_two_roster_entries_answer_to_closes_the_gate`).
- Test: `test_review_record_caller.py::test_a_fifo_worker_record_is_refused_at_once`: the CLI is a subprocess with a 5 s timeout, the FIFO has no writer, and nothing is written (A2, A4).
- Test: `test_review_file_case.py::test_rejected_marker_and_human_approval_replace_a_case_variant`, with two rows: canonical names, found by `rejected_state` and `list_reviews` (A3, A4).
- Test: `test_review_file_case.py::test_an_unreadable_rejected_marker_is_listed_whatever_its_case` (A3).
- Test: `test_review_file_case.py::test_a_ready_that_is_not_utf8_is_refused_naming_the_file`, covering the gate, `handoff status`, `mark-implementation-reviewed` and `finish-this-task` (A7).
