# Implementation summary: M15.18

`planned_test_changes` can now be edited after pickup. Any removed or weakened test it doesn't list becomes a required reviewer check, whether `policy.integrity_gate` is on or off.

## Acceptance

- **A1:** `edit-node` accepts `planned_test_changes` with `--set` (one per item; an empty value removes the field), `--add` and `--remove`, like the other list fields. Each item is checked against the field's item shape in `templates/project/schemas/roadmap.schema.json`. `add-node` takes a repeatable `--planned-test-change`. A test edits the field on a claimed leaf (`make_review_repo`'s M1.1), and `validate_roadmap.py` then exits 0.
- **A2:**
  - `integrity_removals.py` checks the `removed-test`, `removed-test-file`, `new-skip` and `assert-loss` findings against `planned_test_changes`. It reads the list from both the integration branch and the node as committed at the reviewed commit.
  - When any finding is unlisted, `review-packet` adds `## Required check: unplanned test removal` after `## Test integrity`. The section lists each line plus paste-ready acceptance entries.
  - The reviewer prompt (`role_prompt_rca.py`) requires one acceptance entry per line, keyed by the line exactly, whatever `policy.integrity_gate` says.
  - `review record` refuses an approve that omits any of these entries and names the test (`review_record_rules.unplanned_removal_problem`).
  - Tests cover an unlisted removal (heading present; approve refused, then filed once the entry is added), a removal listed on the leaf branch (no heading; approve filed without the entry), and one listed on the integration branch (no heading).
- **A3:** the new `docs/acceptance-evidence.md` explains how to authorize a test change after pickup: run `edit-node` on the integration branch (the only place the gate reads), or on the leaf branch, where the edit is reviewed with the diff. `integrity.py` is unchanged (395 lines) and `roadmap_edit_fields.py` is 391. `review_packet.py` went from 400 to 392: the heading comes from `review_packet_observed.py`, and `test_integrity_section` and `_computed` moved there and are re-imported. `integrity_gate` still defaults to off.

## Decisions

- **Record schema** (`specy_road/schemas/review-record.schema.json`): `acceptance` keys may now be `A#` or one of the four removal-line forms. Removal keys accept only `pass`, because a `fail` there would crash `review_rca._id_key` (`int(aid[1:])`), and an unjustified removal should be a block with a `required_changes` entry. A block needs no entry.
- **`review_files.review_semantic_errors`:** a key containing `:` (a removal key) no longer counts as "not in the brief". I edited it in place to keep the file at its 400-line cap.
- **Milestone targets** get no required check, because the diff spans many leaves.
- **Plan sources:** the cross-check reads the plan from the integration branch and from the reviewed commit, so an edit made on the leaf branch counts for this check. `integrity_gate` itself is unchanged and still reads only the integration branch.

## Final touch zones

These are the zones as widened by the coordinator, all used: `roadmap_edit_fields.py`, `roadmap_edit_list_fields.py` (new), `roadmap_crud_argparse.py`, `roadmap_crud_ops.py`, `integrity_removals.py` (new), `review_packet.py`, `review_packet_observed.py` (new), `review_record_rules.py`, `review_files.py`, `schemas/review-record.schema.json`, `role_prompt_rca.py`, `docs/acceptance-evidence.md` (new), `tests/`. `integrity.py` didn't need changes.

## Added

- **New functions:**
  - `roadmap_edit_list_fields.planned_test_change_items`: strips items, drops blanks and validates each against the schema's item shape (shared by `edit-node` and `add-node`).
  - `roadmap_edit_list_fields.set_planned_test_changes`: the `--set` handler; an empty value removes the field.
  - `roadmap_edit_list_fields._item_validator` (cached): the item validator built from the packaged roadmap schema.
  - `integrity_removals.unplanned_removals`: keeps the removal and weakening lines a plan doesn't list.
  - `integrity_removals.planned_for_target`: the plan from the integration branch and the reviewed commit, combined.
  - `integrity_removals.target_unplanned_removals`: what `review record` checks; returns nothing for a milestone or when a commit is missing.
  - `integrity_removals.missing_removal_entries`: the removal lines a record's `acceptance` has no entry for.
  - `review_packet_observed.integrity_sections`: the integrity block plus the required check, computing integrity only once.
  - `review_packet_observed.unplanned_removal_lines`: renders the heading section.
  - `review_packet_observed._findings`, `_integrity_block`: the helpers they share.
  - `review_record_rules.unplanned_removal_problem`: refuses an approve that omits an entry and names each line.
- **Edits to existing code:**
  - `roadmap_edit_fields.apply_set`: routes `planned_test_changes` to its own handler; the field was also added to `EDIT_WHITELIST` and `LIST_KEYS`.
  - `roadmap_crud_argparse`: `--planned-test-change` on `add-node`; the list-field help text for `edit-node` now names the field.
  - `roadmap_crud_ops.cmd_add`: one field-list entry that stores the new flag's values.
  - Schema: a `patternProperties` entry (`const: pass`) and a wider `propertyNames` pattern for removal keys.
- **Tests:** 11 new tests in `tests/test_planned_test_changes.py`, covering edit-node set/add/remove plus validate on a claimed leaf; add-node with and without the flag plus validate; item stripping; which lines count as unplanned; the packet's heading for an unlisted removal and its absence for one listed on the leaf branch or the integration branch; record refusal, then filing with the entry; a block filed without the entry and a `fail` entry refused; an approve filed when the removal is planned; the reviewer prompt text.
- **Mocks:** none.
