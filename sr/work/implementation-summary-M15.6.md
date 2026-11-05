# M15.6 implementation summary

The previous worker (`w-0026`) committed nothing; this round implements the leaf from the base.

## What changed

- **New `specy_road/rework_rca.py`.**
  - `governing_rca(root, node_id, blocks)` returns the accepted RCA, or `None`. Accepted means two things. The record is valid after `review_rca.loop_state`'s schema and semantic checks. For `defer_findings`, it is also applied (`DEFERRAL-<round>.yaml` exists). This is the same rule M12.1's next-step table uses for `NON_DEFER` / `DEFER_APPLIED`.
  - The latest accepted record by `trigger.round` is carried only when that round is at or after the round of the oldest carried blocking review. That is how A1's "newer than its oldest carried blocking review" is checked.
  - It raises `RcaNotCarried` in two cases:
    - an `RCA-*.md` file that cannot be read (front matter or schema errors) is at or after that round, so it may be the accepted record;
    - the accepted record's design (`recommended_action.instructions`) is blank.
  - `rca_lines(doc)` renders, in order:
    - a `### Governing design: RCA-<n>.md` heading;
    - the overruling sentence;
    - the design (the recommended action's type and instructions, plus "requires human approval" when set);
    - any proposed criterion;
    - the findings it labels `in_scope_must_fix`, as the required changes.
  - `filed(root, doc, review)` returns `filed before RCA-<n>.md` when the review's commit is in a round the RCA analysed, else `filed after`.
- **`specy_road/bundled_scripts/role_prompt_rework.py`.**
  - `rework_lines` puts the RCA block first under `## Rework` (A1). Each review heading gets `; filed before|after RCA-<n>.md`.
  - If the RCA cannot be carried, the prompt says so and names the file, rather than crashing `prompt`.
  - `rework_check` (`worker delegate --rework`) names the RCA path in its stderr note. When `RcaNotCarried` is raised, it refuses with a `WorkerError` that names the file (A2).
  - `_review_lines` gained an optional `rca` argument. Its other call site, `worker_ops_message.py` (outside the zones), is unchanged and its output is the same.
- With no RCA, the section is byte-for-byte what it was before this change (A3, `test_no_rca_gives_the_prompt_unchanged`).

Touch zones confirmed: `specy_road/bundled_scripts/role_prompt_rework.py`, `specy_road/rework_rca.py`, `tests/`. No change was needed outside them.

## Decisions

- **"Design section".** The RCA schema has no design field, and real records have no `## Design` heading. So the design is `recommended_action.instructions`, the required changes are `criterion_rewrite.finding_disposition` entries labelled `in_scope_must_fix`, and "no design section" means the instructions are blank.
- **"Unreadable"** means schema or parse errors (`list_rcas`). A record that is readable but fails only the semantic checks is not accepted under M12.1, so it is ignored, not refused.
- **Before/after** is decided by review round, not file mtime. A carried review whose commit is not in the review history counts as after every analysed round.
- **No blocking reviews means no RCA.** With only a stopped worker there is no "oldest carried blocking review", so no RCA is carried. This follows A1 literally.

## Probes

- `prompt --role executor` path: a broken RCA does not raise. It renders a "not carried" line naming the file (`test_an_unreadable_rca_refuses_rework`).
- RCA older than every carried review: not carried (`test_an_rca_older_than_every_carried_review_is_not_carried`).
- Unapplied `defer_findings` RCA: not treated as accepted (`test_an_unapplied_defer_findings_rca_is_not_accepted`).
- `worker message --fix-round` (`worker_ops_message.py`): it calls `_review_lines` without `rca`, so its output is unchanged. `tests/test_fix_round_class_audit.py` passes.
- Existing rework and next-step suites, then the full suite: `pytest -n 4` gave 4122 passed. In an earlier run, `test_worker_queue_message.py::test_message_while_running_queues_and_delivers` failed once under load. It passed alone and on the rerun.
- `specy-road file-limits`: OK. `ruff check` on the changed files: clean.

## Added

- `specy_road/rework_rca.py`: new module, so `role_prompt_rework.py` stays small. It holds the RCA selection and rendering.
- `RcaNotCarried`: the exception for an accepted RCA that cannot be rendered. The CLI turns it into a refusal and the prompt into a note.
- `RcaDoc`: the record plus the commits of the rounds it analysed, used for the before/after marks.
- `_key`, `_file_round`: commit normalisation (as in `review_rounds`) and the round number from an RCA file name, used to judge unreadable files.
- `governing_rca`, `filed`, `rca_lines`: A1/A2 selection, before/after mark, rendering.
- `_review_lines(..., rca=None)` branch: appends the before/after mark only when an RCA is carried.
- `rework_lines` try/except `RcaNotCarried`: the prompt names an RCA it could not carry instead of failing.
- `rework_check` RCA guard and note: A2.
- `tests/test_rework_rca.py`, 8 tests:
  - reported case: design X then RCA design Y, so Y and the overruling sentence come before X, and the stderr note names the RCA (A1, A2, A3);
  - a review filed after the RCA is marked "after";
  - criterion rewrite and in-scope findings are rendered as required changes;
  - with no RCA, the prompt is unchanged byte for byte (A3);
  - an RCA older than every carried review is not carried;
  - an unapplied `defer_findings` RCA is not accepted;
  - an unreadable RCA makes rework refuse (A2);
  - a blank design makes rework refuse (A2).
- Mocks: none.
