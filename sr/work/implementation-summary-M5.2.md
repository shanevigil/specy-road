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
  on any warning by design, turns it into a failure. An unregistered command-shaped token is
  reported whatever follows it. A registered command is never reported. Prose is not a command when
  the product name is preceded by a determiner, possessive, or preposition (the, a, an, this, that,
  these, those, other, any, all, every, each, its, our, your, their, own, of, with, in, for, from,
  about). A code span, a fenced block, a list item, or a run verb (run, exec, execute, invoke, uvx)
  still reports after one of those words. A token followed by the word command or subcommand
  reports even inside that noun phrase (`Use the specy-road frob command.`). An ATX heading is a
  title unless it opens with the tool or a run verb, so `# AGENTS — specy-road toolkit repository`
  is not a command. The rule is in the
  `unregistered_commands` docstring and in `docs/install-and-usage.md`.
  - `unregistered_commands` on this repository's `AGENTS.md` and `CLAUDE.md` reports nothing.
  - `specy-road validate` on this checkout adds no stale-command line.

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

## Review round 4

The same reviewer blocked A1 at `a8b4a91`: an unknown command followed by an unquoted positional
argument (`specy-road frob M1.2`, `specy-road frob somefile.md`) was not reported. The trailing-context
heuristic is gone. Those two strings warn. `the specy-road toolkit is` does not. `specy-road validate
--strict` does not, because `validate` is registered.

## Review round 5

The same reviewer blocked A1 at `0d92dc5` both ways. `PROSE_NOUNS` hid `Run specy-road project now.`
because `project` was on the list, and it reported `other specy-road formats` in this repo's
`CLAUDE.md` because `formats` was not. The noun list is gone. The word before the product name
decides: a determiner, possessive, or preposition is a noun phrase; code, a fenced block, a list
item, and a run verb still report.

## Review round 6

The same reviewer blocked A1 at `1729432`: `Use the specy-road frob command.` is a noun phrase
(determiner before the product name) whose token is followed by the word `command`, and the
determiner rule hid it. A1 on `origin/WIP/improvements-0-3-1` (`5b4ec8e`) now states the same
rule. A token followed by `command` or `subcommand` reports even inside a noun phrase.
`the specy-road toolkit command set` also reports, because `toolkit` is not registered; that
warning is acceptable. `unregistered_commands` on this repository's `AGENTS.md` and `CLAUDE.md`
is still empty.

## Touch zones

Final list: `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/cli.py`, `tests/`,
`docs/install-and-usage.md` (the noun-phrase rule, which this round asked to document).
`specy_road/managed_block.py` was listed but did not need changing: `_split` is imported as is.

## Verification

- `python -m pytest -q` (after review round 1): 2258 passed, 2 skipped. Not re-run after round 2.
- `python -m pytest -q tests/test_validate_stale_commands.py` (after review round 6): 7 passed.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests scripts`: clean.
- `scripts/check_test_private_imports.py`: 0 new.
- `scripts/check_clones.py` could not run here because `pylint` is not installed.

## Added

- Sets `_NOUN_PHRASE` and `_RUN_VERB` (validate_roadmap.py): the determiner/possessive/preposition words that make a noun phrase, and the run verbs that still count as a command after one of those words (A1, A3).
- Helper `_preceding_words` (validate_roadmap.py): the last two words before the product name, so "the specy-road toolkit" and "run the specy-road project" are told apart.
- Helper `_list_command` (validate_roadmap.py): a list item whose text is the command (`- the specy-road frob`) still reports; a noun phrase later in a long bullet does not.
- Helper `_heading_title` (validate_roadmap.py): an ATX heading is a title unless it opens with the tool or a run verb, so this repo's `# AGENTS — specy-road toolkit repository` is quiet (A3).
- Helper `_followed_by_command_word` (validate_roadmap.py): the token is a command when the next word is `command` or `subcommand`, even after a determiner (A1).
- Helper `_reports` (validate_roadmap.py): code, fences, list commands, run verbs, and a following `command`/`subcommand` report; a noun-phrase word or a heading title does not.
- Helper `_command_mentions` (validate_roadmap.py): walks every line and yields the tokens `_reports` keeps (A1).
- Helper `unregistered_commands` (validate_roadmap.py, public): drops registered names. Its docstring states the noun-phrase rule.
- Helper `warn_unregistered_commands` (validate_roadmap.py, public): the A1 warning, wired into `validate_at`.
- Regexes `_FENCE`, `_INLINE_CODE`, `_MENTION`, `_LIST_ITEM`, `_HEADING` (validate_roadmap.py): fences, inline code, the lookbehind mention, a list marker, and an ATX heading.
- Table `REPLACED_COMMANDS` (cli.py): the A2 alias/deprecated-name table, next to the command set it complements.
- Guard `if not path.is_file(): continue`: most projects have only one of the two files, and the test's tmp git root has no `AGENTS.md`.
- Guard `except UnicodeDecodeError: continue`: a non-UTF-8 agent file; reached by `test_an_agent_file_that_is_not_utf8_is_skipped`.
- Branch: three-way advice (replacement / removed with none / `--help`): A2 wording; all three are asserted in the end-to-end test.
- Mocks: none.
- Test `test_validate_warns_for_each_unregistered_command_and_still_passes`: A1 + A2 + A3 end to end through the validate script on a nested `sr/` copy of the dogfood fixture (exit 0, exact warning lines, managed block skipped, `frob` / `does-not-exist` / a fenced `files` flagged, `the specy-road toolkit is` and `specy-road validate` not flagged, `CLAUDE.md` at the git root).
- Test `test_a_noun_phrase_is_quiet_and_a_command_is_not`: `Run specy-road project now.`, `Then specy-road frob.`, `specy-road frob M1.2`, `- the specy-road frob`, and `Use the specy-road frob command.` (and the same with `subcommand`) warn; `other specy-road formats (templates...)` and `the specy-road toolkit is` and `specy-road validate --strict` do not.
- Test `test_each_replaced_name_is_unregistered_and_its_replacement_is_not` (parametrized over the table): keeps the alias table honest as commands change.
- Test `test_the_toolkits_agent_files_report_nothing`: `unregistered_commands` on this repository's `AGENTS.md` and `CLAUDE.md` is empty (A3). Replaces `test_prose_nouns_in_the_toolkits_docs_are_not_reported`, which checked the deleted noun list.
- Test `test_an_agent_file_that_is_not_utf8_is_skipped`: reaches the `UnicodeDecodeError` guard.
