# Implementation summary: M5.2 — stale-command-check

base: `cf1e222d58bdeb60bc0cb6c45a08b7649d07011e` · branch: `feature/rm-stale-command-check`

## What changed

`specy-road validate` now prints one non-fatal `agents: warning — …` line for each distinct
`specy-road <name>` or `specyrd <name>` that a project's own `AGENTS.md` or `CLAUDE.md` tells agents
to run when neither CLI registers that name. The check reads `AGENTS.md` and `CLAUDE.md` at both the
project root and the git root, because `CLAUDE.md` sits at the git root in a nested `sr/` layout. Paths
are reported relative to the git root, for example `sr/AGENTS.md`.

- **A1.** `warn_unregistered_commands(root)` in `validate_roadmap.py`, called from `validate_at`
  next to the other `AGENTS.md` checks. The managed block is dropped first with
  `managed_block._split(…, HTML_COMMENT)`, as the planning sheet says: the existing staleness
  warning already covers a block written by another version. The registered set comes from
  `cli._known_commands()` plus `version`, which `main` accepts as an alias of `--version`. The
  `specyrd` set is read from `specyrd_cli._build_parser()`'s subparsers, so it cannot drift when a
  `specyrd` subcommand is added.
- **A2.** `REPLACED_COMMANDS` in `cli.py` maps names that are not registered to what replaces
  them, and the warning names the replacement. Each entry comes from the toolkit's own history:
  - `grind` becomes `grind-session`. It is the common guess, and the CHANGELOG's did-you-mean
    entry cites it.
  - `pm-sync` becomes `sync`. It is still cited in a design note.
  - `backfill-activity` was removed in `4207281` because last-worked dates are now derived from
    git. The warning says nothing replaces it.

  For any other unknown name, the warning points to `<tool> --help`.
- **A3.** The check only prints to stderr, so validation still passes; only `--strict`, which fails
  on any warning by design, turns it into a failure. To avoid false positives, it matches only
  inside inline code spans and fenced blocks, and only at command position: the start of the
  code, after `$`, `;`, `&`, `|` or `(`, or after `uvx`, `run` or `exec`.
  - Plain prose such as "the specy-road toolkit" was the dominant false positive in a scan of
    the repo's Markdown (about 60 distinct words), so prose is not scanned.
  - Inside code, a comment like `# specy-road files omit…` and the managed-block marker
    `>>> specy-road managed block` are not matched.
  - The test runs the scanner over the toolkit's `AGENTS.md`, `CLAUDE.md`, `README.md`,
    `docs/*.md`, `suggested_prompts/*.md` and every template `.md`, and finds nothing.
  - `specy-road validate` on this checkout (`sr/`) adds no new lines.

Known limits, by choice: prose mentions without backticks are not checked, and second-level
subcommands are not checked (`specy-road worker frob` passes because `worker` exists).

## Touch zones

Final list: `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/cli.py`, `tests/`.
`specy_road/managed_block.py` was listed but did not need changing: `_split` is imported as is.

## Verification

- `python -m pytest -q`: 2258 passed, 2 skipped.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests scripts`: clean.
- `scripts/check_test_private_imports.py`: 0 new.
- `scripts/check_clones.py` could not run here because `pylint` is not installed.

## Added

- Helper `_code_spans` (validate_roadmap.py): yields fenced-block lines and inline code spans, so only code is scanned (A3).
- Helper `unregistered_commands` (validate_roadmap.py, public): the scanner; public so tests reach it without private imports.
- Helper `warn_unregistered_commands` (validate_roadmap.py, public): the A1 warning, wired into `validate_at`.
- Regexes `_FENCE`, `_INLINE_CODE`, `_COMMAND` (validate_roadmap.py): code detection plus the command-position rule that keeps prose and comments out (A3).
- Table `REPLACED_COMMANDS` (cli.py): the A2 alias/deprecated-name table, next to the command set it complements.
- Guard `if not path.is_file(): continue`: most projects have only one of the two files, and the test's tmp git root has no `AGENTS.md`.
- Guard `except UnicodeDecodeError: continue`: a non-UTF-8 agent file; reached by `test_an_agent_file_that_is_not_utf8_is_skipped`.
- Branch: three-way advice (replacement / removed with none / `--help`): A2 wording; all three are asserted in the end-to-end test.
- Mocks: none.
- Test `test_validate_warns_for_each_unregistered_command_and_still_passes`: A1 + A2 + A3 end to end through the validate script on a nested `sr/` copy of the dogfood fixture (exit 0, exact warning lines, managed block skipped, prose/comment/`version`/`specyrd init` not flagged, `CLAUDE.md` at the git root).
- Test `test_each_replaced_name_is_unregistered_and_its_replacement_is_not` (parametrized over the table): keeps the alias table honest as commands change.
- Test `test_no_false_positive_on_the_toolkits_own_docs`: A3 on the toolkit's agent files, README, docs, prompts and templates.
- Test `test_an_agent_file_that_is_not_utf8_is_skipped`: reaches the `UnicodeDecodeError` guard.
