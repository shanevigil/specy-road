# Implementation summary: M14.11

## What changed

- **A1** — `specy_road/bundled_scripts/role_prompt_rework.py`: new `CLASS_AUDIT_LINES` (one paragraph): for each blocking finding, name its class (the kind of input, path or state that failed), check every other place in the change that class can reach, prefer a design change that removes the class over patching the one instance, and list what was checked under `## Probes` in the implementation summary, one line each (what was checked, and the result). `rework_lines()` adds it after the blocking findings, only when there is at least one blocking review; a rework from a stopped worker alone gets nothing new.
- **A2** — `specy_road/worker_ops_message.py`: new `fix_round_text()` builds a `## Fix round` message: a short header, each current blocking finding via `blocking_reviews()` + `_review_lines()` (tip = the worker worktree's HEAD), the same `CLASS_AUDIT_LINES`, then any `--text`/`--file` text. `message()` takes `fix_round=False`; the plain path is unchanged (the text is sent as given).
- `specy_road/bundled_scripts/worker_cli.py`: `worker message` gets `--fix-round`, which may omit `--file`/`--text`. Plain `worker message` keeps argparse's refusal unchanged (see Fix round 1). `fix_round` is bound into the `--op-id` inputs.

## Touch zones

Final list: `specy_road/bundled_scripts/role_prompt_rework.py`, `specy_road/worker_ops_message.py`, `specy_road/bundled_scripts/worker_cli.py`, `tests/`, plus the new module **`specy_road/bundled_scripts/worker_cli_args.py`** (added in fix round 1 because the fix took `worker_cli.py` past the 400-line cap; please add it to the touch zones). `role_prompt.py` (the caller) needs no change. `docs/orchestration-workers.md` does not list `worker message` flags, so the docs were not changed. A follow-up could mention `--fix-round` there (outside this leaf's zones).

## Verification

- `python -m pytest -q tests/test_fix_round_class_audit.py tests/test_rework_findings_in_prompt.py tests/test_worker_cli.py`: pass
- `python -m pytest -q -n 4`: 3997 passed
- `ruff check` on changed files: clean. `specy-road file-limits`: OK

## Probes

- Rework with blocking reviews at the tip and at an earlier commit: the audit block is added once, after all findings (existing M11.68 tests still pass).
- Rework with only a terminated/failed worker: no audit block and no `## Probes` (test).
- `--fix-round` with text, without text, and with no blocking review: findings + audit + text; findings + audit; refused with exit 1 (tests).
- Plain `worker message --text`: the prompt file is exactly the given text (test). A plain message with neither `--text` nor `--file` keeps argparse's exit 2 with usage (fixed in fix round 1).
- `--fix-round` to a worker whose turn is still running: the composed text goes through the existing queue path unchanged (`_send`). I reviewed this path but did not add a test for it.
- An approval that replaced a block is not carried, because `blocking_reviews()` reads each reviewer's latest verdict (existing behaviour, reused).

## Fix round 1

Base merged first: `origin/WIP/improvements-0-3-1`, clean merge.

- **R1 (gpt-6.1-sol):** round 0 made the `--file`/`--text` group optional and refused a plain message without either through `WorkerError`, with exit 1 and no usage. Now the group is `required=True` again. `--fix-round` uses a small `argparse.Action` (`FixRound`, in the new `specy_road/bundled_scripts/worker_cli_args.py`) that sets `required = False` on that group during parsing. argparse checks required groups only after every argument's action has run, so `--fix-round` lifts the requirement in any position. Without it, argparse refuses exactly as on the base. The parser is built fresh per `main()`, so the change lasts one parse. The round-0 `cmd_message` guard is gone. The class lives in its own module because inlining it pushed `worker_cli.py` to 403 lines; it is now 395.
- **R2:** `tests/test_fix_round_class_audit.py` imports the public `tests.worker_repo_helpers.make_worker_repo` instead of the private `_repo`. The assertions are kept. The missing-text test now pins exit 2, the `usage: specy-road worker message` line with `(--file PATH | --text TEXT)`, and argparse's `one of the arguments --file --text is required` error, for a plain message, `--no-queue` and `--offline`. No prompt file is written.
- **Red/green:** with round 0's `worker_cli.py` swapped back in, `test_plain_message_is_sent_unchanged` fails (`assert 1 == 2`). With the fix, it passes.

### Probes (fix round 1)

The class was argument paths of plain `worker message` whose exit code or output could differ from the base. I compared the base `29ec3641` `worker_cli.main` with the fixed one, each on a fresh worker repo (so an `--op-id` cannot replay across runs), on exit code, stdout and stderr:

- neither `--file` nor `--text`, alone and with `--no-queue`, `--offline`, `--no-queue --offline --json`, and `--op-id`: identical (exit 2, usage, `one of the arguments --file --text is required`).
- `--text` with `--file`: identical (exit 2, `not allowed with argument --text`).
- `--text`; `--file`; `--text --no-queue`; `--text --offline`; `--file --no-queue --offline`; `--text --json --op-id`; `--text ''`: identical (each reaches `ops.message`, exit 1 on the probe's unknown worker).
- `--file` pointing at a missing path, with and without `--op-id`: identical (exit 1, `cannot read --file …`).
- `-h` and the usage line: the only difference is the new `[--fix-round]` token and its help line. `(--file PATH | --text TEXT)` is unchanged; round 0 had changed it to `[...]`.
- A successful plain send (`--text` to an idle worker): the prompt file is exactly the text (`test_plain_message_is_sent_unchanged`, `test_worker_cli.py::test_message_resume_lease_and_interrupt`).
- `--fix-round` alone, with `--file`, with `--text` before or after it: all parse and reach `ops.message`. `--fix-round --text --file` is still refused by the exclusive group (exit 2).
- Targeted tests: `tests/test_fix_round_class_audit.py tests/test_rework_findings_in_prompt.py tests/test_worker_cli.py tests/test_worker_state.py tests/test_cursor_usage_cost.py tests/test_worker_turn_check.py` passed (73). The full suite was not run this round, as instructed.

## Added

- `CLASS_AUDIT_LINES` (role_prompt_rework.py): the shared class-audit block for A1 and A2.
- `lines += CLASS_AUDIT_LINES if blocks else []` branch in `rework_lines`: adds the block only when there is a blocking finding.
- `fix_round_text()` (worker_ops_message.py): builds the A2 message from the current findings, the block and the text.
- Guard in `fix_round_text`: refuses when no blocking review exists, so the worker is not sent an audit request with no findings.
- `fix_round` parameter on `ops.message`: selects the A2 text. The default is unchanged.
- `--fix-round` CLI flag (`FixRound` action, see Fix round 1): lets `--fix-round` run without text while plain message still requires text. The round-0 relaxed group and `cmd_message` guard were removed in fix round 1.
- `fix_round` in the `--op-id` inputs: a retry with a different mode is a different op.
- `tests/test_fix_round_class_audit.py`: 6 tests covering the block wording, its place in the rework section, its absence without blocks, the fix-round text with and without `--text`, the fix-round refusal, and plain message unchanged plus its argparse missing-text refusal. No mocks.
- Fix round 1: `specy_road/bundled_scripts/worker_cli_args.py` with `FixRound(argparse.Action)`: lifts the required `--file`/`--text` group only when `--fix-round` is given, so plain message keeps argparse's refusal. It is a new module because of the file limit.
- Fix round 1: the parametrised missing-text assertions (plain, `--no-queue`, `--offline`) in `test_plain_message_is_sent_unchanged`: pin exit 2, the usage and the argparse error.
