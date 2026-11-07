# Implementation summary: M22.3 (decisions-follow-moves)

## What changed

- **A1, the move.** `stage_id_rewrite` (`roadmap_move_node.py`) calls `_stage_decision_ids` (`roadmap_id_rewrite_staging.py`) first, before any other file is staged, on every id-changing move (move-node, indent, outdent, group-nodes, `--renumber-outline`, and the PM GUI move, indent, outdent, group and `renumber_outline` reorder all go through `stage_id_rewrite`). When the old -> new map is non-empty and the tracked `roadmap/decisions.yaml` exists, `load_checked_decisions` (`decisions.py`) reads it with `read_decisions` (`yaml.safe_load`) and checks the existing decisions schema. A parse error, a non-mapping root or schema errors raise `ValueError` naming `roadmap/decisions.yaml`, so the CLI exits 1 and the GUI handlers that catch `ValueError` answer 400, and nothing is staged. Each entry's `node` is looked up once in the map, so a chain or a swap keeps the id that entry named. The file is staged, with the same YAML dump `write_decisions` uses, only when an entry changed. An absent ledger is left absent. `decisions.local.yaml` is not read. Summary and answer text are not rewritten.
- **A2, the notice.** `notice_decisions_naming_no_node` (`decisions.py`), called from `run_validation` (`validate_roadmap_checks.py`), prints one stdout notice listing each `open_questions` entry and each `active_preferences` entry whose `node` is a non-empty string that is not a live id. Closed entries, expired preferences and entries with no `node` are omitted. An absent, unreadable or schema-invalid ledger prints nothing. stdout, so `--strict` does not count it and the exit code is unchanged.
- **A4.** `docs/roadmap-authoring.md` (the move-node rewrite list and the validate step), `docs/orchestration.md` (the ledger section) and a CHANGELOG `[Unreleased]` Fixed entry.

Touch zones, unchanged: `specy_road/bundled_scripts/roadmap_id_rewrite_staging.py`, `specy_road/bundled_scripts/roadmap_move_node.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/bundled_scripts/validate_roadmap_checks.py`, `specy_road/decisions.py`, `tests/test_move_node_subtree.py`, `tests/test_decisions.py`, `docs/roadmap-authoring.md`, `docs/orchestration.md`, `CHANGELOG.md`. `validate_roadmap.py` needed no edit: `validate_at` already calls `run_validation`, which is where the notice is invoked.

A6 is not binding. `M16.1.1` and `M16.1.2` are Not Started, and `tests/parity/` does not exist. No file under `tests/parity/` changed.

## Fix round 1 (review gpt-5.6-sol-high at 77cd742f)

- **Class: reading the tracked ledger fails before YAML parses.** Invalid UTF-8 raises `UnicodeError` (a `ValueError` the CLI printed without the file name). A mode `000` file raises `PermissionError` (`OSError`), which the notice did not catch, so `validate --strict` exited 1. One rule in `load_checked_decisions`: a `YAMLError`, `UnicodeError` or `OSError` while reading becomes `ValueError` naming `roadmap/decisions.yaml`. The move already lets that out. The notice already returns on every `ValueError` from that function, so both shapes are silent there. Limit, stated in the docstring: a directory at that path counts as absent (`is_file()` is false); `decisions.local.yaml` is not read.
- **Class: the sheet-zone test's own tail.** `test_a_move_rewrites_zones_naming_the_moved_sheet_in_both_forms` lost its unstaged/staged `validate` assertions in the implementation commit. Restored. No other test in this leaf lost an assertion (diff of `e1902faa` against its parent).

## Probes

- Callers of `load_checked_decisions`: only `_stage_decision_ids` and `notice_decisions_naming_no_node`. One except covers both. `read_decisions` callers outside this leaf (`add`/`close`, `decisions_local`, `review_deferral`) are unchanged.
- Move CLI, invalid UTF-8: exit 1, stderr names `roadmap/decisions.yaml`, tree bytes unchanged (parametrized refusal test).
- Move CLI, mode `000`: same named exit 1 and unchanged bytes (same test).
- `validate --strict`, invalid UTF-8 and mode `000`: exit 0, no `PermissionError`, no `decisions.yaml` on stdout or stderr (silence test).
- A directory at `roadmap/decisions.yaml` makes `load_checked_decisions` return `None` (treated as absent). A `decisions.local.yaml` beside it is not read.
- Restored sheet-zone test: `validate` exits 0 with no "names a planning sheet" line, unstaged and after `git add`.

## Verification

- `pytest -q -n 4` on `tests/test_move_node_subtree.py`, `tests/test_decisions.py`, `tests/test_gui_outline_contract.py` and the PM GUI Python API tests (`tests/test_gui_app*.py`, `tests/test_roadmap_gui_*.py`): 193 passed before this round.
- Fix round: `pytest -q -n 4 tests/test_move_node_subtree.py tests/test_decisions.py` passed (43, then the mode-`000` move row). `ruff check specy_road tests scripts` passed. `specy-road file-limits`: OK (the four hard-alert warnings are pre-existing files this leaf does not touch).

## Added

### Helpers / branches / guards
- `load_checked_decisions` (`decisions.py`): one read of the tracked ledger; `None` when the file is absent; `ValueError` naming `roadmap/decisions.yaml` on a YAML parse error, a non-mapping root or schema errors (A1 refusal, and the notice stays silent on the same shapes).
- `notice_decisions_naming_no_node` (`decisions.py`): the one stdout notice, built from `open_questions` then `active_preferences`, listing a non-empty string `node` that is not a live id; `now` is passed through to `active_preferences` (A2).
- `except (yaml.YAMLError, UnicodeError, OSError)` in `load_checked_decisions`: one read-failure rule, raised as `ValueError` naming the ledger (fix round 1). The notice's existing `except ValueError` is what keeps `validate` silent for those errors.
- `_stage_decision_ids` (`roadmap_id_rewrite_staging.py`): one lookup of each entry's `node` in the move's old -> new map; stage the ledger text only when an entry changed; return immediately when the map is empty (A1).
- Call of `_stage_decision_ids` at the start of staging in `stage_id_rewrite`, so an invalid ledger raises before any file is staged (A1).
- Call of `notice_decisions_naming_no_node` from `run_validation` (A2).

### Mocks
- none

### Tests
- `test_a_move_rewrites_decision_nodes_on_moved_ids_only` (`tests/test_move_node_subtree.py`): an open decision, a closed decision and a preference on moved ids are rewritten; an unmoved id and the summary text are not.
- Assert on `test_moving_a_leaf_out_of_the_middle_of_a_milestone`: a move with no ledger does not create one.
- `test_a_move_leaves_an_unmatched_ledger_byte_for_byte`: a ledger whose nodes are not in the map is not rewritten.
- `test_renumber_outline_swaps_decision_nodes_in_one_lookup`: a `--renumber-outline` swap of `M1`/`M2` and `M1.1`/`M2.1` replaces each `node` once.
- `test_a_refused_move_leaves_the_tree_byte_for_byte_unchanged` (validation / invalid YAML / sequence root / invalid UTF-8 / mode `000`): each leaves `roadmap/` and `planning/` byte-for-byte unchanged; validation names the duplicate title; the other four name `roadmap/decisions.yaml`.
- `_entry`, `_nodes_of` (`tests/test_move_node_subtree.py`): schema-valid ledger rows and a read-back by id for those move tests.
- `test_validate_notices_open_entries_naming_no_live_node` (`tests/test_decisions.py`): one stdout notice under `--strict` lists an orphan open decision, open human-action and active preference once each, and stays silent for a closed entry, an expired preference, a preference without `node` and a live-node reference (fixed dates `2099-12-31` and `2000-01-01`).
- `test_validate_stays_silent_on_an_invalid_decision_ledger` (invalid YAML / sequence root / invalid UTF-8 / mode `000`): `--strict` still exits 0, does not mention the ledger, and does not show `PermissionError`.
- Restored the unstaged/staged `validate` assertions on `test_a_move_rewrites_zones_naming_the_moved_sheet_in_both_forms`.
- `_question`, `_strict_repo` (`tests/test_decisions.py`): ledger rows for that table, and a repo whose `validate --strict` has no other warning.
