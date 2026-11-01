# Implementation summary: M5.8

## Forms handled

The M5.8 planning sheet is still the blank template, so the forms come from M5.2's
later review rounds (`sr/work/reviews/M5.2/` in the main checkout). Only one form
was recorded for M5.8 there (`REVIEW-cursor-grok-4.6-high.md`, section
"M5.8 (not a block)"; repeated in its notes file):

- **A fenced line whose command token is a one-line code span**: ```` ``` ```` /
  ``specy-road `frob` `` / ```` ``` ````. Before: `[]`. Now: `['specy-road frob']`.

Other "out of scope" notes in those rounds (`run all the specy-road frob`,
`the specy-road toolkit **is** a library`, `Use the specy-road frob `M1.2`.`)
were readings the reviewers accepted under M5.2's A1, not forms sent to M5.8,
so they are unchanged.

## Change

`_mentions_in_fenced_line` (in `specy_road/bundled_scripts/validate_stale_commands.py`)
now also reads a one-line span right after the product name as the command
token, through the existing `_span_command_token` (the same parse open lines
use). Per M5.2 A1 a fenced block always warns, so there is no `_reports` call:
the noun-phrase exclusion does not apply inside a fence, matching the existing
`the specy-road frob` inside a fence case. Registered names (`init`) and
tokens that are not command-shaped (`M1.2`) stay quiet. `docs/install-and-usage.md`
already says a fenced block always warns, so no doc change.

## Touch zones (final)

`specy_road/bundled_scripts/validate_stale_commands.py`, `tests/` — accurate; nothing else needed.

## Verification

- `python -m pytest -q tests/test_validate_stale_commands.py` — 11 passed (the new test failed before the fix).
- `specy-road file-limits` — OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` — exit 0.
- `python -m pytest -q -p no:cacheprovider tests/test_validate_stale_commands.py tests/test_validate_roadmap.py` — 40 passed (`validate_roadmap.py` is the only importer of the changed module).
- **Full suite not completed.** The host's load average was 68–80 from other agents, and subprocess-heavy tests ran niced: the full `pytest -q -p no:cacheprovider` was about 3% done after 32 minutes, with no failures up to that point, before I stopped it. A wider set did finish: `pytest -q -p no:cacheprovider tests/test_init_project.py tests/test_generated_files.py tests/test_validate_gates.py tests/test_validate_acceptance_coverage.py tests/test_project_layouts.py` — 68 passed (22 minutes wall-clock under that load). The change only adds yields for fenced lines in `_mentions_in_fenced_line`, but a full-suite run is still owed.

## Added

- Branch in `_mentions_in_fenced_line`: yield a span command token on a fenced line — the recorded M5.8 form.
- Test `test_command_token_in_an_inline_span_inside_a_fence`: the form with ``` and ~~~ fences, a noun-phrase line, a flag follower, a span token followed by a plain mention on the same line (both warn), plus the registered (`init`) and not-command-shaped (`M1.2`) span tokens staying quiet.
- Helpers: none. Guards: none. Mocks: none.
