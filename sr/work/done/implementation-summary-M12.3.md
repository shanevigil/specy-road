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

## Fix round 1 (cursor-grok-4.6-high block at 6a837cf1)

- **Correctness/regression:** `GITIGNORE_LINES` in `specy_road/agent_ignores.py` (added to the zones by the coordinator) now lists `work/chores/garden.json` and nothing else under `work/chores/`. Chore start/close records are left as they were; no doc says they are tracked or ignored, so this round does not decide that. Nested projects get `sr/work/chores/garden.json` through the existing `_prefixed` step, as the runtime dirs do. The block's note names the record. I did not add it to `RUNTIME_WORK_DIRS`, because that tuple also drives the directory list in the agents' prompt prose (`runtime_dirs_prose`). Once ignored, the record never shows in `git status`, so delegate's dirty check and the executor/reviewer preconditions pass. An older managed block gains the line through `specy-road refresh-stubs`, and the docs now say so. This toolkit's own root `.gitignore` block is outside the zones, so it gets the line on its next `refresh-stubs`.
- **Test integrity:** `garden_repo()` no longer commits `work/`. It replaces `.gitignore` with what `apply_agent_ignores` writes (the managed block only, plus `.cursorindexingignore`). The A1 test now asserts empty `git status --porcelain --untracked-files=all`, that `git check-ignore work/chores/garden.json` succeeds, and that the public `dirty_check("", "M1.1")` clean-tree command prints nothing after a garden run. Red-green: with the `agent_ignores.py` change reverted, `test_garden_prints_one_line_per_finding_and_writes_nothing_tracked` fails.
- **Docs:** the cadence paragraph now says the managed block ignores the record (not "gitignored").

### Added (fix round 1)

- `GITIGNORE_LINES` entry `work/chores/garden.json`, plus a line in the block's note: the review's required ignore rule.
- In `garden_repo()`: the managed-ignore setup and the `check-ignore` and `dirty_check` assertions in the A1 test: lock the fix against the scaffold's real lines.

## Fix round 2 (gpt-6.1-sol block, R1–R3)

- **R2:** the run record moved to `work/chores/.garden.json`. A chore slug must start with a letter or digit, so no chore record can be that file. The reserved `garden` slug is dropped: `_SLUG` and its message are back to the base version. The managed ignore line in `agent_ignores.py`, the schema description and the docs now name `.garden.json`. Test `test_a_chore_named_garden_survives_a_garden_run` starts a `garden` chore through the public `chore start`, runs `chore garden`, and checks that the chore loads unchanged, takes a `worker delegate`, closes and writes `garden.md`. It replaces `test_garden_is_not_a_chore_slug`, which pinned the reservation this round removes.
- **R1:** garden's stale-command path set is now `validate`'s `agent_files()` plus `.specyrd/AGENTS.md`; `validate`'s own set is unchanged. Test `test_garden_reports_stale_commands_in_the_managed_rules_file` plants `specy-road nonexistent-garden-probe` in `.specyrd/AGENTS.md`, checks that `chore garden --json` reports it at line 7, and checks that `agent_files()` still leaves that file out.
- **R3:** `open_chores` calls `assert_pm_nodes_not_milestone_locked(nodes, under)` before writing anything. A refusal becomes a `WorkerError`, so the CLI prints `error: --under <id>: … Pass another --under parent, or run after the milestone closes.` and exits 1. Test `test_open_chores_refuses_a_parent_in_a_locked_milestone[active|pending_mr]` runs the CLI and checks that the roadmap and planning files are byte-identical afterwards. Docs mention the refusal.
- Red-green: with `chore_garden.py` and `chore_cli.py` reverted to the round-1 commit, all four new tests fail.

### Added (fix round 2)

- `chore_garden.open_chores` milestone-lock guard (`assert_pm_nodes_not_milestone_locked`): R3, the same lock `add-node` and brainstorm promotion apply.
- `RULES_MD` in `stale_command_findings`' path set: R1.
- `record_path` docstring: explains why a dot-file cannot collide with a chore.
- Tests: the three R1–R3 tests above (four cases). Removed: `test_garden_is_not_a_chore_slug`, because the behaviour it pinned is removed.

## Fix round 3 (gpt-6.1-sol block, R4)

- **R4:** garden no longer calls `file_unregistered_commands`, which drops managed blocks. `validate_stale_commands.line_unregistered_commands(lines)` exposes the same occurrence scanner (`_occurrences`) for any numbered line source. Garden feeds it `chore_garden._numbered_lines(path)`, which is the whole file, managed blocks included, at its original line numbers. `validate` still uses `file_unregistered_commands`, unchanged, so it keeps skipping managed blocks. Test `test_garden_reports_mentions_inside_managed_blocks_and_validate_still_skips_them` puts a managed block with `specy-road managed-probe` at line 5 of `AGENTS.md`, `CLAUDE.md` and `docs/guide.md`. Garden reports all three at line 5, and `warn_unregistered_commands` prints none.

## Fix round 3: coverage audit

Each input garden reads, whether the scan sees the whole file, whether line numbers are right, and what (if anything) filters it upstream:

| Scan | Input | Whole file? | Line numbers | Upstream filter | Result |
| --- | --- | --- | --- | --- | --- |
| stale-command | `docs/**/*.md` under the project root and the git root (`rglob`, dot-dirs included) | yes, after R4 | git's (`\n` only) | none; non-UTF-8 files are skipped, as `validate` skips them | **fixed (R4)**: managed blocks in docs were dropped |
| stale-command | `AGENTS.md` and `CLAUDE.md` at project and git roots, `.specyrd/AGENTS.team.md` (`agent_files()`) | yes, after R4 | git's | none | **fixed (R4)**: managed blocks were dropped |
| stale-command | `.specyrd/AGENTS.md` (`RULES_MD`) | yes | git's | none | fixed in round 2 (R1); whole file after R4 |
| stale-command | (any of the above) | — | — | the occurrence scanner's own rules (fenced code, mandatory contexts), shared with `validate` by design | by design |
| stale-command and advisory-rule | line splitting | — | `str.splitlines()` also broke on U+2028, form feed and a lone CR, so later line numbers drifted from git's | — | **fixed**: `_numbered_lines` splits on `\n` only and strips a trailing CR. Test `test_garden_line_numbers_count_only_newlines` |
| advisory-rule | `agent_files()`, `.specyrd/AGENTS.md`, and the three `templates/specyrd/` sources when they are inside the checkout | yes (never block-filtered) | git's (now `_numbered_lines`) | matches only whole-line `PROVENANCE` comments, the same rule `strip_provenance` uses; rendered files carry none, which is why the templates are read | by design |
| ratchet-grew | every `policy.ratchet_paths` entry: `git diff --raw --no-relative --no-renames <tag> HEAD` with no pathspec (whole repo), whole blobs | yes | n/a (a count of added lines) | non-UTF-8 diffs are skipped (shared `integrity` behaviour). An unreadable integration-branch policy made `integration_ratchet_paths` return `[]` silently | **fixed**: a `policy_source` error is now a one-line note, as no-tag is. Test `test_garden_says_why_when_the_ratchet_policy_is_unreadable` |
| ratchet-grew | the base tag | — | — | `git describe --tags --abbrev=0`: the newest tag reachable from HEAD; no tag gives a note | by design |

Not scanned, because A1 does not name them: `.claude/CLAUDE.md`, `CLAUDE.local.md`, `README.md` and other non-`docs/` Markdown.

### Added (fix round 3)

- `validate_stale_commands.line_unregistered_commands()`: the shared occurrence scanner over a caller's line source (R4).
- `chore_garden._numbered_lines()`: garden's whole-file line source, numbered as git numbers lines; it returns nothing for a missing or non-UTF-8 file (R4, audit).
- `ratchet_findings` `policy_source` guard and note: an unreadable policy is no longer a silent clean scan (audit).
- Tests: `test_garden_reports_mentions_inside_managed_blocks_and_validate_still_skips_them`, `test_garden_line_numbers_count_only_newlines`, `test_garden_says_why_when_the_ratchet_policy_is_unreadable`, and the `_garden_json` helper. All three tests fail with `chore_garden.py` at the round-2 commit.

## Fix round 4 (gpt-6.1-sol block, R5; coordinator RCA class B)

- **Write path:** `open_chores` no longer builds nodes itself (`append_node_to_chunk`, `new_node_key`, `next_sibling_order`, its own parent and lock checks are all gone). It runs the `add-node` command: `chore_garden._add_node` calls `roadmap_crud.main(["--repo-root", root, "add-node", ...])`, the same entry point as `specy-road add-node`. So `cmd_add` makes every check from one place: id pattern, duplicate id, parent exists (`_resolve_parent`), milestone lock (`_refuse_if_milestone_locked`), codename pattern, sibling order, codename and planning-sheet derivation, chunk routing, and the post-write validation for unique titles, codenames and title slugs. No `add-node` check needed factoring out, because its CLI entry is callable as is; `roadmap_crud_ops.py` (outside the zones) is unchanged. The one thing `add-node` does not do is choose an id (`--id` is required), so garden passes `next_child_id(nodes, under)`, the allocator brainstorm promotion uses. `add-node`'s write report on stdout is discarded. A refusal (exit 1) becomes `error: --under <P>: add-node refused the <class> leaf: <its reason>. Pass another --under parent, or fix what add-node names, then run again.` and garden exits 1. The explicit lock and parent checks from round 2 are removed, since `add-node` makes them.
- **Identity and numbering:** `chore_garden._generation(cls, codename, title)` names a node's generation when its codename is `garden-<cls>` or `garden-<cls>-N`, or its title is `<class title>` or `<class title> (N)`. The unnumbered form is generation 1. A node is a garden leaf of the class when either field says so, under any parent. **Idempotency:** while any *live* (`load_roadmap`, so not archived) leaf of the class is not Complete, garden adds nothing and prints that leaf's id. **Next generation:** the highest generation across all live nodes (any status) and every archived node (`archive_index.iter_archived_summaries`; archived summaries keep the title, not the codename), plus 1. Survivors are never counted.
- **Deleted nodes:** `archive-node --hard-remove` removes a node and leaves no ledger, so no "deleted but indexed" state exists. A deleted leaf's title and codename are free again, so reusing its number cannot collide.

## Fix round 4: lifecycle audit

All rows run through the public CLI (`chore garden --open-chores --under …`); setup uses `edit-node`, `add-node` and `archive`. Ids are as in the tests, under `M1.1` unless noted. Only the stale-command class is shown; the other classes behave the same.

| Row | State before the run | Expected result | Test |
| --- | --- | --- | --- |
| 1 | no prior leaf | **add** `M1.1.1`, `Garden: stale command mentions`, codename `garden-stale-command` (generation 1, no suffix) | `test_chore_mode.py::test_open_chores_adds_one_leaf_per_class_then_nothing` |
| 2 | open leaf (Not Started) | **skip**, printing `stale-command: M1.1.1 is still open; added nothing`; roadmap byte-identical | same test, second run |
| 3 | In Progress / claimed leaf | **skip**, printing its id; byte-identical | `test_chore_garden_lifecycle.py::test_in_progress_leaf_is_skipped` |
| 4 | Complete leaf (generation 1) | **add** the next child id, `… (2)`, `garden-stale-command-2` | `test_complete_then_archived_takes_the_next_unused_number` (first half) |
| 5 | Complete then archived: 1 archived, 2 Complete (**R5**) | **add** exactly `… (3)`, `garden-stale-command-3`; the second run **skips**, printing gen 3's id; byte-identical | `test_complete_then_archived_takes_the_next_unused_number` |
| 6 | gaps: 1 archived, 2 Complete, 3 open | **skip**, printing gen 3's id; once 3 is Complete, **add** `… (4)` | `test_generations_with_gaps_skip_the_open_one_then_number_past_the_highest` |
| 7 | leaf hand-edited: title changed, codename kept; or codename changed, title kept | **skip**, printing its id (either field keeps the identity) | `test_hand_edited_leaf_keeps_its_identity_by_codename_or_title` |
| 7b | leaf hand-edited: title and codename both changed | it is no longer a garden leaf: **add** generation 1 under the freed name (`garden-stale-command`) | same test |
| 8 | garden leaf under a different parent (`M1.1`), run with `--under M2` | open: **skip**, printing the `M1.1.x` id; Complete: **add** `M2.1`, `… (2)` | `test_leaf_under_another_parent_counts` |
| 9 | parent in a milestone whose execution is `active` / `pending_mr` | **refuse**: exit 1, `add-node refused the stale-command leaf: roadmap node 'M1.1' is inside milestone subtree …. Pass another --under parent, or fix what add-node names, then run again.`; roadmap and planning byte-identical | `test_milestone_locked_parent_is_refused[active,pending_mr]` |
| 10 | parent missing (`--under M9`) | **refuse**: exit 1, `add-node refused the stale-command leaf: parent_id 'M9' not found in roadmap. Pass another --under parent, …`; byte-identical | `test_missing_parent_is_refused` |

Refusals happen on the first class's `add-node`, before anything is written. With `chore_garden.py` at the round-3 commit, six of the eight lifecycle tests fail. Rows 5, 6 and 7 fail on numbering or identity, and rows 9 and 10 fail on the message. Rows 3 and 8 are behaviour the old code already had.

### Added / removed (fix round 4)

- `chore_garden._generation()`: one rule for a garden leaf's identity and generation, by codename or title (row 7) and readable from archived summaries (rows 5 and 6).
- `chore_garden._add_node()`: runs the `add-node` command and returns its refusal; this replaces the custom node write (class B root cause).
- `open_chores` rewritten: live-only idempotency, numbering at max + 1 over live and archived nodes, and `add-node` refusals turned into `WorkerError`.
- Removed from `open_chores`: `append_node_to_chunk`, `new_node_key`, `next_sibling_order`, the round-2 parent-exists check and the `assert_pm_nodes_not_milestone_locked` call (`add-node` makes both checks).
- New `tests/test_chore_garden_lifecycle.py`: the rows above. It replaces `test_chore_mode.py::test_open_chores_files_a_numbered_leaf_once_the_last_is_complete` (row 4, which edited JSON by hand) and `::test_open_chores_refuses_a_parent_in_a_locked_milestone` (row 9, whose message changed). Both rows are covered there through the public CLI.
- No new production module: `chore_garden.py` stays under the cap.
