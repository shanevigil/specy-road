# Implementation summary — M11.45 (`stale-command-prose`)

## Touch zones (confirmed)

- `specy_road/bundled_scripts/validate_stale_commands.py`
- `tests/` (`tests/test_validate_stale_commands.py`)
- `docs/install-and-usage.md`

No additional paths were required.

## Behaviour

`_reports()` now returns true only for command-shaped open-line contexts: command-led list items, run verbs, and mandatory followers (flags, paths, quoted or id-like arguments, or the words command/subcommand). The previous default-warn plus noun-phrase exclusion is gone. Fenced blocks and inline code spans are unchanged (still scanned without the open-line gate).

## Acceptance

- **A1:** Plain prose examples from the brief (`trying specy-road here`, `when specy-road runs it`, `nothing specy-road surprises me`, plus existing quiet fixtures) stay silent; command-shaped fixtures still warn. Covered in `test_open_line_mentions_warn_only_in_command_shaped_contexts` and related tests.
- **A2:** `docs/install-and-usage.md` lists the contexts that warn and cites plain prose as non-warn, without framing the rule as a noun-phrase exception list.

## Verification

- `python -m pytest tests/test_validate_stale_commands.py`
- `specy-road file-limits`

## Added

- Renamed test `test_open_line_mentions_warn_only_in_command_shaped_contexts` — documents A1 open-line vs prose behaviour through `unregistered_commands`.
- Three quiet prose strings in that test — acceptance examples from the brief.
- Adjusted integration and occurrence expectations — align with command-shaped-only open-line warnings.
