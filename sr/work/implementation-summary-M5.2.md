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
  on any warning by design, turns it into a failure. Every line outside the managed block is scanned
  for `(?<![\w/.-])(specy-road|specyrd)` plus a command-shaped token, whatever precedes the tool.
  The token is a subcommand in inline code or a fenced block (the end of the span counts as end of
  line), on a list item, or when end of line, sentence punctuation (`. , ; : ! ? )`), a flag
  (`-x` / `--name`), or a quoted or path-like argument follows it. A plain following word is not a
  command (`the specy-road toolkit is`, a `#` comment, `>>> specy-road managed block`). A token
  right after `the` / `a` / `an` is a noun phrase when the only signal is punctuation or end of line
  (`the specy-road repository.`). A colon that introduces the next list, and a wrapped line whose
  next line continues with a lowercase word, are the sentence going on.
  - The test runs the scanner over the toolkit's `AGENTS.md`, `CLAUDE.md`, `README.md`,
    `docs/*.md`, `suggested_prompts/*.md` and every template `.md`, and finds nothing.
  - `specy-road validate` on this checkout (`sr/`) adds no new lines.

## Review round 1

`gpt-5.6-sol-high` blocked A1: a plain-prose instruction such as `Run specy-road does-not-exist`,
or a capitalized one wrapped in backticks, was not flagged. Fixed in `2e0efd9` by scanning prose
after a run verb.

## Review round 2

The same reviewer blocked A1 again at `e0753ad`: the run-verb gate skipped `Then specy-road frob.`
and `- specy-road frob --flag`. The run-verb requirement is gone. Those two forms warn, and
`specy-road toolkit is …` does not.

## Review round 3

The same reviewer blocked A1 at `eb701f2`: `_PROSE_AT` allowed only one leading word, so
`Please run specy-road does-not-exist.` was missed. There is no leading-word limit. The end-to-end
validate test carries that sentence. A separate test covers the forms that are not already in the
end-to-end fixture: `run `specy-road does-not-exist``, a `uv run` code span, a blockquote with a
flag, `the specy-road toolkit is` (no warning), and `specy-road validate` at end of line (registered,
no warning).

## Touch zones

Final list: `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/cli.py`, `tests/`.
`specy_road/managed_block.py` was listed but did not need changing: `_split` is imported as is.

## Verification

- `python -m pytest -q` (after review round 1): 2258 passed, 2 skipped. Not re-run after round 2.
- `python -m pytest -q tests/test_validate_stale_commands.py` (after review round 3): 7 passed.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests scripts`: clean.
- `scripts/check_test_private_imports.py`: 0 new.
- `scripts/check_clones.py` could not run here because `pylint` is not installed.

## Added

- Helper `_plain_word_follows` (validate_roadmap.py): a following lowercase word is prose, not a subcommand (`toolkit is`, `repo, or`).
- Helper `_punctuation_kind` (validate_roadmap.py): sentence punctuation in `. , ; : ! ? )` ends a mention unless a word or markdown closer continues it (keeps C901 under the limit).
- Helper `_argument_kind` (validate_roadmap.py): a quoted or path-like argument, as against a plain word (keeps C901 under the limit).
- Helper `_trailing_kind` (validate_roadmap.py): end of line, punctuation, flag, quote, or path — the only disambiguation, with no leading-word limit (A1, A3).
- Helper `_mentions_in` (validate_roadmap.py): applies that trailing rule to one span, including a list item and inline or fenced code.
- Helper `_command_mentions` (validate_roadmap.py): walks every line outside the managed block (A1).
- Helper `unregistered_commands` (validate_roadmap.py, public): the scanner; public so tests reach it without private imports. Its docstring states the rule.
- Helper `warn_unregistered_commands` (validate_roadmap.py, public): the A1 warning, wired into `validate_at`.
- Regexes `_FENCE`, `_INLINE_CODE`, `_MENTION`, `_PLAIN_WORD`, `_FLAG`, `_LIST_ITEM`, `_DETERMINER` (validate_roadmap.py): fences and inline code, the lookbehind mention, a plain word, a flag, a list item, and `the`/`a`/`an` so `the specy-road repository.` stays a noun phrase.
- Table `REPLACED_COMMANDS` (cli.py): the A2 alias/deprecated-name table, next to the command set it complements.
- Guard `if not path.is_file(): continue`: most projects have only one of the two files, and the test's tmp git root has no `AGENTS.md`.
- Guard `except UnicodeDecodeError: continue`: a non-UTF-8 agent file; reached by `test_an_agent_file_that_is_not_utf8_is_skipped`.
- Branch: three-way advice (replacement / removed with none / `--help`): A2 wording; all three are asserted in the end-to-end test.
- Mocks: none.
- Test `test_validate_warns_for_each_unregistered_command_and_still_passes`: A1 + A2 + A3 end to end through the validate script on a nested `sr/` copy of the dogfood fixture (exit 0, exact warning lines, managed block skipped, `Then specy-road frob.`, `- specy-road frob --flag`, and `Please run specy-road does-not-exist.` flagged, `the specy-road toolkit is` / `specy-road validate` / comment / `version` / `specyrd init` not flagged, `CLAUDE.md` at the git root).
- Test `test_a_command_after_any_prefix_is_a_warning_and_a_noun_phrase_is_not`: forms the end-to-end fixture does not carry — `run `specy-road does-not-exist``, a `uv run` code span, a blockquote with `--flag` — plus `the specy-road toolkit is` (no warning) and `specy-road validate` at end of line (registered).
- Test `test_each_replaced_name_is_unregistered_and_its_replacement_is_not` (parametrized over the table): keeps the alias table honest as commands change.
- Test `test_no_false_positive_on_the_toolkits_own_docs`: A3 on the toolkit's agent files, README, docs, prompts and templates.
- Test `test_an_agent_file_that_is_not_utf8_is_skipped`: reaches the `UnicodeDecodeError` guard.
