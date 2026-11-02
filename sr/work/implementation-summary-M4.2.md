# Implementation summary: M4.2 — Structured promote (`promote-structured`)

Base `da8d625`, touch zones widened at `536b6ea`. Implementation commit `b5f71b5`.

## Design

Each promote call now builds a list of `Landing`s (one per node to write: title, parent, type, linked
ideas, alternatives, acceptance, dependencies and a pre-allocated `node_key`). One writer in
`brainstorm_promote.py` writes them, whichever way they were chosen. `brainstorm_promote_plan.py`
chooses them: one per idea, one per cluster lead, or one per plan entry.
Each plan landing gets its `node_key` before anything is written. That lets a dependency on a later
plan entry resolve straight to a `node_key`, and it lets a plan child find its plan parent's display
id at write time.

## Acceptance

- **A1:** `revise --target-parent <ID>` stores `Idea.target_parent`, serialised through
  `brainstorm_fields` (`''` clears it; triage status is unchanged). Promote lands an idea under its
  `target_parent`, otherwise under `--under`, otherwise under the session anchor. Each distinct
  existing parent is checked (exists, not milestone-locked) before anything is written.
- **A2:** `promote --by-cluster` writes one node per cluster. The lead is the idea with the strongest
  verdict; on a tie, the earliest accept wins. The other accepted ideas in the cluster are linked to
  the lead's node (`promoted_node_key`) and listed on its sheet as "Alternative considered", along
  with the cluster's rejected and parked siblings, as before. An idea with no cluster is its own lead.
- **A3:** `promote --min-recommendation strong|consider|park` drops weaker verdicts. An idea with no
  verdict ranks weakest. Skipped ideas stay accepted, and the CLI names each one on stderr.
- **A4:** `promote --plan plan.yaml` reads a `nodes:` list. Each entry needs `title`; the optional
  keys are `ref`, `parent`, `type`, `acceptance`, `dependencies` and `ideas`.
  - `parent` is a node id or an earlier entry's `ref`, and defaults to the anchor.
  - `dependencies` are node ids or any entry's `ref`, and are stored as `node_key`s via
    `resolve_dependency_refs`.
  - `ideas` lists accepted idea ids. The first idea seeds the sheet, every listed idea is linked, and
    the extra ones appear as "Also promoted into this node".
  - Unknown keys, bad refs, ideas that are not accepted or are listed twice, and gate types are all
    refused before anything is written.
  - `--plan` cannot be combined with `--by-cluster` or `--min-recommendation`.
  - The CLI's "nothing to promote" early return no longer blocks `--plan`.

## Behaviour notes

- The anchor frame is now written to each distinct existing parent that received a node, not only
  to the session anchor (the same thing when no target parents or plan are used).
- `execution_milestone` is inherited from each node's own parent, so a plan child inherits from its
  plan parent.
- The authoring prompt covers only nodes an idea seeded. `render_authoring_prompt`
  (`brainstorm_prompt.py`, outside the touch zones) looks up `session.by_id(p.idea_id)`, so a plan
  node with no ideas is left out of the prompt rather than breaking it.
- The CLI now prints `Promoted N node(s).` (it used to say `idea(s)`), because one node can carry
  several ideas. Each output row now says `(from B2, B1)` or `(plan)`.
- `pending_ideas` and `_accept_order_key` moved into `brainstorm_promote_plan`. `pending_ideas` is
  still importable from `brainstorm_promote` because `brainstorm_cli_v2` and the GUI import it from
  there. `brainstorm_promote.py` went from 398 to 388 lines.
- The GUI promote route is unchanged and does not expose the new options.

## Touch zones (final)

`specy_road/bundled_scripts/brainstorm_promote.py`, `brainstorm_promote_plan.py` (new),
`brainstorm_cli.py`, `brainstorm_cli_args.py`, `brainstorm_cli_revise.py`, `brainstorm_fields.py`,
`brainstorm_session.py`, `docs/brainstorming.md`, `tests/test_brainstorm_promote_structured.py` (new).

## Verification

- `pytest -q` on the new test file plus `test_brainstorm_promote.py`, `_promote_judgement.py`,
  `_promote_m37.py`, `test_brainstorm_cli.py`, `test_brainstorm_session.py`, `test_brainstorm_v2.py`,
  `test_gui_app_brainstorm.py`, `test_finish_scaffold_planning.py`, `test_unauthored_leaf_guard.py`:
  183 passed.
- `specy-road file-limits` (run from this worktree): OK. `docs/brainstorming.md` is at 399 of 400.
- `ruff check` (C901) on the touched modules and the new test file: all checks passed.
- `scripts/check_test_private_imports.py`: 0 new private references.
- `scripts/check_clones.py` was **not run**, because `pylint` is not installed in either local
  environment.

## Added

### Helpers
- `brainstorm_promote_plan.Landing` (with `linked()`): one spec type for every way of choosing what
  to write, so a single writer handles A1, A2 and A4.
- `RECOMMENDATION_RANK`, `_rank`, `below_recommendation`: rank verdicts for A3 and for picking the
  A2 lead. `below_recommendation` also rejects an unknown minimum.
- `idea_landings`: one landing per idea or per cluster lead, applying `target_parent` before the
  anchor (A1, A2).
- `select_landings`: chooses between plan and idea landings, applies the A3 filter, and refuses
  `--plan` combined with the filters.
- `_read_plan`, `_plan_entry`, `_str_list`, `_plan_ideas`, `_plan_dependencies`, `plan_landings`:
  parse and validate the plan file, link ideas by id, and resolve refs and display ids to
  `node_key`s (A4).
- `brainstorm_promote._land`: writes one node, seeds its sheet and links its ideas. It was split out
  of the writer loop to stay under C901.
- `brainstorm_promote._promote_landings` (replaces `_promote_ideas`): writes landings with a parent
  per node, plan parents resolved by `node_key`, and dry-run sibling order counted per parent.
- `brainstorm_promote._assert_landings`: checks every landing type and every existing parent before
  any write.
- `brainstorm_cli._promote_warnings`: the A3 skip notices plus the existing strong-but-unverified
  warning, split out so `cmd_promote` stays readable.

### Branches and guards
- `Promotion.linked`: the other idea ids on a node, for CLI output.
- `seed_planning_sheet(also=…)`: the "Also promoted into this node" reference lines.
- `_build_node` now writes `acceptance` and `dependencies` from the landing, and takes its
  `node_key` from the landing.
- `promote_session` takes the `by_cluster`, `min_recommendation` and `plan` keyword arguments. It
  rolls back every linked idea's marker on a validation failure and writes the frame to each
  existing parent.
- `cmd_promote` skips the "nothing to promote" early return and the per-idea warnings when `--plan`
  is given.
- `revise --target-parent` (args) and `_revise_links` store or clear the target parent.
- `parse_extra` and `EXTRA_DEFAULTS` handle `target_parent`, sharing the string branch with
  `cluster_id`.

### Mocks
- none

### Tests (`tests/test_brainstorm_promote_structured.py`)
- `test_revise_target_parent_is_stored_and_cleared`: A1 round-trips through the session file; `''`
  clears it; the idea's status is unchanged.
- `test_promote_honours_target_parent_and_falls_back_to_under`: A1.
- `test_unknown_target_parent_is_refused_before_anything_is_written`: an A1 guard, with no partial
  write.
- `test_by_cluster_promotes_the_lead_and_lists_the_others_as_alternatives`: A2 lead choice, linking
  and the sheet listing.
- `test_by_cluster_ties_go_to_the_earlier_accept`: A2 tie-break.
- `test_min_recommendation_strong_skips_weaker_verdicts`: A3.
- `test_cli_min_recommendation_reports_what_it_skipped`: A3 through the CLI, including the stderr
  notice.
- `test_plan_creates_the_tree_and_links_ideas_by_id`: A4 parent refs, type, acceptance, a forward
  ref plus an existing-id dependency stored as `node_key`s, and idea linking.
- `test_cli_plan_runs_with_no_pending_ideas`: A4 is not blocked by the early return.
- `test_plan_dry_run_nests_ids_and_writes_nothing`: A4 dry-run id allocation under plan parents.
- `test_a_bad_plan_is_refused_before_anything_is_written` (9 cases): A4 validation guards.
- `test_plan_does_not_combine_with_cluster_or_recommendation_filters`: the `--plan` exclusivity
  guard.
