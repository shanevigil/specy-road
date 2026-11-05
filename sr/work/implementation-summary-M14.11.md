# Implementation summary: M14.11

## What changed

- **A1** — `specy_road/bundled_scripts/role_prompt_rework.py`: new `CLASS_AUDIT_LINES` (one paragraph): for each blocking finding, name its class (the kind of input, path or state that failed), check every other place in the change that class can reach, prefer a design change that removes the class over patching the one instance, and list what was checked under `## Probes` in the implementation summary, one line each (what was checked, and the result). `rework_lines()` adds it after the blocking findings, only when there is at least one blocking review; a rework from a stopped worker alone gets nothing new.
- **A2** — `specy_road/worker_ops_message.py`: new `fix_round_text()` builds a `## Fix round` message: a short header, each current blocking finding via `blocking_reviews()` + `_review_lines()` (tip = the worker worktree's HEAD), the same `CLASS_AUDIT_LINES`, then any `--text`/`--file` text. `message()` takes `fix_round=False`; the plain path is unchanged (the text is sent as given).
- `specy_road/bundled_scripts/worker_cli.py`: `worker message` gets `--fix-round`. `--file`/`--text` stay mutually exclusive but are no longer required by argparse, because `--fix-round` may be used without text. Without `--fix-round`, missing both is refused in `cmd_message` with exit 1 (`worker message needs --file or --text (optional with --fix-round)`) instead of argparse's exit 2. `fix_round` is bound into the `--op-id` inputs. The file is 396 lines (cap 400).

## Touch zones

Final list as given: `specy_road/bundled_scripts/role_prompt_rework.py`, `specy_road/worker_ops_message.py`, `specy_road/bundled_scripts/worker_cli.py`, `tests/`. `role_prompt.py` (the caller) needs no change. `docs/orchestration-workers.md` does not list `worker message` flags, so the docs were not changed. A follow-up could mention `--fix-round` there (outside this leaf's zones).

## Verification

- `python -m pytest -q tests/test_fix_round_class_audit.py tests/test_rework_findings_in_prompt.py tests/test_worker_cli.py`: pass
- `python -m pytest -q -n 4`: 3997 passed
- `ruff check` on changed files: clean. `specy-road file-limits`: OK

## Probes

- Rework with blocking reviews at the tip and at an earlier commit: the audit block is added once, after all findings (existing M11.68 tests still pass).
- Rework with only a terminated/failed worker: no audit block and no `## Probes` (test).
- `--fix-round` with text, without text, and with no blocking review: findings + audit + text; findings + audit; refused with exit 1 (tests).
- Plain `worker message --text`: the prompt file is exactly the given text (test). A plain message with neither `--text` nor `--file` is refused with exit 1 (it was exit 2 from argparse).
- `--fix-round` to a worker whose turn is still running: the composed text goes through the existing queue path unchanged (`_send`). I reviewed this path but did not add a test for it.
- An approval that replaced a block is not carried, because `blocking_reviews()` reads each reviewer's latest verdict (existing behaviour, reused).

## Added

- `CLASS_AUDIT_LINES` (role_prompt_rework.py): the shared class-audit block for A1 and A2.
- `lines += CLASS_AUDIT_LINES if blocks else []` branch in `rework_lines`: adds the block only when there is a blocking finding.
- `fix_round_text()` (worker_ops_message.py): builds the A2 message from the current findings, the block and the text.
- Guard in `fix_round_text`: refuses when no blocking review exists, so the worker is not sent an audit request with no findings.
- `fix_round` parameter on `ops.message`: selects the A2 text. The default is unchanged.
- `--fix-round` CLI flag, the relaxed `--file`/`--text` group, and the neither-given guard in `cmd_message`: lets `--fix-round` run without text while plain message still requires text.
- `fix_round` in the `--op-id` inputs: a retry with a different mode is a different op.
- `tests/test_fix_round_class_audit.py`: 6 tests covering the block wording, its place in the rework section, its absence without blocks, the fix-round text with and without `--text`, the fix-round refusal, and plain message unchanged plus its missing-text refusal. No mocks.
