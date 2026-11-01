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

Round 2 (gpt-6.1-sol, R1): plain and span-token mentions on one fenced line
were yielded spans-first, so `specy-road nope && specy-road `frob`` came back
reversed. Both kinds are now collected with their start position (the plain
match start; the product-name start for a span token) and yielded sorted, so
`unregistered_commands` and the warnings keep source order.

## Touch zones (final)

`specy_road/bundled_scripts/validate_stale_commands.py`, `tests/` — accurate; nothing else needed.

## Verification

Round 2, at `b3ce194`:

- `python -m pytest -q -p no:cacheprovider tests/test_validate_stale_commands.py tests/test_validate_roadmap.py` — exit 0, 40 passed. These are the touched test file plus the tests of `validate_roadmap.py`, the only module that imports the changed one. The new plain-before-span assertion failed before the fix: the reviewer reproduced it, and it returned `['specy-road frob', 'specy-road nope']`.
- `specy-road file-limits` — exit 0.
- Full suite `python -m pytest -q -p no:cacheprovider`: **not completed**. The host load average was 6–113 from other agents. Started in the foreground, it was moved to the background at 600s and killed at the time limit after 2,512 of 2,554 tests. All 2,512 passed except 2 skips; there were no failures. Caveat: while this round was running, my then-uncommitted edits disappeared from the worktree, which was not my doing (another session or a test). So I cannot prove that every one of those 2,512 tests ran against the fix. I re-applied the same edits, and the focused run above is at the committed `b3ce194`.
- The other 42 tests (`tests/test_worker_review_round1.py` from `test_concurrent_delegates_on_one_leaf_launch_once` on, plus `tests/test_worker_review_round2.py` and `tests/test_worker_state.py`) are worker-orchestration tests that do not import the stale-command module. Re-run on their own, 4 passed in about 15 minutes at load 113, and I stopped the run. A full-suite run on a quiet host is still owed.

Round 1, at `e0065f1`: `test_validate_stale_commands.py` + `test_validate_roadmap.py` 40 passed; `test_init_project`, `test_generated_files`, `test_validate_gates`, `test_validate_acceptance_coverage`, `test_project_layouts` 68 passed; dogfood `validate` exit 0.

## Added

- Branch in `_mentions_in_fenced_line`: collect a span command token on a fenced line — the recorded M5.8 form.
- Position sort in `_mentions_in_fenced_line`: yields plain and span-token mentions in source order (round 2, R1).
- Test `test_command_token_in_an_inline_span_inside_a_fence`: the form with ``` and ~~~ fences, a noun-phrase line, a flag follower, a span token and a plain mention on the same line in both orders (both warn, in source order), plus the registered (`init`) and not-command-shaped (`M1.2`) span tokens staying quiet.
- Helpers: none. Guards: none. Mocks: none.
