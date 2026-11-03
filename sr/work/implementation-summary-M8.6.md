# Implementation summary: M8.6 — Candidate harness profiles: Copilot CLI reviewer and Antigravity agy generic

Branch `feature/rm-candidate-harness-profiles-copilot-cli-reviewer-and-antigravity-agy-generic`, after merging
`origin/WIP/improvements-0-3-1` at `03332298` (fast-forward; it adds `tests/test_models_and_prompt.py` to the
touch zones). Implementation commit `aab42bf3`.

## What changed

- `specy_road/templates/project/model-profiles/github-copilot/copilot-gemini-4-argon.md` (new): the Copilot
  CLI reviewer profile. Command:
  `copilot -p "<prompt>" -s --no-ask-user --no-auto-update --model=gemini-4-argon --allow-tool='shell,write' --deny-tool='shell(git push),shell(git push:*),shell(git commit),shell(git commit:*),shell(gh),shell(gh:*),memory'`.
  No `--autopilot`, `--share-gist`, `--allow-all` or `--yolo`. It is one-shot: `-p` exits after the reply, and
  there is no `--resume`. Role scores: coordinator 1, executor 1, reviewer 3.
- `specy_road/templates/project/model-profiles/google-antigravity/agy-gemini-4-argon-high.md` (new): the
  Antigravity `agy` generic profile. Command:
  `agy -p "<prompt>" --output-format json --print-timeout 60m --model gemini-4-argon-high`. Its failure modes
  and prompting rules say success is the envelope's `status: SUCCESS`, never the exit code: a soft-denied tool
  and a `--print-timeout` expiry both exit 0.
- `specy_road/templates/project/model-profiles/README.md`: a "Candidate harness profiles" table under Headless
  invocation. It sits outside the rendered harness block, and `refresh-profiles --check` reports no drift.
- `docs/orchestration-models.md`: one paragraph under "Harness facts" naming the two profiles.
- `tests/test_models_and_prompt.py`: the two fixed profile counts (17, and the derived 18 and 16) now come from
  the shipped templates. `test_every_shipped_profile_loads_and_is_schema_2` compares the loaded paths with every
  shipped `*.md` except the README. `test_refresh_profiles_adds_missing_and_keeps_edited` counts them for the
  first refresh and reuses that count. No docstring or comment was removed. The two count comments were reworded
  so they no longer state a fixed number. The file stays at 400 lines.

## Acceptance

- **A1:** both profiles exist. Each carries a front-matter `runtime_checks: 'not run: … not installed;
  maintainer decision 2026-11-02 …'` and a `## Runtime checks` section that lists each check as `not run` with
  its reason. This follows the planning sheet: written from vendor docs only, with no check run. "Model pinned":
  `--model=gemini-4-argon` (Copilot) and `--model gemini-4-argon-high` (agy). "Deny git push and gh pr":
  `shell(git push)` / `shell(git push:*)` and `shell(gh)` / `shell(gh:*)`. "One-shot": `-p` and no resume.
- **A2:** `-p`, `-s`, `--no-ask-user` and `--deny-tool` for `shell(git push)`, `shell(git commit)` and
  `shell(gh)` are present, plus the `:*` forms. The vendor shows `shell(npm test)` matching only the exact
  command, and `:*` matching the stem followed by a space. None of the forbidden flags appear. The check against
  a captured `copilot --help` of 1.0.105 or later is recorded as `not run`: no binary. 1.0.105 (2026-10-27) is
  the newest entry in the vendor changelog read on 2026-11-03.
- **A3:** `--output-format json` and `--print-timeout 60m` are passed. Success is read from `status` (SUCCESS).
  The version is recorded as `not run`. The reports' 1.4.3 vs 1.4.10 conflict is noted: the vendor changelog
  dates entries up to 1.4.9 (2026-10-28), and its version list also names 1.4.10. An open question records that
  the vendor changelog's 1.3.4 entry does not say what the acceptance dates to 1.3.4. The soft-deny that exits 0
  is in the 1.1.3 entry.

## Decisions to check

- **Pinned model: Gemini 4 Argon for both.** Copilot added Argon in 1.0.98 and lists it as a supported model.
  It gives the roster a `google`-family reviewer, a family the current reviewers do not cover. The Copilot id
  `gemini-4-argon` follows the changelog's id form (`claude-opus-5.5`, `gemini-3.6-flash`); no vendor page
  prints the Argon id, so this is a `not run` check. The agy slug `gemini-4-argon-high` comes verbatim from the
  vendor's `agy models` example.
- **`api_id` values are roster ids** (`copilot-gemini-4-argon`, `agy-gemini-4-argon-high`), not vendor ids.
  Profiles resolve by path order, and `github-copilot/` sorts before `google-gemini/`, so reusing
  `gemini-4-argon` would have taken over the existing Argon profile's roster id. I checked that `gemini-4-argon`
  still resolves to `google-gemini/`. Neither `family` (`Google Gemini`) is rendered by any executor template,
  so `refresh-profiles` leaves both `access.cli` lines alone.
- **`--allow-tool='shell,write'` on the reviewer.** A Copilot `-p` run denies anything that needs approval. The
  reviewer prompt requires re-running a verify command and filing through `specy-road review record`. This
  matches the Claude reviewer's `Read,Edit,Bash`, and the deny rules take precedence over it.
- **`--no-auto-update`** keeps the CLI at the version the runtime checks are run against. **`memory`** is in the
  deny list (Copilot Memory is state outside the repository; triage item 3).
- **Not done:** harness-facts records for Copilot and agy (F23/F24 in the 2026-11-02 triage note). They need
  `specy_road/worker_state.py` (`HARNESSES`) and `tests/test_harness_facts.py`, which require the fixture ids to
  equal `HARNESSES`. Both are outside the touch zones, and the planning sheet asks only for profiles.

## Touch zones (final)

`specy_road/templates/project/model-profiles/`, `docs/orchestration-models.md`, `tests/test_models_and_prompt.py`.
`roadmap/` was not edited.

## Vendor pages read (2026-11-03)

- https://docs.github.com/en/copilot/reference/cli-command-reference
- https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference
- https://docs.github.com/en/copilot/reference/ai-models/supported-models
- https://github.com/github/copilot-cli/blob/main/changelog.md (read raw)
- https://antigravity.google/docs/cli/headless
- https://antigravity.google/docs/cli/reference/
- https://antigravity.google/docs/changelog/
- https://antigravity.google/docs/rules/
- https://github.com/google-antigravity/antigravity-cli/issues/76

## Verification

- `python3 -m pytest -q -p no:cacheprovider tests/test_models_and_prompt.py tests/test_lean_rules.py tests/test_harness_facts.py tests/test_init_profiles_subset.py tests/test_upgrade.py tests/test_orchestrate_plan.py tests/test_doc_links.py tests/test_verify_wheel_contents.py tests/test_worker_adapters.py`: 147 passed (exit 0)
- `specy-road file-limits`: exit 0
- `specy-road refresh-profiles --check --repo-root <copy of model-profiles>`: "no drift from harness-facts.yaml", exit 0
- An ad hoc script (not committed): both profiles parse with no errors; `placeholder_problem` is `None` for both
  commands; `substitute_prompt` yields the expected argv; roster id `gemini-4-argon` still resolves to
  `google-gemini/`.

## Added

- `github-copilot/copilot-gemini-4-argon.md`: the Copilot CLI reviewer profile (A1, A2).
- `google-antigravity/agy-gemini-4-argon-high.md`: the agy generic profile (A1, A3).
- Front-matter key `runtime_checks` in both profiles: a machine-readable mark of which runtime checks passed (none run), per A1; the loader ignores unknown keys.
- README "Candidate harness profiles" table: lets the README's guide find the two profiles that are not in the roster table.
- docs/orchestration-models.md paragraph: says where the candidates are and that an agy exit 0 is not success.
- Helpers, guards, mocks: none.
- Tests: none new. Two existing assertions now derive the shipped profile count instead of fixing it, as the maintainer asked.
