# Implementation summary for M9.8

## Summary

An approving reviewer's `verify_pre_existing` no longer clears a failing READY
verifier on its word. `specy-road review check-pre-existing <NODE_ID>` takes the
failing READY verifiers that a counted approval names, runs each twice through
the shell at the project root of a detached temporary worktree of the
integration tip (resolved like `review_gate_ready.trial_merge_or_exit`: the
remote-tracking integration branch, else the local one), removes only that
worktree, and writes `work/reviews/<NODE_ID>/PRE-EXISTING.md` with
`integration_commit` (full SHA) and `commands: [{cmd, exits: [first, second]}]`.
It exits 0 when every command failed both times, else 1 with
`claim-rejected: <cmd>` per command that exited 0 at least once. Errors (no
claim on the node, unresolvable tip, worktree creation failure) print to stderr
and exit 1. With nothing claimed it prints so, writes nothing and exits 0.

`review_files.verifier_gate_problems` keeps its signature (its caller,
`review_gate.py`, is outside the touch zones) and delegates to
`review_pre_existing.gate_problems`: an unclaimed failing verifier gives the
same problem as before; a claimed one is cleared only when the file lists it
with two non-zero integer exits and `integration_commit` equals the current tip;
otherwise the problem ends `(unverified)` (not in the file as a well-formed
`{cmd: <str>, exits: [<int>, <int>]}` entry, `commands` not a list, or the
file missing or invalid), `(stale: <sha12>)` (recorded tip is not the current tip,
checked before the exits, since an outdated record is no evidence), or
`(rejected)`. The tip is resolved from the project root that holds the READY
(`ready.path.parents[3]`, the main worktree's project dir when asked from a
linked worktree), and only when some failing verifier is claimed.

## Changes

- `specy_road/review_pre_existing.py` (new): tip resolution, claim check, the
  two-run worktree runner, and `cmd_check_pre_existing`.
- `specy_road/review_files.py`: `verifier_gate_problems` delegates (lazy import,
  because `review_pre_existing` imports this module); net 3 lines shorter, the
  file was at 397/400.
- `specy_road/bundled_scripts/review_cli.py`: registers `review
  check-pre-existing` (one import, five parser lines; 394/400).
- `specy_road/schemas/review-record.schema.json`: `verify_pre_existing`
  description.
- `docs/orchestration-review.md`, `CHANGELOG.md` (Unreleased → Added).
- `tests/test_review_pre_existing.py` (new); `tests/test_review_evidence.py`:
  `test_pre_existing_marker_on_approve_clears_verifier_block` now asserts the
  marker alone leaves `(unverified)` and that the gate clears after
  `check-pre-existing` (A3 changes that behaviour; same name, more asserts).

Touch zones confirmed: everything changed is inside them. Not changed, outside
the zones and possibly worth a follow-up: `specy_road/templates/project/work/review-record.template.md`
and `specy_road/templates/specyrd/commands/specyrd-review-record.md` still
describe `verify_pre_existing` as the reviewer's claim without naming
`check-pre-existing` (still accurate, just incomplete); `docs/orchestration.md`
only shows the field in an example.

## Verification

- `pytest -q -p no:cacheprovider tests/test_review_pre_existing.py tests/test_review_evidence.py`
  — 27 passed (after the R1 fix from gpt-6.1-sol's block; the full suite was
  not re-run after the fix).
- `pytest -q -p no:cacheprovider` (full suite) — 1 failed, 2736 passed, 2 skipped;
  the failure is `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo`
  on `docs/brainstorming.md: 406 lines`, pre-existing (see file-limits below).
- `ruff check specy_road tests scripts` — all checks passed.
- `specy-road file-limits` — exit 1 on `docs/brainstorming.md: 406 lines`,
  unchanged by this leaf (406 lines at the base commit too).
- `python scripts/check_test_private_imports.py` — 0 new.
- `specy-road integrity M9.8` — no findings.
- `scripts/check_clones.py` could not run here: `pylint` is not installed.

## Walkthrough

1. `specy_road/review_pre_existing.py`: `claim_problem` is the rule A3 states;
   `run_twice` is A1/A4; `cmd_check_pre_existing` is A1/A2.
2. `tests/test_review_pre_existing.py`: `test -f src/a.py` fails on `dev`
   (only the feature branch adds it) and `test -f roadmap/manifest.json`
   passes there, so each also proves the command ran at the project root of a
   checkout of the integration tip, not the feature branch.

## Added

- `review_pre_existing.integration_tip` — full SHA of the integration tip, resolved as the trial merge resolves the branch (A1, A3).
- `review_pre_existing.claim_problem` — the A3 rule: `None` when verified, else `unverified` / `stale: <sha>` / `rejected`.
- `review_pre_existing.gate_problems` — builds the gate problems with the suffix; reads `PRE-EXISTING.md` and the tip only when a failing verifier is claimed.
- `review_pre_existing.run_twice` — two shell runs per command in a detached temporary worktree, removed in `finally` (A1, A4).
- `review_pre_existing.cmd_check_pre_existing` — the CLI command (A1, A2).
- `review_pre_existing._rows` — R1 fix: validates `commands` is a list and each entry has a string `cmd` and exactly two int `exits`; anything else is no evidence, so the claim stays `(unverified)` instead of raising in `evaluate_gate`.
- Guard: `type(e) is int` in `_rows` — YAML `true` is an int subclass and must not count as an exit.
- Guard: no-claim case prints and exits 0 without writing or creating a worktree — nothing to verify.
- Guard: unresolvable tip / failed `worktree add` → error, exit 1 — cannot run on the tip.
- Branch: lazy import in `review_files.verifier_gate_problems` — avoids the import cycle with `review_pre_existing`.
- `review_cli` parser entry `review check-pre-existing` with `--ref` and `--repo-root` — same target resolution as `review record` / `review list`.
- Test `test_a_claim_on_a_command_that_passes_on_the_tip_is_rejected` — A5 rejected case, A2 exit 1 and `claim-rejected:` line, A3 `(rejected)`.
- Test `test_a_claim_that_fails_twice_on_the_tip_is_accepted` — A5 accepted case, A1 record contents, A3 `(unverified)` before the run, A4 worktree list unchanged.
- Test `test_a_tip_that_moved_after_the_run_makes_the_claim_stale` — A5 stale case, A3 `(stale: <sha>)`.
- Test `test_malformed_evidence_leaves_the_claim_unverified_until_rechecked` (3 cases: `commands: 1`, a non-int exit, a non-string cmd) — R1: the gate stays blocked with `(unverified)` without raising, and `check-pre-existing` replaces the malformed file.
- Mocks: none.
