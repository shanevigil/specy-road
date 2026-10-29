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
  about), and only when no mandatory context matched. That noun phrase is the only exclusion.
  Mandatory contexts, decided first: a code span, a fenced block, a command-led list item (the
  product name is the first token after the marker, optionally in code or emphasis, or it is
  preceded only by a run verb), a run verb (run, exec, execute, invoke, uvx), and a token
  followed by a flag, a path, a quoted argument, an id-like argument, or the word command or
  subcommand. A heading has no separate exclusion (`# Please specy-road frob` reports). A prose
  bullet that names the product mid-sentence does not (`other specy-road formats`). Each
  occurrence is reported with its file line number; repeats are not collapsed. The rule is in
  the `unregistered_commands` docstring and in `docs/install-and-usage.md`.
  - This repository's heading was `# AGENTS — specy-road toolkit repository`. With no heading
    exclusion that is `specy-road toolkit`, the same shape as `# Please specy-road frob`. The
    title is now `# AGENTS — the specy-road toolkit repository`, so the noun-phrase rule
    excludes it.
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

## Review round 7

The same reviewer blocked A1 at `1981dfa` on precedence and on deduplication. A determiner or a
heading could hide a list item and a token followed by a flag, path, quote, or id (`Use the
specy-road frob --flag.`, `- Use the specy-road frob`, `## the specy-road frob --x`). Those
contexts are decided first. The same unregistered token on two lines is two warnings, each with
its line number (`AGENTS.md:1`, `AGENTS.md:2`). `specy-road frob; specy-road frob` is two entries.

## Review round 8

The same reviewer blocked A1 and A3 at `5f67e54`. A1 on `origin/WIP/improvements-0-3-1`
(`2ca83d8`) drops the heading exclusion and narrows list items to command-led items.
`_heading_title` is gone: `# Please specy-road frob` reports. A list item reports only when
the product name is the first token after the marker, or is preceded only by a run verb
(`- specy-road frob --x`, `- Run specy-road frob`). A prose bullet
(`- **Adoption prompts** are kept aligned with other specy-road formats that ...`) is a noun
phrase and does not report. `AGENTS.md` and `CLAUDE.md` in this repository report nothing.

## Touch zones

Final list: `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/cli.py`, `tests/`,
`docs/install-and-usage.md`, and `AGENTS.md` (the title needs the determiner `the` once a
heading is no longer an exclusion).
`specy_road/managed_block.py` was listed but did not need changing. The scanner skips the
managed block by the `HTML_COMMENT` markers and keeps the file's line numbers; it no longer
calls `_split`.

## Verification

- `python -m pytest -q` (after review round 1): 2258 passed, 2 skipped. Not re-run after round 2.
- `python -m pytest -q tests/test_validate_stale_commands.py` (after review round 8): 8 passed.
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
- Helper `_command_led_list_item` (validate_roadmap.py): a list item reports when the product name is the first token after the marker (emphasis and backticks ignored) or is preceded only by a run verb (A1). Replaces `_on_list_item`, which treated every bullet as a command. `_heading_title` and `_HEADING` are gone; a heading is not an exclusion (A1).
- Helper `_run_verb` (validate_roadmap.py): `run` / `exec` / `execute` / `invoke` / `uvx` immediately before the product name, or before one noun-phrase word (A1).
- Helper `_noun_phrase` (validate_roadmap.py): the noun-phrase exclusion, applied only when no mandatory context matched (A3).
- Helper `_next_token` / `_mandatory_follower` (validate_roadmap.py): a flag, path, quote, id-like argument, or the word `command`/`subcommand` after the token reports even inside a noun phrase or a heading (A1). Replaces `_followed_by_command_word`.
- Helper `_reports` (validate_roadmap.py): mandatory contexts first; a noun phrase is the only exclusion. The `code` parameter is gone; code spans are yielded before this helper.
- Helper `_occurrences` (validate_roadmap.py): every unregistered mention with its line number, without collapsing repeats (A1).
- Helper `_lines_outside_block` (validate_roadmap.py): drops managed-block lines but keeps the file's line numbers for the warning.
- Helper `_registered_names` (validate_roadmap.py): the specy-road and specyrd command sets the filter uses.
- Helper `_command_mentions` (validate_roadmap.py): walks every line and yields the tokens `_reports` keeps (A1).
- Helper `unregistered_commands` (validate_roadmap.py, public): drops registered names and keeps every remaining occurrence. Its docstring states the precedence rule.
- Helper `warn_unregistered_commands` (validate_roadmap.py, public): one warning per occurrence, with the file line number, wired into `validate_at`.
- Regexes `_FENCE`, `_INLINE_CODE`, `_MENTION`, `_LIST_ITEM` (validate_roadmap.py): fences, inline code, the lookbehind mention, and a list marker. `_HEADING` is gone with the heading exclusion.
- Table `REPLACED_COMMANDS` (cli.py): the A2 alias/deprecated-name table, next to the command set it complements.
- Guard `if not path.is_file(): continue`: most projects have only one of the two files, and the test's tmp git root has no `AGENTS.md`.
- Guard `except UnicodeDecodeError: continue`: a non-UTF-8 agent file; reached by `test_an_agent_file_that_is_not_utf8_is_skipped`.
- Branch: three-way advice (replacement / removed with none / `--help`): A2 wording; all three are asserted in the end-to-end test.
- Mocks: none.
- Test `test_validate_warns_for_each_unregistered_command_and_still_passes`: A1 + A2 + A3 end to end through the validate script on a nested `sr/` copy of the dogfood fixture (exit 0, exact warning lines, managed block skipped, `frob` / `does-not-exist` / a fenced `files` flagged, `the specy-road toolkit is` and `specy-road validate` not flagged, `CLAUDE.md` at the git root).
- Test `test_a_noun_phrase_is_quiet_and_a_command_is_not`: `# Please specy-road frob`, `- specy-road frob --x`, and `- Run specy-road frob` warn; `- **Adoption prompts** are kept aligned with other specy-road formats that ...`, `- the specy-road frob`, `the specy-road toolkit is`, and `specy-road validate --strict` do not. A flag, path, quote, `M1.2`, and `command`/`subcommand` still warn inside a noun phrase. `specy-road frob; specy-road frob` is two entries.
- Test `test_each_occurrence_warns_with_its_line`: the same unknown token on two lines of a file is two warnings, `AGENTS.md:1` and `AGENTS.md:2` (A1).
- Test `test_each_replaced_name_is_unregistered_and_its_replacement_is_not` (parametrized over the table): keeps the alias table honest as commands change.
- Test `test_the_toolkits_agent_files_report_nothing`: `unregistered_commands` on this repository's `AGENTS.md` and `CLAUDE.md` is empty (A3). Replaces `test_the_toolkits_agent_files_follow_the_mention_rule`, which expected the prose bullet `specy-road formats` under the wider list-item rule.
- Test `test_an_agent_file_that_is_not_utf8_is_skipped`: reaches the `UnicodeDecodeError` guard.
