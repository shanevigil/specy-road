# Implementation summary for M11.12

## Summary

New command `specy-road ready <NODE_ID> --model <roster id> --verify '<cmd>=<exit>' ...` writes `READY-<model>.md` into the node's hand-off directory (the main checkout's `work/reviews/<NODE_ID>/`, from any worktree). It takes everything except the verifiers from git: `branch` is the checked-out branch, `commit` is the commit under review at `HEAD` (from `resolve_target(..., "HEAD")`, so it is the same commit `handoff status` compares against), `base` is the merge base with the integration branch, and `changed_paths` is `diff_paths(base...commit)`. The file is built with `render_front_matter` and checked with `load_ready` (schema, node, registered branch, acceptance ids), the same loader `handoff status` uses, before anything is written. If any check fails, nothing is written and it exits 1.

A `--verify` with a non-zero exit is refused, and the error points at `--red-green`. `--red-green '<cmd>=<exit>'` is for a check that fails without the fix on purpose. Those go in the body under `## Red-green evidence`, not in `verify`, so they never gate. `--note` adds free text to the body. The handoff schema is not in my touch zones, so I added no new front-matter field. Putting red-green evidence in the body keeps every file the command writes valid under the current schema.

The executor preamble (step 4) now tells executors to write READY with this command and to pass deliberate fails-without-the-fix checks as `--red-green`. Hand-written READY files are still read and validated by `handoff status` as before. I did not forbid writing by hand, because the command has no `blocked_on` flag and a blocked executor still writes `blocked_on` from the template.

## Changes

- `specy_road/review_gate_ready.py`: `parse_check`, `ready_body`, `cmd_ready`, `add_ready_parser` (`_refuse` helper).
- `specy_road/bundled_scripts/review_cli.py`: registers the `ready` subparser (it already owns `handoff` and `review`); docstring.
- `specy_road/cli.py`: `"ready": "review_cli.py"` in `_FORWARDED`.
- `specy_road/cli_usage.py`: usage entry.
- `specy_road/bundled_scripts/role_prompt_rca.py`: executor step 4 names the command.
- `docs/orchestration-review.md`: one paragraph on writing READY with the command.
- `tests/test_ready_command.py`: new; `tests/test_models_and_prompt.py`: one assertion updated to the new step-4 wording (A2 changes that text). The assertion is no weaker.

The prompt writes the flag as `--model=<id>`, not `--model <id>`. With the spaced form, the first full run failed `tests/test_review_round6_policy.py::test_a_profile_cli_launches_only_generic_workers[cursor-…]`. That test's stub harness echoes its whole argv, prompt included, and the test splits it on whitespace to check that `--model` was not passed to Cursor's `agent`. A bare `--model` token in the prompt text therefore read as a launch flag. The test passed at base, and I did not loosen it. Its check is brittle, though: any prompt text containing ` --model ` trips it. The reviewer preamble already contains such text, so a reviewer-delegation variant of the test would trip too. That may deserve its own leaf.

Touch zones: the declared ones were accurate; nothing outside them changed. Not changed (outside the zones): `specy_road/bundled_scripts/do_next_prompt.py` still tells a non-orchestrated finish flow to copy `work/handoff-ready.template.md`. The specyrd command stubs and `suggested_prompts/` do not mention the new command either. Both may want a follow-up.

## Verification

- `python -m pytest -q tests/test_ready_command.py tests/test_models_and_prompt.py tests/test_review_cli.py tests/test_worktree_paths_agree.py tests/test_review_round6_policy.py` → all passed.
- `specy-road file-limits` → OK (`review_cli.py` is at 398 lines; the command lives in `review_gate_ready.py` for that reason).
- `python -m pytest -q` (full suite) → 2984 passed, 2 skipped (after the `--model=` change; before it, 1 failed as described above).

## Walkthrough

1. `review_gate_ready.cmd_ready`: parse, refuse failing verifiers, resolve the target at `HEAD`, build, validate through `load_ready` in a temp dir, then `write_review` into `reviews_dir`.
2. `role_prompt_rca.executor_preamble` step 4.
3. `tests/test_ready_command.py`: a valid write from a linked worktree (file lands in the main checkout, `handoff status` shows `in-review` with no verifier problem), a refused failing verifier, a refused malformed spec and unregistered branch, a hand-written READY without front matter still reported invalid, and the prompt text.

## Added

### Helpers
- `parse_check`: splits `'<cmd>=<exit>'` on the last `=` so commands containing `=` survive; user input, so it raises on a malformed spec.
- `ready_body`: renders `--red-green` rows and `--note` into the body, keeping red-green evidence out of the gating `verify` list.
- `cmd_ready`: the command.
- `_refuse`: prints `error: …` to stderr and returns 1, the same as `review_cli._fail` (not imported to avoid a cycle: `review_cli` imports this module).
- `add_ready_parser`: argparse wiring, kept here so `review_cli.py` stays under the 400-line cap.

### Branches / guards
- Refuse a non-zero `--verify` exit: A1.
- Refuse when there is no checked-out branch, merge base or commit: a detached `HEAD` or a repository without the integration branch cannot produce valid `branch`/`base`.
- Refuse when `diff_paths` returns `None`: git could not answer, and an empty `changed_paths` would be false.
- Validate through `load_ready` before writing: so the command can never write a file that `handoff status` would call invalid (wrong branch, bad agent id).

### Mocks
- none

### Tests
- `test_ready_writes_a_valid_hand_off_from_a_worktree`: A1 valid write, the main-checkout directory, the command is registered, red-green rows do not gate.
- `test_ready_refuses_a_failing_verifier_and_writes_nothing`: A1 refusal.
- `test_ready_refuses_a_bad_spec_and_an_unregistered_branch`: the two input guards.
- `test_handoff_status_still_validates_a_hand_written_ready`: A2, a hand-written file without front matter (the field failure) is still reported invalid.
- `test_executor_prompt_tells_the_executor_to_write_ready_with_the_command`: A2/A3 prompt text.
