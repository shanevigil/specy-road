# Implementation summary: M15.18

`planned_test_changes` can now be edited after pickup. Any removed or weakened test it doesn't list becomes a required reviewer check, whether `policy.integrity_gate` is on or off.

## Acceptance

- **A1:** `edit-node` accepts `planned_test_changes` with `--set` (one per item; an empty value removes the field), `--add` and `--remove`, like the other list fields. Each item is checked against the field's item shape in `templates/project/schemas/roadmap.schema.json`. `add-node` takes a repeatable `--planned-test-change`. A test edits the field on a claimed leaf (`make_review_repo`'s M1.1), and `validate_roadmap.py` then exits 0.
- **A2:**
  - `integrity_removals.py` checks the `removed-test`, `removed-test-file`, `new-skip` and `assert-loss` findings against `planned_test_changes`. It reads the list from both the integration branch and the node as committed at the reviewed commit. The integration branch is resolved from the git workflow config, never from the packet's diff base. The check applies to leaf and milestone targets alike; a milestone's plan also includes its leaves' lists.
  - When any finding is unlisted, `review-packet` adds `## Required check: unplanned test removal` after `## Test integrity`. The section lists each line plus paste-ready acceptance entries.
  - The reviewer prompt (`role_prompt_rca.py`) requires one acceptance entry per line, keyed by the line exactly, whatever `policy.integrity_gate` says.
  - `review record` refuses an approve that omits any of these entries and names the test (`review_record_rules.unplanned_removal_problem`).
  - Tests cover an unlisted removal (heading present; approve refused, then filed once the entry is added), a removal listed on the leaf branch (no heading; approve filed without the entry), one listed on the integration branch (no heading), one listed on the integration branch after an explicit `--base` (no heading, and the record agrees), and a milestone's unplanned removal (heading; `review record M2` refuses, then files with the entry) and its leaf-planned removal (no heading; filed).
- **A3:** the new `docs/acceptance-evidence.md` explains how to authorize a test change after pickup: run `edit-node` on the integration branch (the only place the gate reads), or on the leaf branch, where the edit is reviewed with the diff. `integrity.py` is unchanged (395 lines) and `roadmap_edit_fields.py` is 391. `review_packet.py` went from 400 to 392: the heading comes from `review_packet_observed.py`, and `test_integrity_section` and `_computed` moved there and are re-imported. `integrity_gate` still defaults to off.

## Decisions

- **Record schema** (`specy_road/schemas/review-record.schema.json`): `acceptance` keys may now be `A#` or one of the four removal-line forms. Removal keys accept only `pass`, because a `fail` there would crash `review_rca._id_key` (`int(aid[1:])`), and an unjustified removal should be a block with a `required_changes` entry. A block needs no entry.
- **`review_files.review_semantic_errors`:** a key containing `:` (a removal key) no longer counts as "not in the brief". I edited the comment in place, keeping its original wording ("and still named in the summary"), so the file stays at its 400-line cap.
- **Milestone targets** get the same required check as leaves (fix round 1, RC2). Their plan is the union of the milestone node's and its leaf descendants' `planned_test_changes`, because each removal in the combined diff landed with one leaf, and that leaf's authorization covers it.
- **Plan sources:** the cross-check reads the plan from the integration branch and from the reviewed commit, so an edit made on the leaf branch counts for this check. The integration ref comes from `integrity_removals.integration_ref` (git workflow config → `base_ref`), not from `ReviewTarget.base_ref`, which `--base` and a resumed delta overwrite. `integrity_gate` itself is unchanged and still reads only the integration branch.

## Final touch zones

These are the zones as widened by the coordinator, all used: `roadmap_edit_fields.py`, `roadmap_edit_list_fields.py` (new), `roadmap_crud_argparse.py`, `roadmap_crud_ops.py`, `integrity_removals.py` (new), `review_packet.py`, `review_packet_observed.py` (new), `review_record_rules.py`, `review_files.py`, `schemas/review-record.schema.json`, `role_prompt_rca.py`, `docs/acceptance-evidence.md` (new), `tests/`. `integrity.py` didn't need changes.

## Added

- **New functions:**
  - `roadmap_edit_list_fields.planned_test_change_items`: strips items, drops blanks and validates each against the schema's item shape (shared by `edit-node` and `add-node`).
  - `roadmap_edit_list_fields.set_planned_test_changes`: the `--set` handler; an empty value removes the field.
  - `roadmap_edit_list_fields._item_validator` (cached): the item validator built from the packaged roadmap schema.
  - `integrity_removals.unplanned_removals`: keeps the removal and weakening lines a plan doesn't list.
  - `integrity_removals.planned_for_target`: the plan from the integration branch and the reviewed commit, combined (for a milestone, over the node and its leaves).
  - `integrity_removals.integration_ref`: the integration branch's ref, resolved independently of any diff base.
  - `integrity_removals._plan`: the union of `planned_test_changes` over a set of node ids.
  - `integrity_removals.target_unplanned_removals`: what `review record` checks, for any target kind; returns nothing when a commit is missing.
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
- **Tests:** 14 new tests in `tests/test_planned_test_changes.py`, covering edit-node set/add/remove plus validate on a claimed leaf; add-node with and without the flag plus validate; item stripping; which lines count as unplanned; the packet's heading for an unlisted removal and its absence for one listed on the leaf branch or the integration branch; record refusal, then filing with the entry; the plan on the integration branch with an explicit `--base`; a milestone's unplanned and leaf-planned removals through `review-packet` and `review record`; a block filed without the entry and a `fail` entry refused; an approve filed when the removal is planned; the reviewer prompt text.
- **Mocks:** none.

## Fix round 1

Commit `2e25f8d9` fixes Sol's RC1–RC3 on `d62fdeaf`.

- **RC1, class: "the plan was read from a ref that a caller can replace".** `planned_for_target` read `t.base_ref`, which `_with_base` replaces for `--base` and for the resumed-delta packet (`prior`). The fix removes the dependency: `planned_for_target` resolves the integration ref itself (`integration_ref`), so no change to the target's diff fields can move the authorization source.
- **RC2, class: "a review target kind exempted from the check".** `t.milestone` short-circuits in `integrity_sections` and `target_unplanned_removals` were removed. Both paths now share `planned_for_target`, which handles milestones by taking the union over the node and its leaves.
- **RC3:** the comment phrase is restored, and the file is still 400 lines.

### Fix round 1: target x option

The two inputs are separate. The **diff** is `t.base...t.commit`. The **authorization** is `planned_test_changes` on the integration ref from `integration_ref(root)`, together with the node as committed at `t.commit` (for a milestone, the node and its leaves).

| Target | Option | Diff (`base...commit`) | Authorization |
|---|---|---|---|
| leaf (claimed) | default | merge-base(integration ref, registered branch) ... branch tip minus bookkeeping | integration ref + node at commit |
| leaf | `--ref R` | merge-base(integration ref, R) ... R minus bookkeeping | integration ref + node at commit |
| leaf | `--base B` (packet only) | merge-base(B, commit) ... commit | integration ref + node at commit (unchanged by B) |
| leaf | resumed delta (`prior`, packet only) | merge-base(prior commit, commit) ... commit | integration ref + node at commit (unchanged) |
| milestone (no claim) | default | first parent of the oldest leaf registration ... integration tip | integration ref + node and leaves at the tip |
| milestone | `--ref R` | same base ... R | integration ref + node and leaves at R |
| milestone | `--base B` (packet only) | merge-base(B, tip) ... tip | integration ref + node and leaves at the tip (unchanged by B) |
| `review record` (any kind) | default / `--ref` | as resolved by `resolve_target` (no `--base`) | the same `planned_for_target` |

A milestone that has a registry claim (a branch) resolves as a leaf. There is no separate chore target kind in `resolve_target`. `review record` has no `--base`, so it always checks the full range. A `--base` or delta packet can list fewer removals than the record enforces. That direction is stricter, never looser.

## Probes

- `--base` set to the leaf's merge-base SHA, with authorization only on dev after that base: no heading, and `review record` approve with no entry exits 0 (`test_packet_with_an_explicit_base_still_reads_the_plan_from_the_integration_branch`). It fails on `d62fdeaf`.
- Resumed-delta packet (`prior`): it goes through the same `_with_base`, and the plan no longer reads `t.base_ref`, so it is fixed by construction (no separate test).
- Other readers of `t.base_ref` in the packet (header `base_how`, the empty-diff hint): these describe the diff range, which is their intended use. They are unchanged.
- `integrity_gate.integrity_gate_problems`: it reads the plan from the `ref` it is passed (`policy_source`), never from a review target. Not affected.
- Milestone `review-packet M2` with a leaf-made unplanned removal: heading present (fails on `d62fdeaf`).
- Milestone `review record M2` through `review_cli.main`: approve without the entry exits 1 and names the heading; with `"removed-test: tests/test_ms.py::test_old": pass` it exits 0.
- Milestone whose leaf `M2.1` lists the removal in `planned_test_changes` on dev: no heading, and the record files without the entry.
- Other `t.milestone` branches in the changed modules (grep): only `planned_for_target`'s leaf-plan union remains, which widens authorization and exempts nothing.
- Reviewer prompt (`role_prompt_rca.py`): it has no milestone condition, and its text is keyed on the packet heading.
- `review_files.py` comment: the phrase is restored, and the file is 400 lines (`specy-road file-limits` OK).
- Targeted suite: the 67 test files importing `integrity_removals`, `review_packet`, `review_files`, `review_record_rules`, `review_cli` or `integrity_gate` give 1004 passed.
