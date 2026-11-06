# Implementation summary: M21.3 `rewrite-id-refs`

Implementation commit: `bf244bd2` on `feature/rm-rewrite-id-refs`. Fix round 1 merged `origin/WIP/improvements-0-3-1` (merge `1f4851ca`, no conflicts) and changed no code (see Fix round 1). Fix round 2 found WIP already merged and changed no code (see Fix round 2).

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

The listed zones plus `specy_road/bundled_scripts/roadmap_move_id_forms.py` (since added to the zones, `bc8c9b8c`). `validate_self_heal.py` imports `planning_rename` but is unchanged, because its function is untouched.

## Not done / notes

- `rename-refs` does not check milestone locks: it edits prose only, not structure. The move commands keep their existing lock checks.
- `/outline/reorder` takes no `rewrite_refs`, because the acceptance names only move, indent, outdent and group.

## Fix round 1 (gpt-6.1-sol-low block at e7775e16)

- **Finding:** pytest refused to start because `tests/fixtures/specy_road_dogfood/.specyrd/` held ignored files, so the PM GUI, importer and M21.1 contract tests went unverified.
- **Class:** a verifier that writes ignored runtime state into `tests/fixtures/`, after which the fixture guard (`tests/fixture_guard.py`) refuses every later pytest run in that checkout.
- **Cause:** the round-0 READY ran `specy-road digest --check --repo-root tests/fixtures/specy_road_dogfood` last. That command writes `.specyrd/cache/` into the fixture, so the tree the reviewer got was dirty. This leaf's code and tests don't write there (see Probes).
- **Fix:**
  - The new READY runs only the targeted pytest, `ruff check specy_road tests scripts` and `specy-road file-limits`, none of which touch the fixture.
  - The fixture was cleaned with the guard's own `git clean -fdX tests/fixtures`, and it was clean before and after the targeted run.
  - Stopping `digest` from writing its cache into a `--repo-root` fixture would need a change in `digest_cli.py` or the history cache. That is outside this leaf's zones and acceptance, so it is not done here.

## Fix round 2 (gpt-6.1-sol-low block at 015687c9)

- **Finding:** in the reviewer's Codex session, the GUI tests stalled inside Starlette `TestClient` (AnyIO `start_task_soon` waiting, event-loop thread in `selector.select`) before any request reached repository code, so A3 went unverified.
- **Class:** any cross-thread asyncio wakeup inside the Codex Linux sandbox. That sandbox rejects `send()` on an AF_UNIX `socketpair` with `EPERM`. asyncio's `call_soon_threadsafe` wakes its loop by writing to exactly such a self-pipe and silently ignores that error, so the loop thread never wakes. Every `TestClient` request goes through an AnyIO blocking portal and therefore hangs. This is the same stall the Codex reviews of M21.1, M21.2, M16.67 and M15.13 recorded; M21.1's and M21.2's also reproduced it with a minimal app containing no repository code.
- **Fix:** none in code. Neither the leaf's code nor its tests can remove a sandbox syscall denial, and the A3 gate files (`tests/test_gui_app*.py`, `tests/test_roadmap_gui_*.py`, the unchanged `tests/test_gui_outline_contract.py`) must run as they are. They were run on the host, where `TestClient` requests complete, and their output is recorded in READY. A conftest workaround for the sandbox would be outside this leaf's acceptance, so it is not added.
- **Reproduce:**
  - `codex sandbox -- python -I x.py`, where `x.py` sends one byte across `socket.socketpair()`, fails with `[Errno 1] Operation not permitted`.
  - The same command with a one-route Starlette app and `TestClient(app).get("/")` hangs.

## Probes

- `git status --porcelain --ignored -- tests/fixtures` after `specy-road validate --repo-root <fixture>`: clean.
- The same after `specy-road export --check --repo-root <fixture>`: clean.
- The same after `specy-road digest --check --repo-root <fixture>`: `.specyrd/` left behind. This is the source, and it is excluded from the new READY.
- `tests/test_rename_refs.py` and `tests/move_node_helpers.py` write only under `tmp_path`, and `run_cli` always passes `--repo-root tmp`; no path reaches `tests/fixtures`.
- Fixture status before and after the targeted pytest run: clean both times.
- Targeted pytest over 62 files (every test importing a changed module or `move_node_helpers`, plus `tests/test_gui_app*.py` and `tests/test_roadmap_gui_*.py`, and the unchanged `tests/test_gui_outline_contract.py`): 930 passed.
- `tests/test_gui_outline_contract.py` has no diff against the merge base.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

- Round 2: serial `tests/test_rename_refs.py tests/test_gui_outline_contract.py` with `faulthandler_timeout=60` on the host: 76 passed in 10 s, no stall.
- Round 2: minimal Starlette app (no repository code) with `TestClient.get("/")`: host returns `{'ok': True}`; under `codex sandbox --` it hangs (killed by `timeout 20`, exit 124).
- Round 2: plain `asyncio.run_coroutine_threadsafe` onto a loop running in another thread: under `codex sandbox --` it raises `TimeoutError` after 5 s; on the host it completes.
- Round 2: `socket.socketpair()` then `send(b"x")`: under `codex sandbox --` it fails with `EPERM`; on the host it works. This is the root cause.
- Round 2: earlier Codex reviews (M21.1, M21.2, M16.67, M15.13) report the same TestClient stall; M21.1 and M21.2 reproduced it with a minimal app, and M15.13 reproduced it on its base snapshot.
- Round 2: the A3 gate run serially on the host (`tests/test_gui_app*.py`, `tests/test_roadmap_gui_*.py`, `tests/test_gui_outline_contract.py`, `tests/test_rename_refs.py`): 184 passed.
- Round 2: the 62-file targeted run (`-n 4`): 930 passed. Fixture ignored-file status was clean before and after.
- Round 2: `tests/test_gui_outline_contract.py` has no diff against the WIP merge base `275ca876`.

## Verification

- **A3 GUI gate:** the authoritative results for `tests/test_gui_outline_contract.py`, `tests/test_gui_app*.py` and `tests/test_roadmap_gui_*.py` are the ones `specy-road ready` recorded in `sr/work/reviews/M21.3/READY-claude-opus-5.5.md`. They were run outside any sandbox, because the Codex reviewer sandbox cannot complete TestClient requests (see Fix round 2). The same READY records the targeted pytest, `python scripts/check_clones.py`, `ruff check specy_road tests scripts` and `specy-road file-limits`.
- Round 0: `pytest -n 4`: 5378 passed. Round 1: targeted run, 930 passed (see Probes).
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
- Fix round 1: none (no code, test or guard added).
- Fix round 2: none (no code, test or guard added).
