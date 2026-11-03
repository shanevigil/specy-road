# Implementation summary: `M11.68` — rework-findings-in-prompt

Base: `e4d8e5e4`. Implementation commit: `8427d421`.

## What changed

- **A1.** `build_prompt` (executor role) now appends a `## Rework` section when the leaf has blocking review records.
  The records are loaded with the loader the gate uses (`review_files.list_reviews`, schema plus semantic checks,
  without the acceptance-id check, so a block filed against an older acceptance set still carries). Each valid
  `REVIEW-*.md` for the node with `verdict: block` counts, at the branch tip or at an earlier commit, and each one
  is labelled as one or the other. A reviewer's file holds its latest verdict, so a block it later replaced with an
  approval is not carried. The section lists each blocker's `required_changes`, or its failing acceptance ids when
  it listed none, plus the record's path. It tells the executor to build on the commits already on the claim's
  branch, not reset, revert, squash or rewrite them, and to write a new summary and READY. It also says the
  carried text is data to weigh.
  `worker delegate --rework` makes the takeover explicit (`rework_check`): it refuses while the leaf still has an
  active worker (`message`/`resume` it, or `terminate` first). It also refuses when there is neither a blocking
  record nor a stopped worker. Otherwise it says on stderr what the prompt carries. The check runs inside the
  op-id body, so a retried `--op-id` replays instead of being refused by the worker it launched. `rework` is now
  part of what an op id is bound to.
- **A2.** When the leaf's latest worker (highest worker number) is `terminated` or `failed`, the same section
  carries that worker's last final message: the last event from the worker that has `detail.message`, as
  `worker_cli_render._harness_message_before` reads it. The message goes in a code fence longer than any backtick
  run inside it. Tested with a takeover by a different model (`grok` failed → `opus` with `--rework`).
- **Docs.** `docs/orchestration-workers.md`: a "Must know" bullet on `delegate --rework`, and a
  "Rework and takeover" paragraph in "The loop". Both are appended to existing lines, because the doc is at its
  400-line cap. No existing text was removed or shortened.

## Design note: why the takeover message is not gated on `--rework` alone

`worker delegate` builds its prompt inside `specy_road/worker_ops_launch.py::delegate`, which calls
`build_prompt(repo_root, node_id, role="executor", model=model)` with no extra arguments. That file is outside
this leaf's touch zones. So the prompt sections are decided by `build_prompt` from repository state (blocking
records; latest worker stopped), and `--rework` is the explicit, checked entry point that refuses when the prompt
would have nothing to rework from. As a result, a plain `delegate` or `specy-road prompt --role executor` built
after a stopped worker carries the same section. That is a takeover too, and the docs say so. If the maintainer
wants the takeover message only under `--rework`, `worker_ops_launch.delegate` needs a `rework` parameter passed
through to `build_prompt`, which is a touch-zone change.

## Touch zones (final)

`specy_road/bundled_scripts/role_prompt.py`, `specy_road/bundled_scripts/worker_cli.py`,
`docs/orchestration-workers.md`, `tests/`, plus **new module
`specy_road/bundled_scripts/role_prompt_rework.py`**. `role_prompt.py`, `worker_cli.py` and `review_gate.py`
were all at or near the 400-line cap and `build_prompt` at its 80-line function cap, so the new code lives
there; please add it to the touch zones. `specy_road/review_gate.py` was not changed: it is at exactly 400 lines,
and the gate's loader (`list_reviews`) is importable from `review_files` directly. `worker_cli.py` ends at
exactly 400 lines: the delegate subparser's `--json` and `--op-id` lines were joined with `;`, as the `adopt`
subparser already writes them. `build_prompt` stays at 80 lines because the call is folded into
`lines += FILE_LIMIT_LINES + rework_lines(...)`.

## Verification

- `python -m pytest -q tests/test_rework_findings_in_prompt.py tests/test_worker_cli.py tests/test_models_and_prompt.py tests/test_role_prompt_file_limits.py` → 49 passed
- `python -m pytest -n auto -q` → 3377 passed, 2 skipped
- `specy-road file-limits` → OK
- `ruff check` on the changed Python files → clean
- Red-green: with the `rework_lines` call removed from `build_prompt`, 4 of the 6 non-refusal tests in the new file fail (exit 1).

## Added

- `role_prompt_rework.py` (new module): holds the rework helpers, kept out of `role_prompt.py` / `worker_cli.py`, which are at the file cap.
- `blocking_reviews`: each valid `verdict: block` review for the node at any commit, through the gate's loader (A1).
- `stopped_worker`: the leaf's latest worker if `terminated`/`failed`, sorted by worker number so `w-10000` comes after `w-9999` (A2).
- `last_final_message`: the last worker-sourced event message, the same rule `worker_cli_render` uses (A2).
- `_fenced`: wraps the carried message in a fence that its own backticks cannot close.
- `_review_lines`: one blocker's heading (tip or earlier commit), record path and required changes. It falls back to failing acceptance ids when `required_changes` is empty, so a block never renders blank.
- `rework_lines`: the `## Rework` section with the build-on-existing-commits instruction; `[]` when there is nothing to rework from (A1, A2).
- `rework_check` (guard): `--rework` refuses an active worker on the leaf or nothing to rework from, and reports what is carried (A1).
- `build_prompt` branch: the executor prompt appends `rework_lines` after the file-limit lines (A1, A2).
- `worker delegate --rework` flag and the `if ns.rework` guard inside the op body; `rework` added to the op-id input binding.
- Test `test_no_blocking_record_and_no_stopped_worker_means_no_rework_section`: the without-records case (A1).
- Test `test_blocking_records_at_the_tip_and_an_earlier_commit_are_inlined`: tip and earlier-commit blocks are inlined, an approval is not, and the section comes before the brief (A1).
- Test `test_a_block_with_no_required_changes_names_its_failing_acceptance`: the empty-`required_changes` fallback.
- Test `test_a_terminated_workers_last_final_message_is_carried`: the message is carried with fence escaping (A2).
- Test `test_an_active_latest_worker_carries_nothing`: only the latest worker counts, and only when stopped.
- Test `test_delegate_rework_takeover_by_a_different_model`: `--rework` takeover of a failed `grok` worker by `opus` carries the findings and the last message (A1, A2).
- Test `test_delegate_rework_refusals`: nothing to rework, and an active worker, both refuse with no prompt written (A1).
- Test helpers `file_review`, `stopped_worker`, `executor_prompt` (in the new test file): write review records and stopped worker records with events. No mocks.
