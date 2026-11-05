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
    - a `channels.cli` that passes `--force`, `--yolo` or `--dangerously-skip-permissions` (checked by `bypass_problem`; see the fix round)
- **A3:** `role_prompt_cli.leaf_worktree` picks where the reviewer runs.
  - It is the worktree that `git worktree list --porcelain` shows with the claim's branch checked out. `--worktree PATH` overrides it.
  - With no such worktree, `prompt` refuses. The message names `--worktree PATH` and `git worktree add work/.worktrees/<codename> <branch>`.
  - The worktree is passed as `cwd` through `run_default_reviewer` and `run_custom_reviewer` into `run_and_file`. The launch and the tripwire's `git status` snapshots both use it. Filing still happens against the main checkout's `work/reviews/`.
  - The cursor adapter needed no workspace flag, because `agent` uses its cwd.
- **A4:** new module `specy_road/review_model_check.py`.
  - `normalise` is re-exported from `model_names`. `reported_models` collects the first `system/init` model (through `worker_adapter_parsers.init_model`) and, since the fix round, each `result` event's model; `check_run` turns them into `(harness_model, state)`. `check` returns match, mismatch or unreported, using `model_names.same_model` against the entry id, `harness_model` and the profile names. It also has `check_note` and `model_mismatch_problem`.
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

## Fix round 1 (gpt-6.1-sol-low blocked 0d291615)

Merged `origin/WIP/improvements-0-3-1` first (clean; roadmap and research files only). Each finding was fixed as
a class, with one validation function per concern in `role_prompt_cli.py`:

- **Unknown model on a custom command (A2).** Class: a reviewer launch path that skipped the model check.
  `model_problem(prof, model)` now runs first in `reviewer_command`, which every launch path (`_run`'s up-front
  refusal, `show_reviewer`, `run_reviewer_channel`) goes through, so a `channels.cli` reviewer is checked as well.
- **Bypass flag next to a shell operator (A2).** Class: a flag the word splitter left glued to shell syntax.
  `bypass_problem(cli)` applies one bounded rule, stated in its docstring. The command is split with
  `shlex.shlex(posix=True, punctuation_chars=True, whitespace_split=True)`, so `; & | ( ) < >` become tokens of their
  own and quotes are removed. A token whose name (the part before any `=`) is exactly one of `BYPASS_FLAGS` refuses
  it. A command that cannot be tokenized is refused, where before it fell back to `str.split`. Out of scope, as
  documented: flags the shell produces at run time (`$VAR`, `$(...)`, aliases, scripts).
  - Deliberate reading of "a quoted `--force` argument must not match": a whole-quoted `'--force'` reaches the
    program as `--force`, so it is refused (and tested). A quoted argument that only mentions `--force` among other
    words (`"never pass --force here"`) is one token and does not match (tested).
- **Explicit `--worktree` (A3).** Class: any reviewer cwd that is not the leaf's tree. `worktree_problem(root,
  path, t)` checks three things for both the explicit and the auto-found path:
  - the path is the top of a git checkout
  - its current branch is not the integration branch (`resolve_integration_defaults`)
  - its `HEAD` is the claimed branch's tip (when there is a claim)
- **Result-only model (A4).** Class: a reported model the reader did not look at. `reported_models` reads the first
  init event and every `result` event (its `model`, or the one key of its `modelUsage`). `check_run` returns a
  mismatch if any reported model differs, so a printed line can add a mismatch but never hide one.
  `run_and_file` uses `check_run`, and `file_review` and the gate are unchanged.

## Probes

- Unknown API id with a `channels.cli`, run and dry run: refused before launch, with no process and no run record (tested).
- Unknown API id on the default adapter path: still refused (existing test).
- Other callers of the model check: `reviewer_command` is the only reviewer command resolver in `prompt`; `_run`, `show_reviewer` and `run_reviewer_channel` all use it (grep).
- `review delegate` resolves its model differently (an entry's `harness_model` wins over the profile's `api_id`): left unchanged, since `review_delegate.py` is outside the zones and A5 puts its launch path out of scope.
- Operators glued to a flag (`--force;`, `--force&&x`, `(--force)`, `(agent -p --force)`, `--yolo=true|cat`, `--dangerously-skip-permissions>log`): all refused (tested).
- Text that only mentions a flag (`"never pass --force here"`, `--forceful`): not matched (tested).
- An unbalanced quote: refused, where the old `str.split` fallback accepted it (tested).
- Other places a reviewer command gets text added: the agy flags from `reviewer_cli` and `{effort}` are added by specy-road from fixed lists, so neither carries roster text.
- Executor commands (`run_plain_cli`): not a reviewer, so out of A2's scope; unchanged.
- `--worktree` naming the main checkout on `dev`: refused with the integration-branch message (tested).
- `--worktree` naming a subdirectory, or a worktree at `feature~1`: refused (tested).
- `--worktree` naming a detached worktree at the tip: accepted (tested).
- The auto-found worktree: now goes through the same `worktree_problem` check; the main-checkout-on-the-claimed-branch case still passes (existing tests).
- Other ways for a reviewer to run outside a checked worktree: `run_reviewer_channel` is called only from `_run` with `cwd` from `leaf_worktree`. `run_default_reviewer` and `run_custom_reviewer` still default `cwd` to `root` for direct callers (tests only; grep).
- Model reported only in the result's `model`: mismatch filed and excluded from the gate (tested end to end).
- Model reported only in a single-key `modelUsage`: read (tested).
- Multi-key `modelUsage`: names no single model, so it is ignored, not misread (tested).
- A matching init with a mismatching result: mismatch (tested).
- A forged model line can only add a mismatch, which excludes the record. It cannot turn a mismatch into a match. A harness that reports nothing (Codex) is unreported, which counts anyway, so forging gains nothing.
- Deep-nested JSON in the output: `result_model` catches `RecursionError`, and returns nothing (tested).
- Other readers of the reported model: `worker_runner` uses `init_model` only for worker usage, outside this leaf; not changed.

## Final touch zones

The zones as listed in the roadmap, including the planner's added `review_gate.py` and `review_answer.py`. `review_eligible.py` is in the zones but is unchanged. There are no new modules outside the zones.

## Verification (fix round 1)

- The M15.3 test files plus every test file the earlier merge touched: 534 passed.
- `tests/test_prompt_channel_cli_run.py`: 41 passed.
- `ruff check specy_road tests`: clean.
- `specy-road file-limits`: OK.

## Verification (first round)

- `pytest -n 4`: 4882 passed. Before that, the targeted run over the affected test files passed, and so did `tests/test_prompt_channel_cli_run.py` (21 tests).
- `ruff check specy_road tests/...`: clean.
- `specy-road file-limits`: OK.

## Test edits to existing files

- Every existing test that calls `prompt --channel cli` and expected a launch now passes `--run`. That is the old meaning; no assertion was changed.
- `tests/review_delegate_helpers.py`: the fake harness's init event reports `step.get("model", "fake")`. `verdict_step` sets `model` to the rostered model, as a real harness reports. Without that, every fake-filed record would be a mismatch, since the fake reported `fake` for roster `opus`.
- `tests/test_review_record_write.py`: the expected specy-road-filled set includes the two new fields.

## Added

- `specy_road/review_model_check.py`: `result_model`, `reported_models`, `check_run`, `check`, `check_note`, `model_mismatch_problem`, `MISMATCH_REASON`, and `normalise` re-exported. A4's shared check, used by `prompt --run` and the gate.
- `role_prompt_cli.BYPASS_FLAGS` and `bypass_problem` (replaces `bypass_flag`): A2, the one tokenizer rule for permission-bypass flags.
- `role_prompt_cli.model_problem`: A2, the unknown-API-id check, shared by every reviewer launch path.
- `role_prompt_cli.worktree_problem` and `_claimed_worktree`: A3, one check for any reviewer cwd (explicit or found), and the `git worktree list` lookup split out of `leaf_worktree`.
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
  - `reported_models` reads the first init event and every result event (`model`, single-key `modelUsage`), and survives deep-nested JSON
  - `check_run`: result-only mismatch, single-key `modelUsage` display-name match, a matching init does not hide a mismatching result, nothing reported
  - end to end: a model reported only in the result is filed with `model_mismatch` and excluded from the gate
  - a custom `channels.cli` with an unknown API id is refused before launch (run and dry run)
  - `bypass_problem` finds `--force;`, `--force&&x`, `(--force)`, `(agent -p --force)`, `'--force'`, `--yolo=true|cat` and `--dangerously-skip-permissions>log`; does not match `"never pass --force here"`, `--forceful` or `--mode ask`; refuses an unsplittable command; end to end with `--force;`
  - `--worktree` naming the integration checkout, a subdirectory, or a worktree not at the claimed tip is refused
  - a mismatch is filed and flagged, excluded from the gate, and reported by `review_eligible`
  - an unreported model is a warning and the record counts
- Mocks: none new. The existing `fake_reviewer_run` is reused, and `review_delegate_helpers.FAKE` gets the per-step `model` described above.
