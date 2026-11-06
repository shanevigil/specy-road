# Implementation summary: M21.44 (guidance-bypass-model-excluded-under-signed-reviews)

Base `53c1c864`; implementation commit `e3d66b9f`. Every changed path is inside the brief's touch zones; no zone was
added. Zones listed but left unchanged: `tests/test_review_eligible.py` (handoff-status rows are covered from the CLI
in the new test file).

## What changed, by acceptance item

**A1 — profile field and flag.**
- `model_profiles._structure_errors` checks `guidance_bypass_observed` with `_guidance_bypass_error`: exactly
  `{date, harness, evidence}`, `date` a real `YYYY-MM-DD` (a YAML date or a matching string; an impossible unquoted
  date is already a YAML error), `harness` in claude-code|codex|cursor|generic, and `evidence` a non-blank string.
  Any other shape makes the profile invalid with the usual profile error text.
- `models show` prints `- guidance bypass observed: <date>, <harness>: <evidence>`. `--json` already carries it in
  `front_matter`.
- The composer-2.5 profile carries the field with the §9 evidence (2026-11-06, cursor), in the template and in
  `sr/model-profiles`. The template's `aliases: [composer-2.5-fast]` makes the alias flagged too. The sr copy has no
  aliases line, so the alias is flagged there through the bundled profile.
- `orchestration_pinned.guidance_flags(repo_root)` maps each model name (`api_id` and aliases) to its record. It reads
  the bundled profiles and every profile blob committed at the integration ref (`git show`, independent of the working
  tree). Outside git it reads the working-tree profiles. A record with any shape still flags; a copy only ever adds
  flags. A `policy_source` error comes back as the error, and the refusal then refuses.
- The models an entry launches (`orchestrate_assign._launch_models`) are:
  - the routed profile's `api_id` or alias;
  - `harness_model(entry, profile api_id)`, the id a default command passes;
  - `worker_models.command_model` of `channels.cli` and `cli_resume` (read, never run).

**A2 — one function and its callers.**
- `orchestrate_assign.guidance_bypass_refusal(config, entry, profile, repo_root=None)` returns the brief's exact text.
  The signature adds an optional `repo_root`, which is where the integration-branch profiles are read from.
- It returns `None` in these cases:
  - signed_reviews is off;
  - the entry is human (`family: human`) or launches no model;
  - the entry is unflagged;
  - the roster entry with that id sets the opt-in.
- A flag read error refuses, with a message saying why.
- `guidance_problem(repo_root, config, entry)` wraps it for callers that hold only a config. It resolves the pinned
  profile only while signed_reviews is on.
- Callers:
  - **`orchestrate plan`:** `build_orchestration_plan` sets `Candidate.guidance_refusal` and `guidance_warning`.
    `_guidance_pool` filters only the pools of `_pick_executor` and `_pick_reviewers` (not `_usable`, so the
    coordinator pool is unchanged) and adds a `skipped: <reason>` note.
  - **`worker delegate`, resume and message:** `worker_ops_launch._guidance_check` runs first in `_launch_checks`,
    before the `roster_free` branch and the preflight.
  - **`review delegate`:** `review_delegate._guidance_check` runs right after `_entry`, before `_Harness`, the run
    lock and `_start` (fresh, resume and chore).
  - **`prompt`:** the new `role_prompt.role_check` helper holds `build_prompt`'s former entry, role and availability
    checks and adds the refusal for any need other than coordinator (rca counts as reviewer). `build_prompt` stays
    within file limits.
  - **`handoff status`:** `review_eligible._roster_reason` (it now takes `repo_root`).
  - **Next step:** `review_next_step._available` (it now takes `repo_root`).
  - **Gate:** `review_gate._eligibility` (`... or guidance_problem(...)`).

**A3 — opt-in and warnings.**
- Schema: `allow_guidance_bypass_model` (boolean) is in the roster entry schema, in the template and in
  `sr/schemas`, described as an at-your-own-risk override.
- `roster_local.merge_local_roster` refuses a `roster_add` entry that sets the key. `GUIDANCE_OPT_IN` is defined there
  and imported by `orchestrate_assign` (`roster_local` cannot import `orchestrate_assign` without a cycle).
- `guidance_bypass_warning` gives the launch line. It is printed once:
  - by `_launch_checks` after every refusal and the preflight;
  - by `review_delegate._guidance_check`;
  - by `prompt._run` only with `--run` and a role other than coordinator.
- Plan notes append the warning to the picked executor's or reviewer's note.
- `guidance_bypass_lines(repo_root)` gives the validate and doctor lines while signed_reviews is on, for each
  executor or reviewer entry of the pinned roster. `validate` prints them through `report_roster_profiles`
  (`roster_profile_check`); `doctor` prints them in `_print_cursor_force`.

**A4 — tests and docs.**
- `tests/test_guidance_bypass_roles.py` uses only public CLI entry points (in-process `main`; validate through
  `specy_road.cli.main`). A temp repo has the roster and profiles committed on `dev`, a fake harness that touches
  `HARNESS-RAN` and a preflight that touches `PREFLIGHT-RAN`. Signed records are filed with `review record
  --sign-key`. It covers the decision table and every extra row in the sheet.
- `tests/test_model_profile_aliases.py` checks that only the shipped composer-2.5 profile records the field.
- Docs:
  - `orchestration-roster.md` has a new section and a roster_add bullet.
  - `orchestration-workers.md`: Roster setup.
  - `orchestration-review.md`: Signed reviews, plus "What the gate cannot stop", which recommends signed_reviews
    whenever agents run with shell access.
  - `orchestration-models.md` has a new "Guidance bypass observed" subsection.
  - Both model-profiles READMEs have a Composer note.
  - Each of these names composer-2.5 and says the finding is about the model, not the Cursor harness.
- CHANGELOG: an [Unreleased] Changed entry.

## Verification
- `pytest -n 4`: 5921 passed.
- `pytest tests/test_guidance_bypass_roles.py tests/test_model_profile_aliases.py tests/test_review_eligible.py`: pass.
- `specy-road file-limits` and `ruff check` on the changed files: clean.
- Dogfood validate, export --check and digest --check: OK.
- Red-green: the new test file run against base `53c1c864` (a temporary detached worktree) gives 28 failed and 5
  passed. The 5 passing are the "unchanged" rows.

## Notes for reviewers
- `harness_model(entry, profile_api_id)` falls back to the roster id when no profile matches. A flagged id with no
  project profile (`composer-2.5` on harness cursor) is therefore caught through the bundled flag.
- A flag read error (`policy_source` fails) refuses rather than allows. Routing already fails in that state.
- When the plan's roster comes from the working tree (`orchestrate plan --roster-from-worktree`, a dry run nothing
  launches from), the opt-in is read from that roster.

## Fix round 1 (review `gpt-6.1-sol-low` at `245c471e`)

Merged `origin/WIP/improvements-0-3-1` first (clean). The four findings share one class: **the guidance decision
trusted inputs handed to it by the caller, or read as "no flag" when it could not read.** The inputs were a profile
object a drift refusal had emptied (R1), a working-tree config (R3) and a missing `repo_root` (R4), and git read
failures were swallowed (R2). The design change removes the class. Every integration-branch input the rule needs is
read once, by `orchestration_pinned.guidance_source(repo_root)`, which returns a `GuidanceSource`:
- `flags`: committed plus bundled;
- `profiles`: the committed profiles by path;
- `opt_ins`: committed roster ids;
- `signed`: the committed `policy.signed_reviews`;
- `error`.

A read that fails is an `error` and is not cached. `orchestrate_assign._guidance_hit` is the only consumer, and the
refusal, the warning and the validate/doctor lines all read its result.

- **R1, identity from a drift-emptied profile.** `_launch_models(entry, *profiles)` takes both the routed profile and
  `GuidanceSource.committed(profile)` (the committed copy at the same path). A refusal with no front matter no longer
  hides the committed `api_id` or alias.
- **R2, read failures read as no flag.** `_committed_text` separates absent (`ls-tree` succeeds with empty output, or
  the entry is a symlink) from failed (`ls-tree` or `show` returns `None`). A failed profile listing, profile blob or
  roster blob is the source's `error`, and the entry is refused. Outside git, an `OSError` reading the working tree is
  the error. One bounded rule, stated in the `guidance_source` docstring and in `docs/orchestration-roster.md`: a
  committed profile whose front matter does not parse flags nothing, and it is refused as an invalid profile wherever
  it is routed.
- **R3, opt-in from a supplied config.** The opt-in now comes only from `GuidanceSource.opt_ins`, the committed
  roster (`_opted_in` is removed). Signed reviews are on when either the caller's config or the committed policy turns
  them on, so a working-tree config cannot turn them off for the dry run either.
- **R4, the three-argument contract.** Without `repo_root`, `_source` builds a source from the bundled flags and the
  profile's own, with `config` standing for the committed roster. It never builds a read error. Every toolkit caller
  passes `repo_root`.
- Removed: `guidance_flags`, `_committed_flags`, `_opted_in`. Renamed to public names: `flags_of`, `bundled_flags`.
  No `noqa: C901` was added.

## Probes
- Every refusal, warning and lint path (plan Candidates, worker `_launch_checks`, review delegate, prompt
  `role_check` and `--run`, gate `_eligibility`, `handoff status` rows, next step, validate, doctor): all reach the
  rule only through `_guidance_hit`, so each fix applies to all of them. Result: no other route.
- R1 class, other places identity is taken from a profile object: only `_launch_models`, which now also takes the
  committed copy. Result: covered. Test: the drift test now names the file `custom-worker.md` with `api_id`
  `my-model`. It failed at `245c471e` and passes now.
- R1 class, outside git: `committed()` is a lookup in the working-tree source, so it is the same file as the routed
  one. Result: no drift there, as expected.
- R2 class, every git read in the source (profile listing, each profile blob, roster blob, the `full_sha` of the ref):
  each failure is now an error. Test: deleting a committed profile blob's loose object refuses `prompt` for an
  unrelated entry, and nothing is launched. It failed at `245c471e` and passes now.
- R2 class, the pinned resolver's own `_committed_profile_paths` (routing, not this rule): unchanged. It still reads a
  failed listing as empty. The guidance rule no longer depends on it, and changing routing is outside this leaf.
- R3 class, every config-derived permission (opt-in, signed_reviews off, availability overlay keys, `roster_add`):
  - opt-in: committed only;
  - signed off: needs config and the committed policy to agree;
  - the overlay cannot set either (`AVAILABILITY_OVERLAY_KEYS`);
  - `roster_add` is refused.
  Test: an uncommitted opt-in in an `orchestrate plan --roster-from-worktree` dry run is excluded. It failed at
  `245c471e` and passes now.
- R4 class, public functions with an optional `repo_root`: both `guidance_bypass_refusal` and
  `guidance_bypass_warning` share `_source`. Test: the three-argument contract (unflagged gives `None`, flagged is
  excluded, config opt-in gives `None`, signed off gives `None`). It failed at `245c471e` and passes now.
- A flag read error while the caller's config has signed reviews off: no refusal, because the committed policy is
  unknown. This is bounded: launches and the gate read their config from the same ref, so they already fail on that
  error.
- `ruff check specy_road tests scripts`, `specy-road file-limits`, and the full suite (`pytest -n 4`: 5927 passed):
  clean.

## Added
- `model_profiles.GUIDANCE_BYPASS_KEY` / `GUIDANCE_BYPASS_FIELDS` / `GUIDANCE_BYPASS_HARNESSES`: the field name and its closed sets (A1).
- `model_profiles._guidance_bypass_error` and its branch in `_structure_errors`: the malformed shapes make the profile invalid (A1).
- `orchestration_pinned.flags_of`, `bundled_flags`: flags from a set of profiles and the bundled set (A1); the committed read is the fix-round `guidance_source`.
- `orchestrate_assign._launch_models`: every model an entry can launch (profile, harness_model, literal --model) (A1).
- `orchestrate_assign._guidance_hit`: the shared flag, opt-in and signed lookup (A2, A3).
- `orchestrate_assign.guidance_bypass_refusal`: the one refusal function (A2).
- `orchestrate_assign.guidance_problem`: the refusal for config-only callers (gate, handoff status, next step), with the profile resolved only under signed_reviews (A2).
- `orchestrate_assign.guidance_bypass_warning`: the opted-in launch line (A3).
- `orchestrate_assign.guidance_bypass_lines`: the validate and doctor warnings (A3).
- `Candidate.guidance_refusal` / `guidance_warning`, `_guidance_pool`, `_guidance_note`: plan exclusion and notes in the executor and reviewer pools only (A2, A3).
- Branch in `build_orchestration_plan` that sets the two Candidate fields (A2).
- `worker_ops_launch._guidance_check`, and the warning print at the end of `_launch_checks`: worker refusal before roster_free and preflight; one warning per launch (A2, A3).
- `review_delegate._guidance_check`: review delegate refusal before `_Harness` and `_start`, plus the warning (A2, A3).
- `role_prompt.role_check` (moved checks plus the refusal) and the `--run` warning branch in `_run`: prompt refusal and warning; keeps `build_prompt` within file limits (A2, A3).
- `repo_root` parameter on `review_eligible._roster_reason` and `review_next_step._available`, and the guidance branch in each: handoff status rows and next step (A2).
- `review_gate._eligibility` `guidance_problem` term: the gate does not count an excluded entry's records (A2).
- `roster_local.GUIDANCE_OPT_IN` and the `roster_add` refusal branch: the opt-in counts only on the committed roster (A3).
- `allow_guidance_bypass_model` in both orchestration schemas: the opt-in key; a non-boolean value is a schema error (A3).
- `guidance_bypass_lines` loop in `roster_profile_check.report_roster_profiles` (lazy import: `orchestration_pinned` imports this module) and in `doctor._print_cursor_force`: the validate and doctor warnings (A3).
- `models_cli.cmd_show` guidance line: the text output of `models show` (A1).
- `guidance_bypass_observed` block in both composer-2.5 profiles: the shipped flag (A1).
- `tests/test_guidance_bypass_roles.py` (33 cases): the decision table and the extra rows. Its helpers are `roster`, `guidance_repo`, `on_dev`, `unflagged`, `launched`, `main_exit`, `plan`, `prompt`, `worker_delegate`, `review_delegate`, `checks`, `make_key`, `sign_approval` and `status`. It uses no mocks (A4).
- `tests/test_model_profile_aliases.py::test_only_composer_2_5_records_guidance_bypass`: the shipped data (only composer-2.5 is flagged; composer-2 is not) (A1, A4).
- Fix round 1: `orchestration_pinned.GuidanceSource` (with `committed()`), `guidance_source`, `_committed_source`, `_committed_text`, `_worktree_source`, `_source`, `_failed` and the `_SOURCES` cache. These are the single read of flags, committed profiles, opt-ins and signed policy, with read failures as errors (R1 to R4).
- Fix round 1: `orchestrate_assign._source`, for the no-repository three-argument form (R4), and the `*profiles` parameter of `_launch_models`, for committed identity (R1).
- Fix round 1 tests in `tests/test_guidance_bypass_roles.py`:
  - `test_an_uncommitted_opt_in_does_not_admit_the_model` (R3);
  - `test_an_unreadable_integration_branch_profile_refuses` (R2);
  - `test_the_refusal_needs_only_config_entry_and_profile` (R4);
  - the drift test extended to a profile file not named after its `api_id` (R1);
  - a `worktree_roster` parameter on the `plan` helper.
