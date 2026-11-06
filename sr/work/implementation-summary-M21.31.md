# Implementation summary: M21.31 — review record files only as the caller

## What changed

- **A1** `specy_road/review_caller.py` (new): `caller(repo_root)` returns `("worker", model)` when
  `SPECY_ROAD_WORKER_ID` is set and resolves through `worker_state.load_record` (a bad id, missing, malformed or
  schema-invalid record raises `CallerError`, reported as exit 1, no traceback, nothing written); else
  `("harness", name)` for exactly one marker in `HARNESS_MARKERS`; else `None`. Markers, confirmed against the
  installed replay versions: Claude Code 2.1.318 `CLAUDECODE=1` (this session's env); codex-cli 0.166.0
  `CODEX_THREAD_ID` (in the binary, and exported in the 2026-11-05 Codex transcripts under
  `sr/work/reviews/.transcripts/`); Cursor agent 2026.11.05-86047df `CURSOR_AGENT=1` (set in the env of its shell
  executor in the bundle).
- **A2** `refusal(repo_root, ns)` is called in `review_cli.cmd_review_record_locked` (the argparse handler) after the
  unknown-node check and before the review lock, so a refusal writes no lock, record or REJECTED file.
  `cmd_review_record` (used by `file_review`, i.e. `review delegate` and `prompt --channel cli --run`) is not checked.
  Worker: refused unless its model is `--model`. Harness: refused when the `--model` roster entry's `harness` differs
  (missing or `generic` matches none), with the brief's message. A model not on the roster is left to the existing
  "not in the roster" refusal. Unidentified: needs `--human-filed`, one non-empty non-whitespace line; stored
  (stripped) as `human_filed` before signing in `review_rejected._review_record_signed_data`, read with `getattr`;
  any `human_filed` in the notes' front matter is dropped so only the flag sets it. A matching identified caller's
  flag is dropped with a stderr note. `review-record.schema.json` gains optional `human_filed`.
- **A3** `review_gate._signature_problem`: an unsigned `human_filed` record is ineligible with "filed by hand
  (human_filed) and unsigned; policy.count_human_filed_reviews is off" unless that policy key is true; a verified
  signature counts. `count_human_filed_reviews` (default false) added to `DEFAULT_POLICY` and
  `orchestration.schema.json`. `PASTED_LINES` gains the human-terminal sentence; `reviewer_preamble` unchanged.
  `review_answer.FILLED_BY_SPECY_ROAD` gains `human_filed`, so the reviewer output schema does not offer it
  (coordinator-approved zone).
- **A4** `tests/test_review_record_caller.py` (marked `real_review_caller`) covers the table, including
  `review delegate` of the codex reviewer `gpt-6.1-sol` from a process with the Cursor marker (a fake `codex` on
  PATH), which files and counts.
- **A5** `docs/orchestration-review.md` "Who may file a review record"; CHANGELOG `[Unreleased]` Fixed (security).

## Fix round 1 (block by gpt-6.1-sol-low at 843f6e36)

- **Class: a worker record that fails to load in a way `load_record` does not wrap** (invalid UTF-8 raised
  `UnicodeDecodeError`). The rule is now one clause: `caller` turns *any* failure to load the record named by
  `SPECY_ROAD_WORKER_ID` into `CallerError` (exit 1, no traceback, nothing written), so no shape of a bad record
  can reach a traceback. Docstring and docs state it.
- **Class: `--human-filed` text that is not one line.** The same audit found U+2028 accepted. One rule replaces the
  `\n`/`\r` test: non-blank and `text.splitlines() == [text]`. (Round 1 also added `isprintable()`; round 2 removed
  it, below.)
- **A4 delegate row** now uses a codex roster entry, as the brief's table says.

## Fix round 2 (block by gpt-6.1-sol-low at c849d629)

- **Class: the attestation rule refusing text A2 allows.** Round 1's `isprintable()` clause went beyond A2 ("one
  non-empty, non-whitespace line") and refused a tab, any control character and an undecodable argv byte. The rule is
  now exactly A2 and nothing more: not blank, and one line by `str.splitlines` (no `\n`, `\r`, U+2028 or other
  break). Everything else on the line is kept; the stored value is stripped. Docstring, `--help`, docs and the refusal
  message ("one non-blank line") say the same. Rows: tab, BEL with non-ASCII, and an undecodable byte are filed and
  counted under the policy; a lone tab is refused as blank.

## Probes

Round 2:

- `--human-filed 'Alice<TAB>pasted independent review'` (CLI subprocess, `count_human_filed_reviews` on): exit 0, record valid, gate met (test row; red at c849d629).
- BEL with non-ASCII (`Zoë \x07 by hand`), an undecodable argv byte (`me \xff`), surrounding whitespace: each exit 0, record re-reads valid, gate met (rows for the first three; surrounding whitespace was already a row).
- NUL in an attestation: not reachable from the CLI (the OS refuses NUL in argv, `ValueError: embedded null byte` before specy-road runs); no row.
- A lone tab or spaces: refused as blank (rows).
- The other places the over-strict class could sit: `review-record.schema.json`'s `human_filed` pattern (`^[^\r\n]*\S[^\r\n]*$`) accepts tab and control characters, so it doesn't refuse more than the rule does. The worker-record and marker checks have no text-shape rule. `--help` and docs had the "printable" wording, now removed.

Round 1:


- Worker record with bytes `\xff\xfe` (CLI subprocess): before, a `UnicodeDecodeError` traceback; now exit 1, message, review tree unchanged (test row).
- Worker record YAML with an unhashable complex key: exit 1, no traceback (already wrapped by `load_record`; test row added).
- Worker record that is a self-referencing YAML alias, and one that is a directory: exit 1, no traceback (probe only).
- Invalid id `../w-1`, missing record, non-mapping record: exit 1 (existing rows).
- `--human-filed` with U+2028: before, accepted and filed; now exit 1, nothing written (row). (Round 1 also refused NUL and an undecodable byte; round 2 accepts them again, per A2.)
- `--human-filed` "me\n", "me\r…", empty, whitespace: exit 1 (rows).
- `orchestration.yaml` with invalid UTF-8 at the integration branch, under a harness marker: no traceback; the caller check skips the unreadable config and the existing "not in the roster" refusal applies.
- Other undecodable input reaching the change: markers are compared as strings (no decoding); `--model` is matched against the roster only. Nothing else.

## Final touch zones

The brief's zones plus, approved by the coordinator: `specy_road/review_answer.py`, `tests/conftest.py`,
`tests/test_review_concurrent_writers.py`, `tests/test_review_record_write.py`. `role_prompt_rca.py` was not
changed (its line stays plain).

## Verification

`pytest -n 6 -q`: 5818 passed after fix round 1 (5792 at round 0, both with `CLAUDECODE=1`, this harness, and without it, as CI). `ruff check specy_road
tests` and `specy-road file-limits` pass. Merged `origin/WIP/improvements-0-3-1` before each final run.

## Added

- `specy_road/review_caller.py` `HARNESS_MARKERS`: one confirmed marker per harness (A1).
- `review_caller.CallerError`: a `SPECY_ROAD_WORKER_ID` whose record fails to load for any reason becomes exit 1 without a traceback (A1; fix round 1 widened it from `WorkerError`).
- `review_caller.caller`: worker id ahead of markers; two markers are unidentified (A1).
- `review_caller._attestation_problem`: one rule for `--human-filed`: present, non-blank, one line by `splitlines` (A2; fix rounds 1 and 2).
- `review_caller.refusal`: the worker / harness / unidentified checks and the ignored-flag note (A2).
- Guard in `cmd_review_record_locked` calling `refusal` before the lock (A2).
- `--human-filed` argument on `review record` (A2).
- `data.pop("human_filed")` plus flag write in `review_rejected`: only the flag sets the field, before signing (A2).
- `human_filed` property in `review-record.schema.json` (A2); in `FILLED_BY_SPECY_ROAD` so reviewers are not asked
  for it (A2/A3).
- Branch in `review_gate._signature_problem` for unsigned `human_filed` records (A3).
- `count_human_filed_reviews` in `DEFAULT_POLICY` and `orchestration.schema.json` (A3).
- `PASTED_LINES` sentence (A3).
- `tests/conftest.py` `review_record_caller_matches` fixture and `real_review_caller` marker: the suite clears the
  harness markers (so subprocess filings run as in CI under any harness) and patches `refusal` to pass for
  in-process filings, except in tests marked `real_review_caller` (coordinator decision).
- `tests/test_review_record_caller.py`: refusal rows (Cursor→claude-code, Cursor→codex, worker mismatch, worker with
  inherited marker, two markers, no marker) with an unchanged review tree; bad worker id/record rows; attestation
  rows; matching harness with and without the flag; a worker's own model; hand-filed counted only with the policy;
  signed hand-filed counted; delegate of a codex reviewer from a Cursor-marked process (a `FAKE_CODEX` script on
  PATH); rendered paste prompt (A4). Fix round 1 added parametrize rows: invalid-UTF-8 and complex-key worker
  records; trailing-newline, CR and U+2028 attestations. Fix round 2 replaced the NUL and undecodable-byte refusal
  rows with a lone-tab refusal row, and parametrized the hand-filed counting test over accepted attestations (tab,
  BEL with non-ASCII, undecodable byte).
- `tests/test_review_concurrent_writers.py`: the two subprocess filings pass `--human-filed` (they run unidentified).
- `tests/test_review_record_write.py`: `human_filed` added to the filled-field list.
- Mocks: none beyond the conftest `refusal` patch.

## Context feedback

- missing: "Modules that import each zoned Python file ... `tests/review_delegate_helpers.py` _(outside zones)_" — the brief did not say that ~25 test files file `review record` through the CLI with harness-less roster entries, so A2 breaks them without a suite-wide fixture (found on the first turn).
- wrong: "Claude Code exports `CLAUDECODE=1`. The Codex and Cursor markers are confirmed ... before they go in the table" — not wrong, but no confirmed values were given; they had to be read from the installed binaries.
- unused: "## 8. Rollup semantics (reference)"
