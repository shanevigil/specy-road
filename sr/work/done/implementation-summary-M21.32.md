# Implementation summary: M21.32 (session-end-only-your-own)

Base `b674f664`; `origin/WIP/improvements-0-3-1` merged in (M21.36 and roadmap zone commits; no budget change). Fix commit `b535d434`.

## Behaviour

- `session end` (`specy_road/bundled_scripts/session_cli.py`, `cmd_end`). The caller is always `default_agent_id()`. A positional id or `--agent` only selects the target, and every form goes through one check:
  - **Target is the caller's own id:** the record is removed, as before (no user check, as before).
  - **Other target:**
    - an unreadable record, or one another user started: refused, kept, exit 1 (the same message as before);
    - expired: removed;
    - live: exit 1 with the A1 message, file kept;
    - live with `--force`: removed only when `sys.stdin.isatty()`, otherwise exit 1 with "a human ends another agent's live session from a terminal; nothing was removed".
  - **No record for the caller's id:** prints `session <id>: no record; your record is under the id \`session start\` printed (export SPECY_ROAD_AGENT_ID=<id>)`, exits 0 and lists no other sessions.
  - `_end_own` and `_retire` are merged into `cmd_end`. The "your only live session" and "worktree and branch" fallbacks are gone.
- The guard's deny reason (`tool_call_guard.decide`) adds "Do not end, edit or delete another session's record to get past this; ask its owner or a human."
- `session_presence.own_live_sessions`: docstring only. `session touch` still uses it through `own_session_here`.
- Guidance:
  - `agents-rules.md` "Shared checkouts and other agents." and the managed block's "Shared checkout" rule, each with an updated provenance comment.
  - `suggested_prompts/bootstrap-agents-md.md`: the same sentence, verbatim.
  - `docs/orchestration.md` Presence: the `session end` line and the paragraph on retiring records.
  - CHANGELOG `[Unreleased]` Fixed (security).
- `tests/test_enforced_rules_pointers.py`: budgets raised to 17 / 2,347 (stub) and 68 / 9,496 (rules), as the coordinator approved, each with a comment citing M21.32.

## Touch zones (final)

The brief's list plus `tests/test_enforced_rules_pointers.py` and `suggested_prompts/bootstrap-agents-md.md`, both added by the coordinator. No new module.

## Verification

- `pytest -q -n 4`: 5777 passed.
- `ruff check specy_road tests`: clean.
- `specy-road file-limits`: OK.
- Red-green: against the base `session_cli.py` and `tool_call_guard.py`, `tests/test_session_end_others.py` fails 6 of 8 cases.

## Added

- `cmd_end` own-or-expired check, `--force` flag and TTY check: A1.
- `cmd_end` no-record hint naming the exported id: A2.
- Guard deny-reason sentence: A2.
- `tests/test_session_end_others.py::test_session_end_only_your_own`: the CR3 table, seven rows (peer by id, peer by `--agent`, no own record, expired peer, own id, `--force` without and with a TTY). It checks that peer.yaml stays byte-identical.
- `tests/test_session_end_others.py::test_guard_denial_names_the_rule`: the guard's `git restore` denial names the rule (A3).
- `_Stdin` test stub in that file (a `StringIO` with a set `isatty`): patches `sys.stdin` for the TTY rows.
- `tests/test_session_presence.py`:
  - three fallback tests merged into `test_cli_end_with_a_new_derived_id_ends_nothing_and_names_the_exported_id` (A3);
  - two derived-end tests now end their own id;
  - two tests that ended another agent's live record now run as that agent.
- Mocks: none beyond the `sys.stdin` patch above.
