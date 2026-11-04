# Implementation summary: M12.3 — scheduled gardening chores

Branch `feature/rm-scheduled-gardening-chores-that-find-drift-and-open-small-chore-leaves`, base `6d080df2`.

## What changed

- **A1: `specy-road chore garden`** is a new subparser in `chore_cli.py`, so `cli.py` needs no new entry. The scans live in a new module, **`specy_road/bundled_scripts/chore_garden.py`**, because `chore_cli.py` plus the garden code would have gone over the 400-line `file-limits` cap. **Please add that path to the touch zones.** The command prints one line per finding, `<class>: <path>:<line>: <detail>`, with git-root-relative paths. For `ratchet-grew` the form is `<path>: +N line(s) since <tag>`, because a baseline's growth has no single line. The command exits 0 whether or not it finds anything, and `--json` gives the same report for machines. The three scans:
  - `stale-command`: runs the scanner `validate` already uses over `docs/**/*.md` (at the project root and the git root) and the agent files `validate` reads. I factored the file list out of `warn_unregistered_commands()` into `agent_files()`, and the per-file scan into `file_unregistered_commands()`. `validate`'s path set and output are unchanged.
  - `advisory-rule`: one finding per provenance comment marked `| enforced: advisory`. It reads the managed agent files (`AGENTS.md`, `CLAUDE.md`, `.specyrd/AGENTS.md`, the team file). It also reads the three `templates/specyrd/*` sources, but only when they sit inside this checkout. The reason: rendering runs `strip_provenance`, so a rendered consumer file normally carries no such comments, and the templates are where the rules live.
  - `ratchet-grew`: `_ratchet_findings(root, <newest tag>, "HEAD", integration_ratchet_paths(root))`. With no tag it reports nothing and prints one note to stderr.
- **A2: `--open-chores --under <PARENT>`** adds at most one leaf per finding class under `PARENT`, through `append_node_to_chunk` together with `next_child_id`, `next_sibling_order` and `new_node_key`. The title comes from the class, the codename is `garden-<class>`, and there is one acceptance line per finding path (the first 10, then a count). The touch zones are the finding paths. It is idempotent: while a non-Complete node with that codename exists, it adds nothing and prints that node's id. Because titles and codenames must be unique, a class filed again after its leaf is Complete becomes `garden-<class>-N` with title `… (N)`. It never edits code, docs or agent files. Using `--open-chores` without `--under` is refused with exit 1.
- **A3: cadence.** The new optional key `policy.garden_cadence_days` (integer, at least 1) is in `templates/project/schemas/orchestration.schema.json`. Every garden run writes `{"last_run": <date>}` to `work/chores/garden.json`, which is gitignored. `validate_at` calls `warn_garden_due()`, which uses the research-register arithmetic: the warning fires when `(today - last_run).days > cadence`, or when there is no record. The warning reads `garden: warning — gardening due: last run …, every N days; run \`specy-road chore garden\``. An unset key gives no warning. `docs/orchestration-chores.md` gains a quickstart bullet and a "Gardening" section covering the scans, `--open-chores --under`, the cadence key and an unattended cron/CI recipe.
- The chore slug `garden` is reserved (`_SLUG`) so that `load_chore("garden")` never reads the run record as a chore.

## Final touch zones

`specy_road/bundled_scripts/chore_cli.py`, `specy_road/bundled_scripts/chore_garden.py` (new, for the file-limits cap), `specy_road/bundled_scripts/validate_stale_commands.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `docs/orchestration-chores.md`, `specy_road/templates/project/` (the schema only), `tests/`.

## Notes for reviewers

- **Flags are not checked.** A1 says "command or flag". The plan's approach reuses `unregistered_commands()`, which checks only command names, and specy-road has no central record of each command's flags. The scan therefore reports unregistered commands only, and the docs say so. Checking flags would need a per-command parser registry, which would be new scope.
- **Copy of the schema outside the zones.** `sr/schemas/orchestration.schema.json` is the toolkit roadmap's copy of the schema. `specy-road validate` now warns that it differs from the bundled schema until someone runs `specy-road refresh-schemas`. It is outside the touch zones, so I left it alone.
- **Line budget in `validate_roadmap.py`.** The file was 399 of 400 lines. I collapsed the four-line `validate_stale_commands` import onto one line, which makes room for the new import and call; it ends at 398. No comment or docstring was removed.
- **Lazy imports.** `open_chores` imports the roadmap CRUD helpers lazily, because `roadmap_crud_ops` imports `validate_roadmap`, which now imports `chore_garden`. `chore_cli.cmd_garden` imports `chore_garden` lazily because `chore_garden` imports `chores_dir` from `chore_cli`.
- **Checks run:** `pytest -n 4` (3966 passed), `specy-road file-limits` (OK), `ruff check` on the changed modules (passed), and `specy-road validate` for the fixture and for `sr/` (exit 0).

## Added

- `validate_stale_commands.agent_files()`: `validate`'s agent-file list, factored out so `validate` and garden share one scanner.
- `validate_stale_commands.file_unregistered_commands()`: the per-file scan (outside the managed block; nothing for a missing or undecodable file), shared by `validate` and garden.
- `validate_stale_commands.stale_command_advice()`: `validate`'s advice text, factored out so garden's finding detail matches it.
- `chore_garden.Finding` and `.text()`: one finding and its printed line; with no line number it prints `path: detail`, which `ratchet-grew` uses.
- `chore_garden.stale_command_findings()`: the A1 stale-command scan over docs plus agent files; removes a line's repeated mention of the same command.
- `chore_garden.advisory_rule_findings()`: the A1 advisory-rule scan; templates count only when inside the checkout, because rendered files have their provenance stripped; skips unreadable files.
- `chore_garden.ratchet_findings()`: the A1 ratchet scan; the guard for an empty `ratchet_paths` returns early, and with no tag it returns one note.
- `chore_garden.scan()`, `garden()`, `as_json()`, `record_path()`: run the scans, open chores when asked, write the run record, and give the JSON form.
- `chore_garden._acceptance()`: per-path acceptance lines, capped at 10 plus an overflow count (A2).
- `chore_garden.open_chores()`: the A2 add-node write. Guards: an unknown `--under` is refused; an open node for the class is skipped (idempotency); a numbered generation once the last leaf is Complete, because titles and codenames are unique.
- `chore_garden.garden_due()` and `warn_garden_due()`: the A3 cadence check and its `validate` warning; an unreadable or malformed record counts as never run.
- `chore_cli.cmd_garden()` and the `garden` subparser: the CLI. Guard: `--open-chores` without `--under` is refused.
- `chore_cli._SLUG` excludes `garden`: so the run record is never loaded or started as a chore.
- Schema `policy.garden_cadence_days`: the A3 key.
- Test helpers `garden_repo()` and `_roadmap_bytes()` in `tests/test_chore_mode.py`: a fixture repo with one finding per class, and a byte snapshot of the roadmap and planning trees.
- `test_garden_prints_one_line_per_finding_and_writes_nothing_tracked`: A1, all three scans, text and JSON, nothing tracked written.
- `test_garden_without_a_tag_skips_the_ratchet_scan_and_says_why_once`: A1, the no-tag case.
- `test_open_chores_adds_one_leaf_per_class_then_nothing`: A2, one leaf per class with its title, acceptance and zones; the second run leaves the roadmap byte-identical; `--under` is required.
- `test_open_chores_files_a_numbered_leaf_once_the_last_is_complete`: A2, the numbered generation after Complete.
- `test_garden_cadence_warns_when_due_and_names_the_command`: A3, unset, never run, on the cadence boundary, past due, `validate_at` printing the warning, and a run resetting the clock.
- `test_garden_is_not_a_chore_slug`: the reserved slug.
- `test_validate_and_garden_share_the_scanner_and_only_garden_reads_docs` in `tests/test_validate_stale_commands.py`: `validate`'s path set is unchanged, garden reads `docs/**`, and both use the same scanner.
- Mocks: none.
