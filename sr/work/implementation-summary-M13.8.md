# Implementation summary: M13.8

## What changed

- **A1** — New `specy_road/behaviour_changes.py`: `BehaviourChange` frozen dataclass (`since`, `command`, `flags`, `now`, `contradicts`) and `CATALOGUE` with five entries:
  1. `mark-implementation-reviewed --yes` (0.3.1rc1): `--yes` never creates a review, so an agent never approves its own work.
  2. `finish-this-task --on-complete/--override-on-complete` (0.3.1rc3): a mode that differs from the recorded one is refused without the override.
  3. `do-next-available-task --local` (0.3.1rc1): pickup does not always push.
  4. `finish-this-task --delete-branch` (0.3.1rc2): finish can delete the branch.
  5. `do-next-available-task --base` (0.1.0rc1): pickup registers on the integration branch before the feature branch exists (A4).
  The `since` versions come from the CHANGELOG sections that introduced each change. Patterns 1–4 require the command's name on the same line (pattern 3 also accepts "pickup"). Pattern 4 also needs "branch" after the "delete" phrase. Pattern 5 has no command, so a line must contain "first commit", the verb "register" (or registers/registered/registering), and claim context: feature branch, registry, claim, in-progress, or "the work".
- **A2** — New `specy_road/agent_text_report.py`: `warn_contradicted_instructions(project_root)` reads the files `validate_stale_commands.agent_files()` returns (root and git-root `AGENTS.md`/`CLAUDE.md`, plus `.specyrd/AGENTS.team.md`). It uses `managed_block.agent_file_lines_outside_block` to drop the managed block. That helper already wraps the `_split` logic and keeps the original line numbers. It prints one notice per matching source line on **stdout**: `agents: notice — <file>:<line>: says "<excerpt>"; since <since>: <now>`. When a line matches more than one entry, the `since …: …` parts are joined with `; ` in that same notice. That makes it a notice, so `--strict` does not count it. It never writes to the files.
- **A3** — `_REQUIREMENT_PIN`, `pinned_version` and `warn_if_pin_differs` moved to new `specy_road/version_pin.py`. `validate_roadmap.py` imports them back (they are still in `__all__`), so `vr.pinned_version` and `vr.warn_if_pin_differs` still work. Imports that became unused were removed. `validate_at` gains one call, `warn_contradicted_instructions(root)`, after `warn_unregistered_commands(root)`. `validate_roadmap.py` is now 359 lines (was 398).
- **A4** — `docs/roadmap-authoring.md` "Before starting implementation" steps 3 and 4 now give the real order: register on the integration branch first (push unless `--local`), then branch. The file is still 400 lines.

## Touch zones

The final list matches the PM list: `specy_road/behaviour_changes.py`, `specy_road/agent_text_report.py`, `specy_road/version_pin.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`, `docs/roadmap-authoring.md`. Nothing outside the zones changed. The callers of `validate_roadmap` outside the zones import only `validate_at`, which still works the same way.

## Rework (review by gpt-6.1-sol of 4f12fad3)

- **R1** (class: one source line matching several catalogue entries). `contradicted_lines` now yields `(line number, line, entries)` once per line, and the reporter prints one notice that lists every matching entry's current behaviour. Grouping happens where lines are produced, so no caller can emit more than one notice per line.
- **R2** (class: a catalogue pattern matching prose unrelated to the old instruction). The first-commit pattern now needs the verb "register" and claim context (feature branch, registry, claim, in-progress, the work). The historical commandless sentence "**First commit** registers the work in `registry.yaml`" still matches. The same class reached the delete-branch pattern, which now needs "branch" after the delete phrase (for example, "finish-this-task never deletes uncommitted work" no longer matches).

## Verification

- `pytest -q tests/test_behaviour_changes.py tests/test_validate_roadmap.py tests/test_validate_stale_commands.py`: 50 passed.
- `pytest -n 4 -q`: 4033 passed (after the rework).
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK. Plain `specy-road validate` on `sr/` prints no `agents: notice`.
- `specy-road file-limits`: OK.
- Red/green: with `HEAD`'s `docs/roadmap-authoring.md` restored, `test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work` fails (line 351 matches). With 4f12fad3's `behaviour_changes.py` and `agent_text_report.py`, the four new rework tests fail; with the fix they pass.

## Probes

- Every catalogue pattern checked for prose false positives. Patterns 1–2 need the command plus a specific flag (and value): fine. Pattern 3 needs pickup/do-next-available-task plus "always push": fine. Pattern 4 matched "never deletes uncommitted work": narrowed and pinned by a test. Pattern 5 matched "registers the service worker" and "Register the plugin in the first commit": narrowed and both pinned by tests.
- Pattern 5 still catches the historical commandless roadmap-authoring sentence and the CITED feature-branch sentence: pinned by tests.
- One line matching several entries, in either order: only possible through `contradicted_lines`, which now groups per line. The R1 regression gives one notice that contains both finish-this-task behaviours.
- Duplicate files: `agent_files` already de-duplicates paths when the project root is the git root, so the same line in the same file is never read twice.
- Toolkit `docs/` and `specy_road/templates/` against the narrowed pattern 5: no hits (existing test). Plain `specy-road validate` on `sr/`: 0 notices.
- Behaviour `validate_at` relies on: unchanged. It still makes the single call; only the notice text changed, and only for lines that match several entries.

## Added

### Helpers
- `behaviour_changes.BehaviourChange`, `CATALOGUE`: the tracked catalogue (A1).
- `behaviour_changes._line_with`: builds a "line contains all of these, in any order" regex, so a pattern can require the command name on the line.
- `agent_text_report.contradicted_lines`: groups the catalogue entries that match each numbered line (one tuple per line, R1); kept separate from printing.
- `agent_text_report.warn_contradicted_instructions`: validate's report (A2).
- `version_pin.py`: moved code only, nothing new (A3).

### Branches and guards
- `behaviour_changes`: claim-context term in pattern 5 and the "…branch" term in pattern 4 (R2 class).
- `agent_text_report`: skips a missing or unreadable file (`OSError`/`UnicodeDecodeError`), the same way the stale-command scan does.
- `agent_text_report`: cuts excerpts to 120 characters so a long line does not flood the notice.

### Mocks
- none

### Tests (`tests/test_behaviour_changes.py`)
- `test_every_entry_names_a_registered_command_and_flag`: each catalogue command is registered and every flag appears in that command's `--help` (A1).
- `test_cited_sentences_each_print_one_notice_outside_the_managed_block`: the four cited sentences plus the A4 sentence, spread over `AGENTS.md` and the team file, give exactly five notices with file:line and current behaviour. The same sentence inside a managed block and a clean `CLAUDE.md` give none. The files are byte-identical afterwards (A2, A4).
- `test_a_line_matching_two_entries_prints_one_notice_with_both_behaviours`: R1 regression. A finish-this-task line with `--on-complete auto` and "never deletes the source branch" gives one notice with both behaviours.
- `test_unrelated_prose_prints_no_notice` (3 cases): R2 regression ("The first commit registers the service worker.") plus the other members of the same class found under Probes.
- `test_the_historical_commandless_first_commit_sentence_is_still_reported`: the narrowed pattern 5 still reports the old init-era sentence (A4).
- `test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work`: the A4 pattern finds nothing in `docs/` or `specy_road/templates/` (A4).
