# M15.6 implementation summary

The previous worker (`w-0026`) committed nothing; round 0 implemented the leaf from the base. Fix round 1 merged `origin/WIP/improvements-0-3-1` (clean) and addressed `gpt-6.1-sol`'s R1–R3.

## What changed

- **New `specy_road/rework_rca.py`.**
  - `governing_rca(root, node_id, blocks)` returns the accepted RCA, or `None`. Accepted means two things. The record is valid after `review_rca.loop_state`'s schema and semantic checks. For `defer_findings`, it is also applied (`DEFERRAL-<round>.yaml` exists). This is the same rule M12.1's next-step table uses for `NON_DEFER` / `DEFER_APPLIED`.
  - The latest accepted record by filing time is carried only when it was filed after the oldest carried blocking review. That is how A1's "newer than its oldest carried blocking review" is checked (fix round 1, R1: filing provenance, not rounds).
  - It raises `RcaNotCarried` in three cases:
    - a record file it reads is not valid UTF-8 (`check_inputs`, see below);
    - with blocking reviews to carry, any `RCA-*.md` has front matter or schema errors, so it may be the accepted record;
    - the accepted record's design (`recommended_action.instructions`) is blank.
  - `check_inputs(root, node_id)` (fix round 1, R2) reads every `RCA-*.md`, `READY-*.md`, `REVIEW-*.md` and `history/*.md` under the leaf's reviews directory as bytes and decodes it as UTF-8 before any loader runs. On failure it names the path and the fix.
  - `rca_lines(doc)` renders, in order:
    - a `### Governing design: RCA-<n>.md` heading;
    - the overruling sentence;
    - the design (the recommended action's type and instructions, plus "requires human approval" when set);
    - any proposed criterion;
    - the findings it labels `in_scope_must_fix`, as the required changes.
  - `filed(doc, review)` returns `filed before RCA-<n>.md` when the review file was written before the RCA file (mtime, nanoseconds), else `filed after`.
- **`specy_road/bundled_scripts/role_prompt_rework.py`.**
  - `rework_lines` runs `check_inputs` first; an undecodable record file gives a short `## Rework` section that names it. It then puts the RCA block first under `## Rework` (A1). Each review heading gets `; filed before|after RCA-<n>.md`.
  - If the RCA cannot be carried, the prompt says so and names the file, rather than crashing `prompt`.
  - `rework_check` (`worker delegate --rework`) runs `check_inputs` before loading anything and refuses on failure. It names the RCA path in its stderr note. When `RcaNotCarried` is raised, it refuses with a `WorkerError` that names the file (A2).
  - `_review_lines` gained an optional `rca` argument. Its other call site, `worker_ops_message.py` (outside the zones), is unchanged and its output is the same.
- With no RCA, the section is byte-for-byte what it was before this change (A3, `test_no_rca_gives_the_prompt_unchanged`).

Touch zones confirmed: `specy_road/bundled_scripts/role_prompt_rework.py`, `specy_road/rework_rca.py`, `tests/`. No change was needed outside them.

## Decisions

- **"Design section".** The RCA schema has no design field, and real records have no `## Design` heading. So the design is `recommended_action.instructions`, the required changes are `criterion_rewrite.finding_disposition` entries labelled `in_scope_must_fix`, and "no design section" means the instructions are blank.
- **"Unreadable"** means schema or parse errors (`list_rcas`). A record that is readable but fails only the semantic checks is not accepted under M12.1, so it is ignored, not refused.
- **Before/after** (changed in fix round 1, R1) is filing provenance: the file modification time `review record` sets on `REVIEW-<model>.md` and the analyst sets on `RCA-<n>.md`, compared in nanoseconds. A review written before the RCA is "before". A tie or later write is "after". Which commit the review names does not matter. A second reviewer filing at an analysed commit after the RCA is "after".
- **Unreadable RCA** (fix round 1): any schema-broken `RCA-*.md` refuses once there are blocking reviews to carry. The old round-number gate came from the file name, so it went with the R1 change. With nothing to rework, a broken RCA does not add a `## Rework` section.
- **No blocking reviews means no RCA.** With only a stopped worker there is no "oldest carried blocking review", so no RCA is carried. This follows A1 literally.

## Fix round 1: inputs

Every input this leaf reads, and how it is validated at load:

- `RCA-*.md`: bytes decoded as UTF-8 in `check_inputs` (refuses, naming the path). Front matter and schema are checked by `list_rcas` (refuses when blocks exist). Semantic checks run in `loop_state`: a semantically invalid record is not accepted and is ignored. Filing time is the file's mtime.
- `REVIEW-*.md` (any prefix case): decoded in `check_inputs`. Schema and semantics are checked by `list_reviews`/`load_review`; `blocking_reviews` keeps only `ok` records for this node whose verdict is `block`. Filing time is the live file's mtime (`on_disk` when the case differs).
- `history/*.md`: decoded in `check_inputs`. `load_review` checks them, and `review_rounds` keeps only `ok` records for this node. They are used only by `loop_state`'s semantic RCA checks.
- `READY-*.md`: decoded in `check_inputs`. `load_ready` checks them, and `rca_parties` keeps only `ok` ones. They are read only inside `loop_state`.
- `DEFERRAL-<round>.yaml`: this leaf reads only whether it exists (`marker_path(...).exists()`). `loop_state` → `load_markers` reads its content and already catches `OSError`, `UnicodeDecodeError` and `YAMLError`, reporting the file as a marker problem.
- Decisions (`roadmap/decisions.yaml`): not read by this leaf.
- Worker records and events (`stopped_worker`, `last_final_message`): read through `worker_state`, unchanged from M11.68 and outside this leaf's inputs.
- Orchestration config and policy: read by `loop_state` through `effective_config`, which validates them. Not changed here.

## Probes

- R1 class (before/after from something other than filing time): both uses, the per-review mark (`filed`) and the "newer than the oldest carried review" gate (`governing_rca`), now use `filed_at`. The round-number gate for unreadable RCAs was also removed. Tests: `test_a_second_reviewer_at_an_analysed_commit_after_the_rca_is_marked_after` (it fails on a46181ca), `test_a_review_filed_after_the_rca_is_marked_after`, `test_an_rca_older_than_every_carried_review_is_not_carried`. All tests set mtimes with `os.utime`, so order never depends on clock resolution.
- R2 class (record bytes that are not UTF-8, reaching a text loader that names no path): every file the rework section or `loop_state` reads with `review_files._read` is now decoded first: RCA, REVIEW, history, READY. Tests: the CLI regression `test_rca_with_invalid_utf8_refuses_delegate_rework_through_the_cli` (exit 1, path named, no prompt written; it fails on a46181ca with `UnicodeDecodeError`), and `test_any_undecodable_record_file_the_rework_reads_is_named` for REVIEW, READY and history files.
- R2 class, outside the zones: `review_files._read` catches only `OSError`, so `handoff status`, `review` commands and `worker message --fix-round` (`worker_ops_message.py` → `blocking_reviews`) still raise `UnicodeDecodeError` on such a file. The design fix that removes the class is to catch `UnicodeDecodeError` in `review_files._read`. That file is outside this leaf's zones, so I left it unchanged and it needs a follow-up.
- R3 class (private test-module names): `tests/test_rework_rca.py` now imports only public names: `tests/rework_rca_helpers.py`, `review_repo_helpers`, `worker_repo_helpers` and `test_worker_cli.run_worker_cli`. `grep "import _"` on the file: none.
- A broken RCA with nothing to rework: no `## Rework` section is added (`test_a_schema_broken_rca_with_nothing_to_carry_leaves_the_prompt_alone`).
- `prompt --role executor` path: a broken RCA does not raise. It renders a "not carried" line naming the file (`test_an_unreadable_rca_refuses_rework`).
- RCA older than every carried review: not carried (`test_an_rca_older_than_every_carried_review_is_not_carried`).
- Unapplied `defer_findings` RCA: not treated as accepted (`test_an_unapplied_defer_findings_rca_is_not_accepted`).
- `worker message --fix-round` (`worker_ops_message.py`): it calls `_review_lines` without `rca`, so its output is unchanged. `tests/test_fix_round_class_audit.py` passes.
- Round 0: full suite `pytest -n 4`, 4122 passed. Fix round 1: targeted suites only (as instructed), 83 passed.
- `specy-road file-limits`: OK. `ruff check` on the changed files: clean.

## Added

- `specy_road/rework_rca.py`: new module, so `role_prompt_rework.py` stays small. It holds the RCA selection and rendering.
- `RcaNotCarried`: the exception for an accepted RCA that cannot be rendered. The CLI turns it into a refusal and the prompt into a note.
- `RcaDoc`: the accepted record (fix round 1: the round-commit set was removed).
- `filed_at`: a record's filing time (file mtime in ns); R1.
- `_record_files`, `check_inputs`: the R2 boundary decode over every record file the rework reads.
- `governing_rca`, `filed`, `rca_lines`: A1/A2 selection, before/after mark, rendering.
- `_review_lines(..., rca=None)` branch: appends the before/after mark only when an RCA is carried.
- `rework_lines` try/except `RcaNotCarried`: the prompt names an RCA it could not carry instead of failing.
- `rework_check` RCA guard and note: A2. `rework_check` and `rework_lines` also call `check_inputs` first (R2).
- `tests/rework_rca_helpers.py` (R3): public `ROSTER` (adds `sonnet`), `run_review_cli`, `rca_record`, `write_rca`, `file_after` (sets filing order explicitly).
- `tests/test_rework_rca.py`, 14 tests:
  - reported case: design X then RCA design Y, so Y and the overruling sentence come before X, and the stderr note names the RCA (A1, A2, A3);
  - a review filed after the RCA is marked "after";
  - criterion rewrite and in-scope findings are rendered as required changes;
  - with no RCA, the prompt is unchanged byte for byte (A3);
  - an RCA older than every carried review is not carried;
  - an unapplied `defer_findings` RCA is not accepted;
  - an unreadable RCA makes rework refuse (A2);
  - a blank design makes rework refuse (A2);
  - R1: a second reviewer at an analysed commit, filed after the RCA, is marked "after";
  - R2: invalid UTF-8 in `RCA-1.md` makes `worker delegate --rework` refuse through the CLI, naming the path;
  - R2 class: undecodable REVIEW, READY and history files are named (3 parametrised cases);
  - a schema-broken RCA with nothing to rework adds no section.
- Mocks: none.
