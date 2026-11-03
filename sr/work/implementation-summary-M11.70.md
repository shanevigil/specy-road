# Implementation summary: M11.70 — Touch zones are checked when they are written

Base: `be4ba26818a7fcca2b3fac32891f1fbe263be26d`. Code commit: `a513f0bd`.

## What changed

### A1 — zones checked against `git ls-files` at authoring time

- **`validate`** (and so every `add-node` / `edit-node`, which run validation and
  re-print its `warning` lines) now warns, one line per zone, when a zone on any
  open node (Not Started included; Complete/Archived/Cancelled skipped) is a
  **name prefix** of tracked files but names no tracked file and no directory —
  e.g. `pkg/worker_ops_`. The line says the prefix is read as a literal path and
  is not supported, and names the glob to use (`pkg/worker_ops_*.py`; the
  extension is added when every prefixed file shares one).
- **`add-node`** (any zones) and **`edit-node`** (only when the `--set` pairs
  include `touch_zones`) warn, one line, about every zone of the node they wrote
  that matches no tracked file and is not a directory (on disk or tracked),
  leaving out name prefixes (validate's line already names those, with the
  fix). The line tells the author to keep a zone that names a file the work will
  create, so nobody deletes such a zone to silence it.
- **Globs:** already supported by the matcher
  (`finish_implementation_check.zone_matches`, fnmatch); the new checks match
  globs against tracked paths the same way, and both warnings say zones may be
  globs and that a bare prefix is not supported.
- Tracked paths are taken from `git ls-files` at the git root, in both git-root
  and project-relative form, so nested projects (`sr/`) accept a zone from
  either root. Outside git both checks are silent. Each warning is a single
  line containing `warning` because `run_validate_raise` re-prints only such
  lines during `add-node` / `edit-node`.
- The existing working-tree check (`validate_touch_zones.py`, In Progress /
  Blocked only) is unchanged; an In Progress node with a prefix zone gets both
  its block and the new prefix line.

### A2 — call sites in the brief; docs

- Brief section 7 gains `### Call sites (one level)` when the node has zones:
  each zoned Python file at `HEAD` with the modules that import it directly.
  Importers outside the zones are named (cap 10 per file, 30 files); importers
  inside the zones are counted, and zoned files imported only from inside the
  zones are summarised in one line, so a `tests/` zone does not bury the
  useful entries. Reuses `specy_road.impact`'s import graph
  (`python_sources`, `module_names`, `imported_names`), read one level.
  Degrades to one line outside git; says `_none found (Python imports only)_`
  when nothing imports a zoned file.
- `docs/roadmap-authoring.md`: the `touch_zones` field row now says how to
  choose zones (read the code; files, directories ending in `/`, or globs;
  never a bare prefix; add importers whose calls change, as listed under
  **Call sites**) and documents the new warnings; the Registry and brief
  section mentions the call-site list. The file was at its 400-line cap, so
  both edits extend existing lines; no line was added or removed.

## Touch zones (final list)

The leaf's zones plus two **new modules**, created because
`validate_roadmap_checks.py` (392/400 lines) and `generate_brief.py`
(427/450) had no room for the logic:

- `specy_road/bundled_scripts/roadmap_crud_ops.py`
- `specy_road/bundled_scripts/validate_roadmap_checks.py`
- `specy_road/bundled_scripts/generate_brief.py`
- `specy_road/bundled_scripts/touch_zone_tracked.py` **(new)**
- `specy_road/bundled_scripts/brief_call_sites.py` **(new)**
- `docs/roadmap-authoring.md`
- `tests/`

No file outside these was edited. Not covered (outside the zones, not required
by A1's "add-node, edit-node"): the PM GUI's edit path calls
`edit_node_set_pairs` directly, so it gets validate's prefix warning but not the
add/edit-only untracked-zone line.

## Verification

- `python -m pytest -q tests/test_touch_zone_tracked.py tests/test_brief_call_sites.py` — 22 passed
- `specy-road file-limits` — OK
- `ruff check` on the changed Python files — clean
- `python -m pytest -n auto -q` — 3341 passed, 2 skipped
- Ran the prefix check over the `sr/` roadmap and the dogfood fixture: no
  prefix warnings; the untracked-zone helper finds only Not Started zones that
  name files their work will create (author-time only, so not printed by
  validate).
- `specy-road brief M11.70` renders the new section (adds ~1 KB with this
  leaf's zones).

## Added

### Helpers
- `touch_zone_tracked.Tracked` — tracked paths in both root forms, sorted, with `starting_with` (bisect prefix scan) and `matches` (file, tracked or on-disk directory, or glob); one place both checks read.
- `touch_zone_tracked.tracked_files` — `git ls-files -z` at the git root plus project-relative forms; `None` outside git so both checks stay silent.
- `touch_zone_tracked.prefix_of` — tracked files a zone is only a name prefix of; the A1 example case.
- `touch_zone_tracked._glob_for` — the glob suggestion, with the shared extension.
- `touch_zone_tracked._is_settled` / `_clean` — skip Complete/Archived/Cancelled nodes; normalise zones (a local copy because `validate_touch_zones._is_settled` is private and outside the zones).
- `touch_zone_tracked.warn_zone_prefixes` — validate's one-line prefix warning (A1, validate and every add/edit).
- `touch_zone_tracked.untracked_zones` / `warn_untracked_zones` — the add-node/edit-node warning for the written node (A1).
- `touch_zone_tracked.GLOB_HINT` — shared wording that zones may be globs and prefixes are not supported (A1's "say in the warning").
- `brief_call_sites.direct_importers` — one-level importers per target using `impact`'s import parser (A2).
- `brief_call_sites.call_site_lines` / `_importer_line` — the `### Call sites` section with caps (A2).

### Branches and guards
- `Tracked.matches`: `ValueError`/`OSError` on the directory probe reads as a match — an advisory check must not fail a write.
- `prefix_of`: a zone ending in `/`, or containing glob characters, is never a prefix — `/` states directory intent.
- `untracked_zones`: an absolute or `..` zone is always reported (it can match nothing in the repo); prefixes are left to validate's line to avoid two lines for one zone.
- `cmd_edit`: the author-time check runs only when the `--set` pairs include `touch_zones`, so unrelated edits do not repeat it.
- `call_site_lines`: one line when git cannot read the tree; `FILE_CAP` / `IMPORTER_CAP` truncation with counts; zoned files imported only from inside the zones collapsed into a count.
- `_section_touch_zone_instruction` now takes `root` and appends the call sites only when the node has zones.

### Mocks
- `test_long_lists_are_capped_and_counted` monkeypatches `IMPORTER_CAP` to 1 to exercise truncation without a large fixture.

### Tests
- `tests/test_touch_zone_tracked.py` — prefix warning text, glob suggestion and single-line shape; files, dirs, globs and new files are not prefixes; settled nodes skipped; silent outside git; untracked-zone selection (globs, untracked dirs, `..`, prefixes left out); nested-project root forms; `add-node` CLI warns for a prefix and an untracked zone and is quiet for good zones; `edit-node` CLI warns only when it writes zones.
- `tests/test_brief_call_sites.py` — one-level importers with relative imports; outside named / inside counted / inside-only collapsed; none found; outside git; caps; the brief's section 7 carries the list; no list without zones.
