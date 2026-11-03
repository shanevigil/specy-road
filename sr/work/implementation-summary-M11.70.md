# Implementation summary: M11.70 — Touch zones are checked when they are written

Base: `be4ba26818a7fcca2b3fac32891f1fbe263be26d`. Code commit: `a513f0bd`.

## What changed

### A1 — zones checked against `git ls-files` at authoring time

Fix round 1 (Codex Sol block): validate now reports **every** open node's zone
that matches no tracked file and is not a directory, Not Started included.

- **`validate`** runs `touch_zone_tracked.warn_untracked_zones` over every open
  node (Complete/Archived/Cancelled skipped):
  - a zone that is a **name prefix** of tracked files but no file or directory
    (e.g. `pkg/worker_ops_`) gets one **stderr warning** per zone: the prefix is
    read as a literal path and is not supported, and the glob to use is named
    (`pkg/worker_ops_*.py`; extension added when every prefixed file shares one).
    `add-node` and `edit-node` show it, since they re-print validate's stderr
    `warning` lines;
  - every other such zone — plain missing path or unmatched glob — is named in
    **one stdout notice** for all nodes, with the advice to keep a zone that
    names a file the work will create. A notice, not a stderr warning, because
    `validate --strict` fails on any stderr line and a fresh `init project`
    scaffold's starter leaf names `vision.md`, a file its work creates: as a
    warning it failed `validate --strict` on every new project
    (`test_validate_strict.py` ×4 and `test_unauthored_leaf_guard.py` ×1 failed
    in the first attempt). Same precedent as the unauthored-leaf block.
- **`add-node`** (any zones) and **`edit-node`** (when the `--set`/`--add`/
  `--remove` pairs touch `touch_zones`) print that untracked-zones line as a
  **stderr warning** for the node they wrote (`warn_written_zones`), because
  they discard validate's stdout. Prefixes are left to validate's line.
- **Globs:** already supported by the matcher
  (`finish_implementation_check.zone_matches`, fnmatch); the checks match globs
  against tracked paths the same way, and every line says zones may be globs
  and that a bare prefix is not supported.
- Tracked paths come from `git ls-files` at the git root, in both git-root and
  project-relative form, so nested projects (`sr/`) accept a zone from either
  root. Outside git the checks are silent.
- The existing working-tree check (`validate_touch_zones.py`, In Progress /
  Blocked only) is unchanged; a started node with a missing zone gets its
  stderr block and the new notice.

### A2 — call sites in the brief; docs

- Brief section 7 gains `### Call sites (one level)` when the node has zones:
  each zoned Python file at `HEAD` that something imports, with **every** direct
  importer named (fix round 1: inside-zone importers are named too, not
  counted). Importers outside the zones are marked _(outside zones)_ and listed
  first, and zoned files with an outside importer come first, so the bounds
  never hide them. Bounds: `IMPORTER_CAP` = 10 importers per file and
  `FILE_CAP` = 30 files, each with an explicit `… and N more` count. Reuses
  `specy_road.impact`'s import graph (`python_sources`, `module_names`,
  `imported_names`), read one level. One line outside git;
  `_none found (Python imports only)_` when nothing imports a zoned file.
- `docs/roadmap-authoring.md`: the `touch_zones` field row now says how to
  choose zones (read the code; files, directories ending in `/`, or globs;
  never a bare prefix; add importers whose calls change, as listed under
  **Call sites**) and documents the new warnings; the Registry and brief
  section mentions the call-site list. The file was at its 400-line cap, so
  both edits extend existing lines; no line was added or removed.

## Touch zones (final list)

The leaf's zones plus two **new modules**, created because
`validate_roadmap_checks.py` (392/400 lines) and `generate_brief.py`
(427/450) had no room for the logic; both are in the node's zones since `f5e369ba`:

- `specy_road/bundled_scripts/roadmap_crud_ops.py`
- `specy_road/bundled_scripts/validate_roadmap_checks.py`
- `specy_road/bundled_scripts/generate_brief.py`
- `specy_road/bundled_scripts/touch_zone_tracked.py` **(new)**
- `specy_road/bundled_scripts/brief_call_sites.py` **(new)**
- `docs/roadmap-authoring.md`
- `tests/`

No file outside these was edited. Not covered (outside the zones, not required
by A1's "add-node, edit-node"): the PM GUI's edit path calls
`edit_node_set_pairs` directly, so it gets validate's prefix warning and notice but not
the add/edit-only untracked-zone warning.

## Verification

Fix round 1:

- `python -m pytest -n auto -q` on the new tests and the validate, CRUD, brief,
  init and layout suites (`tests/test_touch_zone_tracked.py`,
  `tests/test_brief_call_sites.py`, `tests/test_validate_strict.py`,
  `tests/test_unauthored_leaf_guard.py`, `tests/test_validate_roadmap.py`,
  `tests/test_validate_touch_zones.py`, `tests/test_roadmap_crud*.py` (5 files),
  `tests/test_roadmap_apply.py`, `tests/test_generate_brief.py`,
  `tests/test_init_project.py`, `tests/test_project_layouts*.py`) — 255 passed
- `specy-road file-limits` — OK
- `ruff check` on the changed Python files — clean
- An earlier full-suite run in this round, with validate's generic line on
  stderr, failed the five `--strict` scaffold tests named above; that led to
  the notice. The full suite was not rerun after the change.

Round 0: full suite 3341 passed, 2 skipped.

## Added

### Helpers
- `touch_zone_tracked.Tracked` — tracked paths in both root forms, sorted, with `starting_with` (bisect prefix scan) and `matches` (file, tracked or on-disk directory, or glob); one place both checks read.
- `touch_zone_tracked.tracked_files` — `git ls-files -z` at the git root plus project-relative forms; `None` outside git so the checks stay silent.
- `touch_zone_tracked.prefix_of` — tracked files a zone is only a name prefix of; the A1 example case.
- `touch_zone_tracked._glob_for` — the glob suggestion, with the shared extension.
- `touch_zone_tracked._is_settled` / `_clean` — skip Complete/Archived/Cancelled nodes; normalise zones (a local copy because `validate_touch_zones._is_settled` is private and outside the zones).
- `touch_zone_tracked.untracked_zones` — zones matching no tracked file and no directory, prefixes left out; shared by both reporters.
- `touch_zone_tracked._warn_prefix` — validate's per-zone prefix warning (stderr).
- `touch_zone_tracked._untracked_line` / `_entry` — the one untracked-zones line, shared by the notice and the add/edit warning.
- `touch_zone_tracked.warn_untracked_zones` — validate's entry point: prefix warnings plus the one notice (A1, validate).
- `touch_zone_tracked.warn_written_zones` — add-node/edit-node's stderr warning for the written node (A1, add/edit; they discard validate's stdout).
- `touch_zone_tracked.GLOB_HINT` — shared wording that zones may be globs and prefixes are not supported (A1's "say in the warning").
- `brief_call_sites.direct_importers` — one-level importers per target using `impact`'s import parser (A2).
- `brief_call_sites.call_site_lines` / `_importer_line` — the `### Call sites` section, every importer named, outside ones marked and first, with caps and counts (A2).

### Branches and guards
- `Tracked.matches`: `ValueError`/`OSError` on the directory probe reads as a match — an advisory check must not fail a write.
- `prefix_of`: a zone ending in `/`, or containing glob characters, is never a prefix — `/` states directory intent.
- `untracked_zones`: an absolute or `..` zone is always reported (it can match nothing in the repo); prefixes are left to the prefix warning so one zone gets one line.
- `warn_untracked_zones`: the untracked line goes to stdout as a notice so `--strict` does not fail on zones naming files the work will create.
- `cmd_edit`: the written-zones warning runs only when the pairs include `touch_zones`, so unrelated edits do not repeat it.
- `call_site_lines`: one line when git cannot read the tree; outside importers and files with them sorted first; `FILE_CAP` / `IMPORTER_CAP` truncation with explicit counts.
- `_section_touch_zone_instruction` now takes `root` and appends the call sites only when the node has zones.

### Mocks
- `test_long_lists_are_capped_and_counted` monkeypatches `IMPORTER_CAP` and `FILE_CAP` to 1 to exercise both truncation counts without a large fixture.

### Tests
- `tests/test_touch_zone_tracked.py` — prefix warning text, glob suggestion and single-line shape; missing paths and unmatched globs on Not Started and In Progress nodes share one stdout notice; the written-node warning; files, dirs and matching globs quiet; settled nodes skipped; silent outside git; untracked-zone selection (globs, untracked dirs, `..`, prefixes left out); nested-project root forms; public `validate_roadmap.py` script: a Not Started node's missing path and unmatched glob are reported, `--strict` does not count them, a prefix zone warns (and fails `--strict`), good zones are quiet; `add-node` CLI warns for a prefix and an untracked zone; `edit-node` CLI warns only when it writes zones.
- `tests/test_brief_call_sites.py` — one-level importers with relative imports; every importer named with outside ones marked and first; files imported only from inside the zones still listed with their importers; none found; outside git; both caps with counts; the brief's section 7 carries the list; no list without zones.
