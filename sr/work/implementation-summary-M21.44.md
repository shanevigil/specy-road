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

## Added
- `model_profiles.GUIDANCE_BYPASS_KEY` / `GUIDANCE_BYPASS_FIELDS` / `GUIDANCE_BYPASS_HARNESSES`: the field name and its closed sets (A1).
- `model_profiles._guidance_bypass_error` and its branch in `_structure_errors`: the malformed shapes make the profile invalid (A1).
- `orchestration_pinned._flags_of`, `_bundled_flags`, `_committed_flags`, `guidance_flags`: read flags from bundled profiles and committed integration-branch blobs, independent of drift (A1).
- `orchestrate_assign._launch_models`: every model an entry can launch (profile, harness_model, literal --model) (A1).
- `orchestrate_assign._guidance_hit`, `_opted_in`: the shared flag lookup and the committed-roster opt-in (A2, A3).
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
