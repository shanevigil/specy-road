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
  - `integrity_removals._plan_at`: `planned_test_changes` of the node (and, for a milestone, its leaves) in the roadmap committed at one ref, via `load_roadmap_nodes_at_ref`.
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
- **Tests:** 15 new tests in `tests/test_planned_test_changes.py`, covering edit-node set/add/remove plus validate on a claimed leaf; add-node with and without the flag plus validate; item stripping; which lines count as unplanned; the packet's heading for an unlisted removal and its absence for one listed on the leaf branch or the integration branch; record refusal, then filing with the entry; the plan on the integration branch with an explicit `--base`; a milestone's unplanned and leaf-planned removals through `review-packet` and `review record`; the plan read at the reviewed commit when the review runs from dev after the leaf moved its chunk; a block filed without the entry and a `fail` entry refused; an approve filed when the removal is planned; the reviewer prompt text.
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

## Fix round 2

Commit `e35ebab5` fixes Sol's round-2 RC1 and RC2 on `4377030a`.

- **RC1, class: "a roadmap read that depends on the working checkout".** `planned_for_target` read the reviewed commit's node through `node_at()`. That function picks the chunk path from the checkout, so a review run from dev after the leaf moved M1.1 to a new chunk found nothing. Now both sides (the reviewed commit and the integration ref) load the whole roadmap at that ref with `load_roadmap_nodes_at_ref`. A milestone's leaf ids also come from each ref's graph (`leaf_descendants` on those nodes), not from `t.nodes`.
- **RC2:** the milestone fixture is now public in `tests/milestone_repo_helpers.py`: `make_milestone_repo`, `milestone_node`, `chunk_path`, `set_status`, `branch_leaf`, `merge_leaf`, `land_leaf`, `KEYS` and `LEAVES`. `test_milestone_full_review.py` keeps only `_statuses` and `_effective_rollup`. It, `test_planned_test_changes.py` and `test_refusals_name_their_fix.py` (which imported `make_milestone_repo` from the test module) now import from the helpers. Both milestone scenarios are unchanged.

### Fix round 2: ref reads

These are the roadmap reads in this leaf's code, and where each one reads from:

| Read | Where | Source |
|---|---|---|
| plan at the reviewed commit | `integrity_removals._plan_at(root, t.commit, ...)` | `load_roadmap_nodes_at_ref(root, t.commit)`: manifest and chunks at that commit |
| plan on the integration branch | `integrity_removals._plan_at(root, integration_ref(root), ...)` | `load_roadmap_nodes_at_ref` at the integration ref |
| milestone leaf ids for the plan | `leaf_descendants(nodes_at_ref, node_id)` in `_plan_at` | that ref's graph |
| integrity findings | `compare_integrity(root, t.base, t.commit)` | git objects at `base` and `commit`; not a roadmap read |
| `review_packet_observed`, `review_record_rules.unplanned_removal_problem`, `role_prompt_rca` text | none | no roadmap read |
| `review_files` schema load | `schemas/review-record.schema.json` | packaged schema; not the roadmap |
| `edit-node` / `add-node` (`roadmap_edit_fields`, `roadmap_edit_list_fields`, `roadmap_crud_ops.cmd_add`, `roadmap_crud_argparse`) | `load_roadmap(root)`, `find_chunk_path`, `load_json_chunk` | the working checkout, by design: these commands edit that tree, and the edit is committed and then read at its ref |

Outside this leaf, `resolve_target` still decides `t.milestone` and node existence from the checkout's `load_roadmap`. That is pre-existing and shared by every review command, and I did not change it here. Only the plan's leaf set moved off `t.nodes`.

## Probes (round 2)

- Review from dev after the leaf moved M1.1 from `phases/M1.json` to `phases/M1b.json` and added `planned_test_changes` there: `review-packet` has no heading, and `review record` approve with no entry exits 0 (`test_plan_is_read_at_the_reviewed_commit_after_the_leaf_moves_its_chunk`). It fails on `4377030a`.
- `node_at` and `t.leaf_ids` in `integrity_removals.py`: no longer used (grep).
- Imports of underscore names from another test module in this leaf's tests: none remain (grep `from tests.test_milestone_full_review`: none).
- Milestone scenarios (an unplanned removal is refused, then filed with the entry; a leaf-planned removal is filed): both pass with the shared helpers.
- Targeted suite: the 67 test files importing the changed modules or the milestone fixture give 1005 passed. `tests/test_refusals_name_their_fix.py` (41 together with the two above) passes. `specy-road file-limits` OK; `ruff` clean.
