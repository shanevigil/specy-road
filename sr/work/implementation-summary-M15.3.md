# Implementation summary: M15.3

Branch `feature/rm-prompt-channel-cli-launches-nothing-without-run`. Base is `762bc1b0`, after merging `origin/WIP/improvements-0-3-1`, which added `specy_road/review_gate.py` and `specy_road/review_answer.py` to the zones and reworded A4.

## What changed

- **A1:** `specy-road prompt` gets `--run` and `--worktree PATH` (`role_prompt.py`).
  - Without `--run`, `--channel cli` writes the prompt and prints `would run …; add --run to launch it`. This applies to every role (`show_cli`, `show_reviewer` in `role_prompt_cli.py`).
  - Nothing starts without `--run`: no preflight, no reviewer run lock and no run record.
  - Without `--run`, a reviewer prompt uses the "file it yourself" ending, because nothing reads the session back.
  - `--run` without `--channel cli` is an argparse error.
  - The help for `--channel` and `--run` says which one launches.
  - CHANGELOG has an `[Unreleased] / Fixed` entry. No version heading was added.
- **A2:** `role_prompt_cli.reviewer_command` builds the reviewer's command from the roster entry only.
  - A claude-code, codex or cursor entry without `channels.cli` uses the adapter's read-only command with the entry's model.
  - Any other entry uses its `channels.cli`. The profile's `access.cli` is never used for a reviewer.
  - Refused before launch, with the reason, and from `_run` before any run record or process exists:
    - a missing `channels.cli`
    - an API id that is empty or `unknown`
    - a `channels.cli` that passes `--force`, `--yolo` or `--dangerously-skip-permissions` (checked by `bypass_flag`)
- **A3:** `role_prompt_cli.leaf_worktree` picks where the reviewer runs.
  - It is the worktree that `git worktree list --porcelain` shows with the claim's branch checked out. `--worktree PATH` overrides it.
  - With no such worktree, `prompt` refuses. The message names `--worktree PATH` and `git worktree add work/.worktrees/<codename> <branch>`.
  - The worktree is passed as `cwd` through `run_default_reviewer` and `run_custom_reviewer` into `run_and_file`. The launch and the tripwire's `git status` snapshots both use it. Filing still happens against the main checkout's `work/reviews/`.
  - The cursor adapter needed no workspace flag, because `agent` uses its cwd.
- **A4:** new module `specy_road/review_model_check.py`.
  - `normalise` is re-exported from `model_names`. `reported_model` takes the first `system/init` model through `worker_adapter_parsers.init_model`. `check` returns match, mismatch or unreported, using `model_names.same_model` against the entry id, `harness_model` and the profile names. It also has `check_note` and `model_mismatch_problem`.
  - `review_record_write.run_and_file` runs the check, prints a warning on a mismatch or an unreported model, and passes `model_check` to `file_review`. `file_review` writes `harness_model`, and `model_mismatch: true` on a mismatch.
  - The schema gains both fields. `review_answer.FILLED_BY_SPECY_ROAD` lists both, so a reviewer's output schema cannot set them.
  - `review_gate._eligibility` has one added check, `model_mismatch_problem(review.data)`. A mismatched record lands in `gate.ineligible` with the reason `harness ran a different model (...)`.
  - `review_eligible.py` needed no change: `_rejected` already reports `gate.ineligible` reasons, and a test confirms the row.
- **A5:** `review delegate` is unchanged (`review_delegate.py` is outside the zones). It calls `file_review` without `model_check`, so its records carry no `harness_model` yet.
- **Docs:** updated `docs/orchestration-reviewer-output.md` (new M15.3 section, the specy-road-filled field list, and the agy row no longer mentions `access.cli`) and `specy_road/templates/specyrd/commands/specyrd-prompt.md`.

## Merge with WIP (1b8fa35f)

`origin/WIP/improvements-0-3-1` (M15.40, M15.37 and others) conflicted in `role_prompt_cli.py`; both sides kept:
WIP's `harness_bin` (passed from the roster entry to `run_default_reviewer` and, in `show_reviewer`, to the
dry-run's `reviewer_launch`), `checked` launch and `_refused` helper (now also used for `reviewer_command`'s
refusal), alongside this leaf's roster-only `reviewer_command`, leaf-worktree `cwd` and model check. Re-verified:
the M15.3 test files plus every test file the merge touched (514 passed), ruff, file-limits, full suite.

## Final touch zones

The zones as listed in the roadmap, including the planner's added `review_gate.py` and `review_answer.py`. `review_eligible.py` is in the zones but is unchanged. There are no new modules outside the zones.

## Verification

- `pytest -n 4`: 4882 passed. Before that, the targeted run over the affected test files passed, and so did `tests/test_prompt_channel_cli_run.py` (21 tests).
- `ruff check specy_road tests/...`: clean.
- `specy-road file-limits`: OK.

## Test edits to existing files

- Every existing test that calls `prompt --channel cli` and expected a launch now passes `--run`. That is the old meaning; no assertion was changed.
- `tests/review_delegate_helpers.py`: the fake harness's init event reports `step.get("model", "fake")`. `verdict_step` sets `model` to the rostered model, as a real harness reports. Without that, every fake-filed record would be a mismatch, since the fake reported `fake` for roster `opus`.
- `tests/test_review_record_write.py`: the expected specy-road-filled set includes the two new fields.

## Added

- `specy_road/review_model_check.py`: `reported_model`, `check`, `check_note`, `model_mismatch_problem`, `MISMATCH_REASON`, and `normalise` re-exported. A4's shared check, used by `prompt --run` and the gate.
- `role_prompt_cli.BYPASS_FLAGS` and `bypass_flag`: A2 refuses custom reviewer commands that skip permissions.
- `role_prompt_cli.reviewer_command`: A2's roster-only command, with no `access.cli` fallback and refusing an unknown API id.
- `role_prompt_cli.leaf_worktree`: A3, where a reviewer runs, or the refusal.
- `role_prompt_cli.show_cli` and `show_reviewer`: A1, print the command without starting anything.
- `cwd` parameter on `run_reviewer_channel`, `run_default_reviewer`, `run_custom_reviewer` and `run_and_file`: A3, the launch and snapshot directory.
- `model_check` parameter on `file_review`: A4, writes `harness_model` and `model_mismatch`.
- `role_prompt` `--run`, `--worktree`, the `--run`-needs-cli parser error, and the dry-run branch in `_run`: A1 and A3.
- One `or model_mismatch_problem(...)` in `review_gate._eligibility`: A4, the gate excludes a mismatch.
- Two names in `review_answer.FILLED_BY_SPECY_ROAD`: a reviewer cannot set `harness_model` or `model_mismatch` itself.
- Schema fields `harness_model` and `model_mismatch` (`const: true`): A4, the record carries them.
- Test fixture `started`, which records every non-git `Popen` in `tests/test_prompt_channel_cli_run.py`: A1's "no subprocess starts" assertion.
- Tests in `tests/test_prompt_channel_cli_run.py`:
  - no launch without `--run` for executor, reviewer and rca (no process, no preflight, no run record)
  - help text
  - `--run` needs cli
  - no `access.cli` fallback
  - cursor's read-only command uses the entry's model
  - unknown API id refused
  - three bypass flags refused
  - a run from the main checkout launches in the leaf worktree (cwd asserted)
  - no-worktree refusal
  - the `--worktree` override
  - `check` for match, display-name match, mismatch and unreported
  - `reported_model` reads the first init event
  - a mismatch is filed and flagged, excluded from the gate, and reported by `review_eligible`
  - an unreported model is a warning and the record counts
- Mocks: none new. The existing `fake_reviewer_run` is reused, and `review_delegate_helpers.FAKE` gets the per-step `model` described above.
