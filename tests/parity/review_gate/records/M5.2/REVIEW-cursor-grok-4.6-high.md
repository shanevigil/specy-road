---
node_id: M5.2
model: cursor-grok-4.6-high
date: '2026-10-29'
verdict: approve
commit: bd7c4e6e3d34535b1c3e5ed4d6a7f4f60da50aff
acceptance:
  A1: pass
  A2: pass
  A3: pass
findings:
  correctness: []
  regression: []
  boundary: []
  test_integrity: []
commands_rerun:
- python -m pytest -q tests/test_validate_stale_commands.py (10 passed in 0.54s)
- 'specy-road file-limits (OK: file limits satisfied.)'
- specy-road validate --repo-root tests/fixtures/specy_road_dogfood (OK; no tells-agents-to-run
  lines)
- specy-road validate --repo-root sr (OK; no tells-agents-to-run lines)
- unregistered_commands on this checkout's AGENTS.md and CLAUDE.md (both [])
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
notes_sha256: bd22f724741c72e098db89a86e1c25e62e35e126e17eddb6e950099a2b1a46b3
family: xai
independence: distinct-family
---

## Verdict

Approve. A1–A3 hold at `bd7c4e6e3d34535b1c3e5ed4d6a7f4f60da50aff`. Round 16's span-as-token path works on the forms the tests cover; the check is warning-only; this repo's agent files stay quiet.

## Acceptance

- **A1 pass.** Every mention form in `tests/test_validate_stale_commands.py` behaves as asserted (re-run: 10 passed). Mandatory contexts beat the noun-phrase exclusion; occurrences keep their line numbers; the managed block is skipped. Frozen A1 (2026-10-29): the tests are the spec; further Markdown forms go to M5.8, not a block.
- **A2 pass.** `REPLACED_COMMANDS` names `grind` → `grind-session`, `pm-sync` → `sync`, and `backfill-activity` → nothing. The end-to-end validate test asserts all three advice strings; the parametrized test keeps the table honest.
- **A3 pass.** Warnings go to stderr; the nested-fixture validate still exits 0. `unregistered_commands` on this checkout's `AGENTS.md` and `CLAUDE.md` is empty. `specy-road validate --repo-root sr` prints no `tells agents to run` line. `Use the specy-road \`init\` command.` does not raise.

## Correctness

Round 16's public contract holds. Probes at this commit:

| Input | Result |
| --- | --- |
| `run specy-road \`frob\`` | `['specy-road frob']` |
| `Use the specy-road \`init\` command.` | `[]` |
| `Use the specy-road frob \`M1.2\`.` | `[]` (quiet in `test_command_token_in_an_inline_span`; round 16 required it) |
| `Use the specy-road frob M1.2.` | `['specy-road frob']` |

Fence interiors still scan only with `_MENTION.findall`, so `unregistered_commands("```\nspecy-road \`frob\`\n```")` is `[]`. That form is not in the branch's tests. Frozen A1 sends it to M5.8.

## Regression

None. `validate_at` calls `warn_unregistered_commands` next to the other agent-file checks. A registered span token no longer aborts validate.

## Boundary

Diff stays in the named touch zones plus `sr/work/implementation-summary-M5.2.md`. `AGENTS.md` only adds the determiner `the` so the title is a noun phrase once headings are not an exclusion.

## Test integrity

No existing test was deleted or weakened. New tests go through `unregistered_commands` / `warn_unregistered_commands` / the validate script. No `_`-prefixed imports, no mock call counts.

## Excess

The summary has a `## Added` inventory. It still lists `_follower_tokens`; that helper is not in this commit (`_followers_after` replaced it). Inventory drift only.

- *Test pins internals*: none proven. Tests import public `unregistered_commands`, `warn_unregistered_commands`, and `REPLACED_COMMANDS`.
- *Unreachable defence*: `except UnicodeDecodeError` is reached by `test_an_agent_file_that_is_not_utf8_is_skipped`. `if not path.is_file()` is the missing-agent-file case. No completed caller trace for a dead branch that should be removed.
- *Duplicated logic*: `_mention_at` and `_span_command_token` share a span-as-token parse but differ in inputs and outputs. `agent_file_lines_outside_block` is not `_split`: it keeps original line numbers.
- *Overlapping test*: `test_registered_subcommand_in_a_span_does_not_abort_validate` uses the same sentence as a quiet case in `test_command_token_in_an_inline_span`, but through `warn_unregistered_commands` (the path that raised). That is a regression for a distinct crash, not a required deletion.

## M5.8 (not a block)

A fenced line whose command token is a same-line span (`specy-road \`frob\`` inside ` ``` `) is quiet. Record on M5.8; do not change this leaf for it.