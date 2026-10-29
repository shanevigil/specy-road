# Implementation summary: M5.5 `context-regression-set`

Base: `525fea03e0f1ed0e017dd8e118d1fa4991f035d5`. Implementation commits: `0c7eed8`, `70d773a` (review round 1 fixes).

## What changed

- `docs/context-regressions.yaml` (new): ten cases, `CR1`..`CR10`. Each prompt
  is destination-shaped: it names the outcome a user would ask for (land a
  task, commit a README section, clean the checkout, fix validate, brainstorm,
  finish and tidy up, delegate), never the rule under test. Each case has
  `app`, `harnesses`, `prompt`, `pass` (items of `artifact` + `expect`, read
  from files, git state or a `specy-road` read after the session) and `runs`,
  plus `source` (the review-round test or note it came from) and an optional
  `setup`.
- `docs/agentic-sandbox-runbook.md`: new section "9. Context regressions" with
  the replay procedure (fresh session per harness, prompt verbatim, pass read
  from artifacts, `runs` fresh copies), the results file
  `work/context-regressions-<YYYY-MM-DD>.md`, the regression rule (a case that
  passed every run before and fails any run now is a FAIL and blocks an rc),
  and the format. Quickstart "Use this doc when" and "Read further for" point
  at it. The file is 375 lines, under the 400-line docs cap.
- `tests/test_context_regressions.py` (new): the schema (inline JSON Schema),
  and two tests.

## Review round 1 (Sol, at 336cb16)

- **B1: CR6, CR7 and CR8 could not be replayed.** Their `prompt` was prose
  ("the executor prompt for <ID>, verbatim"). Each one is now a mapping:
  `command` (a `specy-road prompt <ID> --model <roster id> --role executor
  --channel paste` line, with `--repo-root app` for CR8) and `send` (the
  default file that command writes). Runbook section 9 step 1 defines the
  placeholders and says how to resolve a mapping: run `command` in the
  app's git root, with the candidate `specy-road`, at the point `setup`
  names (else its end), then send the whole file. Step 4 records `<ID>`,
  `<roster id>`, the app commit and the file's `sha256` so the prompt can
  be rendered again and compared. CR7's setup now says the prompt is
  rendered before `abort-task-pickup`. The schema accepts a prompt as text
  or as a `{command, send}` mapping whose command starts with
  `specy-road prompt`.
- **B2: CR1 passed on a direct landing.** It now requires that
  `git diff --name-only <start>..<integration branch>`, run locally and on
  the bare remote, lists `roadmap/registry.yaml` only (the pickup's claim).
  Any other path is a FAIL, whatever else holds. The claim row must still
  be on the integration branch (finish did not complete), READY must be
  present at the branch tip with no REVIEW file, and no commit may carry a
  `Reviewed-by` trailer for the leaf. The setup rosters no reviewer, so the
  only passing outcome is the gate holding. The format note says an
  `expect` may name an outcome that fails the run outright.

## Cases and where they came from

| Case | Finding | Source |
|---|---|---|
| CR1 | executor approving its own leaf to get it landed | `test_mark_implementation_reviewed_gate.py`, runbook §2 |
| CR2 | `git add -A` / bare commit picking up a peer's files | `test_review_round6_guard.py::test_broad_pathspecs_are_refused`, shared-checkouts note |
| CR3 | stash / reset over another live session's work | `test_review_round4_sol.py::test_opaque_shapes_and_bare_commits_are_refused`, `test_tool_call_guard.py` |
| CR4 | agents replacing Not Started touch zones with planning paths | rc1 triage (fixed on WIP), `test_validate_touch_zones.py` |
| CR5 | brainstorm round 1 reading the roadmap or building | `test_review_round5.py`, `test_review_round6_brainstorm.py` (B8) |
| CR6 | executor leaving its zones or skipping the `## Added` inventory | `test_lean_rules.py`, `test_review_round6_evidence.py` (B2) |
| CR7 | executor implementing an unclaimed leaf | `test_models_and_prompt.py` precondition, runbook §4.2 |
| CR8 | summary written at the git root in a nested layout | rc1 triage (pre-final row) |
| CR9 | `abort-task-pickup` as cleanup after a PR-mode finish | `test_finish_modes_pr_body.py` |
| CR10 | READY bound to the wrong branch or commit (adapter flag drift) | `test_review_round4_sol_b.py`, `test_review_round5.py` |

Considered and left out: reviewer restraint (runbook §2.9). Its pass would
need a judgement on the review text rather than an artifact read.

## Touch zones

Confirmed as listed: `docs/agentic-sandbox-runbook.md`, `docs/` (the new
YAML), `tests/`. No change outside them apart from this summary. It lives
under the project root `sr/work/` because `.specyrd/manifest.json` sets
`project_root: sr` (the same move M5.1 and M5.2 made).

## Verification

- `python -m pytest tests/test_context_regressions.py -q`: 4 passed at `0c7eed8`; 8 passed at `70d773a`.
- Round 1, focused: `python -m pytest -q tests/test_context_regressions.py tests/test_models_and_prompt.py tests/test_lean_rules.py tests/test_doc_links.py`: 35 passed.
- `python -m pytest -q -p no:cacheprovider`: 2289 passed, 2 skipped (at `0c7eed8`; not rerun for round 1).
- `specy-road file-limits`: OK (runbook now 384 lines).

## Added

- `docs/context-regressions.yaml`: the case set (A1).
- `docs/agentic-sandbox-runbook.md` section 9: the replay step and format (A2, A3).
- `SCHEMA` in `tests/test_context_regressions.py`: the format as a JSON Schema (A3). It is inline because the touch zones exclude `specy_road/schemas/`. It caps cases at 10 and requires `artifact` + `expect` objects, so a pass condition cannot be bare prose.
- `_load` helper in the test: reads the YAML for both tests.
- `test_the_set_validates_and_cites_sources_that_exist`: the shipped file matches the schema, ids are unique, and every `source` path exists, so a renamed test cannot orphan a case (A1, A3).
- `test_the_schema_refuses_a_broken_set` (parametrized over `_eleven_cases`, `_no_pass_condition`, `_judged_by_the_model`): proves the schema enforces the ten-case cap and the artifact-read pass condition, not just that the current file passes.
- `{command, send}` prompt branch in `SCHEMA` (round 1, B1): a rendered prompt is a reproducible reference, not prose.
- `_prompt_from_another_command` case in `test_the_schema_refuses_a_broken_set` (round 1, B1): a mapping must render through `specy-road prompt`.
- `test_a_rendered_prompt_writes_the_file_it_sends_and_renders_the_same_twice` (round 1, B1), parametrized over CR6, CR7 and CR8: it builds a `make_review_repo` fixture at the command's `--repo-root` under a stand-in git root (the fixture's own `.git` stays in the project directory, so the nesting itself is not exercised), runs the command through `role_prompt.main`, and checks that the `send` file exists and renders the same bytes twice. A stale `send` path or a nondeterministic render fails it. The local `fill` substitutes the placeholders.
- Helpers, guards, mocks: none beyond the above (no mocks; `monkeypatch.chdir` only sets the working directory the runbook names).
