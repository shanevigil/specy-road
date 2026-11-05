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

## Second merge with WIP (4af3a7b5)

The first READY attempt for the fix exposed a full-suite failure (`test_machine_paths_pass_on_this_repo`) in a
research doc the first merge brought in; WIP had fixed it in `39d5b426`, so WIP was merged again. That merge
conflicted with M15.2 (Claude reviewer on a subscription login) in `role_prompt.py` and `role_prompt_cli.py`;
both sides are kept:
- `reviewer_launch_block` (forced-bare auth refusal before the RUN record) runs only with `--run`: it refuses a
  launch, and without `--run` nothing launches (it reads only the environment and starts nothing).
- `_run_launch_mode` and `entry` on `run_default_reviewer` are kept beside `cwd`; `show_reviewer` passes the
  launch mode a run would choose (`claude_launch_decision`) so the shown command matches.
- File limit (`sr/constraints/file-limits.yaml`, 400 lines): the merge put `role_prompt.py` at 402. The reviewer
  tail of `_run` moved to the new `role_prompt_cli.reviewer_turn` and `show_cli` moved from `role_prompt_cli.py` to
  `role_prompt.py` beside `run_cli_channel`; no text was shortened (390 and 389 lines now).
- Tests: WIP's three launching `prompt --channel cli` calls in `tests/test_reviewer_auth.py` pass `--run`; the two
  tests that patched `role_prompt.run_reviewer_channel` patch `role_prompt_cli` where the call now is
  (`test_review_delegate.py`, `test_review_record_write_closure.py`), assertions unchanged.
- Verified: the M15.3 test files plus every test file either merge touched (34 files) pass, ruff, file-limits,
  and the full suite.

## Third merge with WIP

`specy-road ready` then reported WIP 25 commits ahead with a trial-merge conflict, so WIP was merged once more.
WIP's new specy-road-filled record field `sibling_heads` conflicted with `harness_model`/`model_mismatch` in
`review_answer.FILLED_BY_SPECY_ROAD`, the record schema and the output-schema test; all three fields are kept in
each. The `harness_model` schema description now says it comes from init or result events and, on a mismatch, is
the reported model that differs. Verified: 35 test files (M15.3's plus every test file the merges touched), 580
passed; full suite 5028 passed; ruff; file-limits.

## Fix round 2 (gpt-6.1-sol-low blocked 9f1cbe63)

Merged `origin/WIP/improvements-0-3-1` first (clean; roadmap and planning files only, no code or tests).

- **Finding (A2):** with roster `id: review-label`, `harness: cursor`, `harness_model: gpt-6.1-sol` and no profile,
  preview and launch both passed `--model review-label`. Class: a path that turns a roster entry into a model flag
  without the documented resolver. Fix: `role_prompt_cli.model_problem(prof, entry)` resolves only through
  `orchestration_config.harness_model` (the entry's `harness_model`, else the profile's `api_id`, else the roster
  `id`, as `docs/orchestration-models.md` documents) and refuses a model that resolves to none.
  - `reviewer_command` (used by the preview, the refusal before the run record, and the launch) takes its model from
    it, and so does `run_default_reviewer`, which builds the default `--model`. That function no longer computes the
    model itself, so the two can no longer disagree.
  - A `harness_model` now also rescues a profile whose `api_id` is `unknown`, where before that entry was refused.
- **Tests:**
  - A public CLI test with exactly that roster shape. The preview shows `--model gpt-6.1-sol`, and the launch argv
    passes `--model gpt-6.1-sol` and never `review-label`. The filed record has the harness's own name (`GPT 6.1 Sol`)
    as `harness_model`, which matches through the entry's `harness_model`, so there is no mismatch.
  - A unit test of `model_problem`: `harness_model` over an unknown `api_id`; unknown with no `harness_model` refused;
    no profile gives the roster id.
  - Existing refusal tests keep their "resolves to no API model id" assertion; the message still says it.

## Fix round 3, root cause (gpt-6.1-sol-low blocked df0142e3)

Merged `origin/WIP/improvements-0-3-1` first. It was clean: roadmap and planning files only. M15.3's zones are unchanged, and `review_delegate.py` and `orchestration_config.py` are still outside them.

**Root cause.** A roster entry had no single authoritative "effective model". Resolution (`model_problem`), validation (empty only) and comparison (`check`, which accepted the roster id, `harness_model` and every profile identity) each had their own idea of it. The three findings are that one gap seen from three places:
- A2: a `harness_model` or `id` of `unknown` passed validation.
- A4: a `harness_model` naming another model was still matched through the profile's names.
- A1: the preview depended on launch-only state.

**Design.**
- `review_model_check.resolve_effective_model(entry, profile)` applies `orchestration_config.harness_model` (the entry's `harness_model`, else the profile's `api_id`, else the `id`), then rejects an empty or `unknown` result from any of those steps.
- `role_prompt_cli.model_problem` is that function plus the refusal message. Every prompt path that shows or launches a reviewer takes its model from it: the preview (`show_reviewer`), the refusal before the run record, `run_reviewer_channel`, and `run_default_reviewer`'s `--model`.
- `check` compares the reported model with the effective model only, after `normalise`. The profile's other names (`display_name`, `aliases`, file name) count only when the effective model is that profile's model. An entry with no effective model matches nothing.
- `run_and_file` looks up its entry and profile by exact roster id (`review_model_check.rostered`). The old `model_names.roster_match` returned the first entry whose id, `harness_model` or profile alias matched, which could be a different entry.
- **A1:** `reviewer_turn` handles the preview before any worktree enforcement. Without `--run` it always prints the command, as "would run in the leaf worktree (none found)" plus `note: --run would refuse: …` when there is none. With `--run` the worktree refusal is unchanged.

**Tests.**
- New `tests/test_effective_model.py`, split out for the 400-line test file cap. It has one parametrized table of 18 rows over `harness_model` set, unset, empty or `unknown`; profile present, absent or `unknown`; `id` `unknown`; and reported model matching, not matching or absent. Each row asserts `resolve_effective_model`, `model_problem` (the value preview and launch use) and `check`. The earlier `model_problem` unit test moved there too.
- `test_preview_without_a_claimed_worktree_still_prints_the_command` in `tests/test_prompt_channel_cli_run.py`.
- All earlier tests pass unchanged, including the public CLI `review-label` test (preview and launch both pass `--model gpt-6.1-sol`).

**Not done:** "use it for delegate". `review_delegate.py` resolves its model with `harness_model(entry, api)` and passes `""` for a missing profile, which gives the harness default instead of the roster id, and it doesn't reject `unknown`. The file is outside this leaf's zones and A5 puts delegate's launch path out of scope, so it was not changed. Fixing it means adding `review_delegate.py` to the zones (or a follow-up leaf) and calling `resolve_effective_model` there. `prompt` has no resume path.

## Fix round 4 (gpt-6.1-sol-low blocked 1dafbf68)

Merged `origin/WIP/improvements-0-3-1` first. It was clean, and WIP added tests only.

- **Finding (A2):** `--for\` + newline + `ce` in a custom reviewer command passed the bypass check, but `sh` joins
  the line continuation and runs `--force`.
- **Class:** the tokenizer reads the command differently from `sh` in a way that hides a word. Probing found a
  second instance: shlex treats `#` as a comment even inside a word, so `agent a#b --force` lost its `--force`, while
  `sh` passes `a#b` and `--force`.
- **One bounded rule, stated once** (in `bypass_problem`'s docstring, the `prompt --help` text from the
  `role_prompt` module docstring, and `docs/orchestration-reviewer-output.md`): the command is split as `sh` reads its
  words, erring towards seeing more.
  - Every backslash-newline is removed first.
  - `shlex` runs in POSIX mode with `punctuation_chars` and no comment character.
  - A token whose name (the part before any `=`) is exactly a bypass flag refuses the command.
  - Conservative clauses: a flag inside a `#` comment refuses, and so does a backslash-newline inside single quotes,
    where `sh` keeps it.
  - Out of scope, as documented: what the shell expands at run time (`$VAR`, `$'...'`, `$(...)`, backquotes, brace
    expansion, aliases, scripts).
- **No added branches.** The change is the input passed to the lexer and one attribute set on it; the function's
  control flow is unchanged.
- **Tests:**
  - The rule table (`test_bypass_flags_are_found_as_sh_reads_its_words`) gains one row per clause: a continuation
    unquoted, inside double quotes, and inside single quotes (conservative); a mid-word `#`; and a flag in a comment
    (conservative).
  - The public CLI refusal test now takes whole commands through a YAML block scalar, so a real backslash-newline
    reaches the roster. It asserts refusal before launch: exit 1, no process, no run record.
  - All six new rows fail on `1dafbf68`'s code with this test file (exit 1), and pass now.
- **File limit:** this round's own new docstring paragraph was reflowed to 120 columns with no words removed;
  `role_prompt_cli.py` is at 400 lines.

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

- Fix round 2: the preview of a reviewer with a `harness_model` and no profile shows `--model gpt-6.1-sol` (tested
  through the public CLI).
- Fix round 2: its launch argv passes `--model gpt-6.1-sol` and not the roster label (tested through the public CLI).
- Fix round 2: `run_default_reviewer` called directly with no entry resolves the model the same way (`{"id": model}`);
  the existing direct-call tests in `test_headless_limits_denials.py` pass.
- Fix round 2: a custom `channels.cli` carries its own `--model`, which is the roster's command as written;
  `model_problem` still refuses one whose entry resolves to no model (tested).
- Fix round 2: `prompt` has no resume path, so there is no other launch to check (grep for `resume` and `--model` in
  `role_prompt.py` and `role_prompt_cli.py`).
- Fix round 2: the model check compares the reported model against the entry's `harness_model` as well (`same_model`):
  `GPT 6.1 Sol` matches (tested).
- Fix round 2, `review delegate` (`review_delegate.py:117-118`, outside the zones): it already resolves through
  `harness_model`, but it passes `""` for a missing profile, which gives `None` (the harness default) instead of the
  documented roster id, and it does not validate. Not changed: the file is outside this leaf's zones and A5 puts
  delegate's launch path out of scope. It needs a follow-up leaf.
- Fix round 2, other callers of `harness_model` outside the zones (`worker_ops_launch.py`, `entry_routing`): executor
  and routing paths, not reviewer launches; not changed.

- Fix round 3 / A2: a `harness_model` of `unknown` or `Unknown`, a profile `api_id` of `unknown`, and an `id` of `unknown` with no profile all resolve to no model and are refused (table rows).
- Fix round 3 / A2: an empty `harness_model` counts as unset and falls through to the profile (table row).
- Fix round 3 / A2: every prompt path that builds a model flag uses `model_problem` → `resolve_effective_model`: `show_reviewer`, the refusal in `reviewer_turn`, `run_reviewer_channel` and `run_default_reviewer` (grep for `api_id` and `harness_model(` in `role_prompt_cli.py`; no other computation remains).
- Fix round 3 / A4: `harness_model: gpt-6.1-sol` with the Opus profile and a reported `claude-opus-5-5` or `Claude Opus 5.5`: mismatch (table rows).
- Fix round 3 / A4: the same entry with `GPT 6.1 Sol` reported: match (table row).
- Fix round 3 / A4: a `harness_model` naming the profile's own model keeps the profile's names, including when the profile's `api_id` is `unknown` (table row).
- Fix round 3 / A4: the roster label reported (`opus`, `review-label`) when it isn't the effective model: mismatch (table rows).
- Fix round 3 / A4: no effective model and a reported model: mismatch; nothing reported: unreported (table rows).
- Fix round 3 / A4: other users of the comparison: `check_run` → `check` in `run_and_file`, and the gate reads only the filed `model_mismatch`. `worker_models.mismatch_note` (worker usage, outside the zones) still uses `same_model` with profile names; not a reviewer record, so not changed.
- Fix round 3 / A4: entry lookup for the check is by exact roster id (`rostered`), not `roster_match`'s first match on id, `harness_model` or profile alias.
- Fix round 3 / A1: preview with no claimed worktree: exit 0, the command printed, a note naming the `--run` refusal, and no process started (tested).
- Fix round 3 / A1: `--run` with no worktree is still refused (existing test).
- Fix round 3 / A1: the preview still refuses a command it can't show (unknown model, bypass flag, no `channels.cli`), with exit 1 and no process (existing tests).
- Fix round 3 / A1: other preview paths that hit launch-only state: `show_cli` (other roles) never needed a worktree, and the run lock and auth block in `main` run only with `--run` (read `role_prompt.main` and `_run`).
- Fix round 3 / existing fixtures: tests whose fake harness reports the roster id still match, because their entries have no profile, so the effective model is the id (601 targeted tests pass).

- Fix round 4: a backslash-newline outside quotes, inside double quotes, and inside single quotes: all refused (table rows; `sh -c` confirmed it joins the first two and keeps the third).
- Fix round 4: a mid-word `#` (`a#b --force`): refused (table row; `sh -c` confirmed `--force` is passed). A real comment that mentions a flag: refused, conservatively (table row).
- Fix round 4: other quoting forms that `sh` concatenates (`--for''ce`, `--for"ce"`, `--for\ce`): shlex in POSIX mode already yields `--force` (probed).
- Fix round 4: other places in the zones that tokenize a reviewer command for safety: only `bypass_problem`, which runs on every `channels.cli` before launch (grep for `shlex` in `role_prompt_cli.py` and `role_prompt.py`).
- Fix round 4: `worker_adapter_base.reviewer_cli`'s agy check (`shlex.split`, outside the zones) runs after `bypass_problem` in the prompt path, so anything it misses is already refused; not changed.
- Fix round 4: `review delegate`'s custom commands have no bypass check. Outside the zones and out of A5's scope; not changed (as in earlier rounds).
- Fix round 4: text specy-road substitutes into the command after the check (`{prompt}`, `"<prompt>"`, `{effort}`): the prompt goes in as one quoted argument or a file path, and the effort flags come from fixed adapter tables, so neither adds roster-controlled words.
- Fix round 4: an unbalanced quote is still refused (existing test).
- Fix round 4: complexity. `bypass_problem` has no new branch, and there is no `noqa: C901` in the zoned files (grep).

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
- `role_prompt_cli.reviewer_turn`: file limit after the second merge; the reviewer tail of `role_prompt._run`, moved unchanged.
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
