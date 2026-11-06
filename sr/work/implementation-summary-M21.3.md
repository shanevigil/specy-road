# Implementation summary: M21.3 `rewrite-id-refs`

Implementation commit: `bf244bd2` on `feature/rm-rewrite-id-refs`.

## What changed

- **A1, the rewriter and `rename-refs`** (`specy_road/bundled_scripts/planning_rename.py`):
  - `rewrite_id_refs(text, id_map)` builds one regex `(?<![A-Za-z0-9_.])(?:keys…)(?!\d|\.\d)` and substitutes in one pass over the original text, so swaps and chains are safe. Keys go longest first, and identity entries are dropped.
  - Protected spans are left as written:
    - fenced blocks, from a line whose trimmed text starts with three or more backticks through the next such line;
    - `<!-- historical -->…<!-- /historical -->` blocks.

    An unclosed fence or historical block runs to the end of the text.
  - `stage_prose_refs(plan, root, nodes, id_map)` rewrites each node's `title` and `acceptance` strings in place. It stages each changed `planning_dir` sheet into an `AtomicWritePlan`, reading a sheet's already-staged text first so it sees any renames in the same plan. It returns counts per sheet and per `<id> title/acceptance`.
  - `rename_refs(root, id_map, dry_run=)` loads live nodes with `load_roadmap`, stages the rewrites, and commits through `run_validate_raise`. With `--dry-run` it writes nothing.
  - `main()` is the `specy-road rename-refs <ID_MAP_JSON> [--dry-run]` CLI, registered in `specy_road/cli.py` `_SCRIPTS`. A map that is not a JSON object of non-empty strings exits 1. It prints one `  <label>: <n>` line per changed place, then a total.
- **A2, `--rewrite-refs` on the CLI moves:**
  - `add_rewrite_refs_arg` and `print_rewrite_refs_note` live in `planning_rename.py` and are shared by `move-node` (`roadmap_move_node.py`) and by `indent`, `outdent` and `group-nodes` (`roadmap_outline_group.py`).
  - `move_nodes`, `move_node` and `stage_id_rewrite` gain `rewrite_refs=False`, and so do `move_node_outline`, `apply_indent` and `apply_outdent` (`roadmap_outline_ops.py`) and `group_nodes`.
  - `stage_id_rewrite` passes the move's own renamed map to `_stage_planning_moves` (`roadmap_id_rewrite_staging.py`). That function now takes optional `nodes` and `prose_map` and, after staging the sheet renames, calls `stage_prose_refs`. Everything goes into the move's single plan, so a failed validation rolls the prose back with everything else.
  - Staging order in `stage_id_rewrite` changed from chunks → new parent → sheet renames to sheet renames (+ prose) → chunks → new parent. The prose step must run before the chunks are rendered, because it edits titles and acceptance, and after the renames, because it reads their staged text. The sheet paths and the chunk paths don't overlap, so without the flag the output is unchanged.
  - Without the flag no prose changes. When ids changed, the CLI prints one line saying whether prose was rewritten or how to rewrite it.
- **A3, PM GUI:**
  - `MoveOutlineBody`, `GroupOutlineBody` and `OutlineShiftBody` gain an optional `rewrite_refs: bool = False`.
  - `/outline/move`, `/outline/group` and `/nodes/{id}/indent|outdent` pass it through.
  - Response shapes are unchanged, and `tests/test_gui_outline_contract.py` (M21.1) is unedited and passes.
- **A4, docs and tests:**
  - `docs/roadmap-authoring.md` (item 2 of "Supported workflow") documents `rename-refs`, `--rewrite-refs`, the GUI's `rewrite_refs` (default false), and the exclusions: docs/, CHANGELOG.md, work/, roadmap.md and git history.
  - `cli_usage.py` lists `rename-refs` and `--rewrite-refs`.
- **File-limits split:** `specy-road file-limits` resolves `sr/constraints/file-limits.yaml`, which has a 400-line cap. Even after the shared CLI helpers moved to `planning_rename.py`, `roadmap_move_node.py` would have been at 405 lines.
  - `_refuse_id_form_combinations` and `_moved_node_id` moved unchanged into the new module **`specy_road/bundled_scripts/roadmap_move_id_forms.py`**. It is outside the zones, so please add it to them.
  - `cli.py` registers `rename-refs` on the same line as `move-node` to stay at 400 lines.

## Final touch zones

The listed zones plus the new `specy_road/bundled_scripts/roadmap_move_id_forms.py`. `validate_self_heal.py` imports `planning_rename` but is unchanged, because its function is untouched.

## Not done / notes

- `rename-refs` does not check milestone locks: it edits prose only, not structure. The move commands keep their existing lock checks.
- `/outline/reorder` takes no `rewrite_refs`, because the acceptance names only move, indent, outdent and group.

## Verification

- `pytest -n 4`: 5378 passed.
- `specy-road file-limits` (sr/ config and `--repo-root .`): OK.
- Dogfood fixture `validate`, `export --check` and `digest --check`: OK.
- `ruff check` on changed files: clean.
- Red check (not recorded as a verifier): with `roadmap_move_node.py` reverted, `tests/test_rename_refs.py` fails (8 failed, 12 errors).

## Added

- `planning_rename.rewrite_id_refs`: the A1 boundary-safe one-pass rewriter.
- `planning_rename._protected_spans`, `_FENCE`, `_HISTORICAL`: the fenced and historical skip rule.
- `planning_rename._rewrite_node_strings`: rewrites title and acceptance in place.
- `planning_rename._sheet_text`: reads a sheet's staged text before disk, so the prose rewrite follows renames in the same plan.
- `planning_rename.stage_prose_refs`: one function shared by `rename-refs` and the moves (A2/A3 "same function").
- `planning_rename._load_id_map`: guard that refuses a map that is not a JSON object of strings (exit 1).
- `planning_rename.rename_refs` and `main`: the standalone command, validated, with `--dry-run`.
- `planning_rename.print_ref_counts`: per-file and per-node counts (A1).
- `planning_rename.add_rewrite_refs_arg` and `print_rewrite_refs_note`: one flag definition and note for the four CLI moves.
- `rewrite_refs=False` parameter on `stage_id_rewrite`, `move_nodes`, `move_node`, `move_node_outline`, `apply_indent`, `apply_outdent` and `group_nodes`: carries the opt-in into one transaction.
- `nodes` and `prose_map` optional parameters on `_stage_planning_moves`, plus the `if prose_map is not None` branch: the prose step inside the plan.
- `rewrite_refs: bool = False` on three GUI request models: optional, additive field (A3).
- `roadmap_move_id_forms.py`: existing helpers moved unchanged to stay under the file cap.
- `tests/test_rename_refs.py` (new file; the M21.1 contract test must stay unchanged):
  - `test_rewrite_matches_whole_ids_only`: boundary cases, swap, chain, fenced, long indented fence and historical.
  - `test_rename_refs_rewrites_sheets_and_acceptance_and_prints_counts`: the CLI with a swap map and its counts.
  - `test_rename_refs_dry_run_writes_nothing`: dry-run leaves the tree byte-identical.
  - `test_moves_rewrite_prose_only_with_the_flag`: move-node, indent, outdent and group-nodes, each with and without the flag.
  - `test_a_failed_move_rewrites_nothing`: a validation failure leaves the tree byte-identical. Uses the same `run_validate_raise` monkeypatch as the existing rollback test.
  - `test_gui_rewrite_refs_is_opt_in`: four GUI routes × true/false/omitted.
- Mocks: only the `run_validate_raise` monkeypatch above.
