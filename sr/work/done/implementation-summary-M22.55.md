# Implementation summary: M22.55 (`process-content-untracked`)

Base `afbbae5d`. Change commit `abb45abe` ("M22.55: process content outside sr/ leaves the tracked tree"); this summary is committed on top of it.

## A1: untracked and ignored

- `git rm -r --cached` on `docs/design-notes/` (28 notes and the README), `scripts/census/` (3 scripts), `scripts/review_effort_study.py` and `.cursor/rules/` (8 rules): 40 files leave the index. `git ls-files` lists none of them.
- `.gitignore`: the `.cursor/*` / `!.cursor/rules/` / `!.cursor/rules/**` lines are now a single `.cursor/` line. A new block ignores `/docs/design-notes/`, `/scripts/census/` and `/scripts/review_effort_study.py`.
- `.cursorindexingignore`: the four paths are added below the specy-road managed block. The block is unchanged.
- The files are still on disk in this worktree. All 40 paths from `git ls-tree -r afbbae5d` exist, and `git hash-object` matches each base blob. `git check-ignore` reports all four paths as ignored. `git status --porcelain --untracked-files=all` shows only `sr/work/brief-M22.55.md`.
- How the commit was made: `git commit --only <paths>` takes each path's working-tree state, so it cannot record an index removal for a file that is still on disk. For the commit only, I moved the four paths with `mv` to a temp directory under `~/.cache`, committed with `--only` and the explicit path list, then moved them straight back. The hash check above was run after they came back. Nothing was deleted and nothing was pushed.
- `sr/` and `scripts/lean_metrics.py` stay tracked. The only change to `lean_metrics.py` is that its `:(exclude,glob)docs/design-notes/**` line is gone.
- **Coordinator:** copy the four paths to the private archive before this commit is merged into any other worktree. A merge deletes them there.

## A2: citations

A citation that pointed at a removed path now describes its source in words, or is dropped where the sentence existed only to cite it.

- Shipped model-profiles:
  - `README.md`: the "Where this comes from" table and its prose, and the "Keeping this current" bullet, describe the proposal and the research reports in words. They no longer link to GitHub `docs/design-notes/`.
  - `harness-facts.yaml`: each `source` names the "harness compatibility triage (2026-10-28)", "M8.7 runtime verification", "2026-11-02 harness-facts triage K13" or "2026-11-04 context-regressions triage". Its header comment no longer names the note.
  - The README's harness block was re-rendered with `specy-road refresh-profiles --render --repo-root specy_road/templates/project`. `--check` now reports no drift.
  - The four Claude profiles' `effort_by_role` comments say "by M10.6's reviewer-effort study".
  - Source rows S5 and S6 in `copilot-gemini-4-argon.md` and `agy-gemini-4-argon-high.md` read "maintainers' triage notes (not published)".
- Docs: `orchestration.md`, `orchestration-review.md`, `orchestration-workers.md`, `dev-workflow.md`, `git-workflow.md`, `pm-workflow.md`, `brainstorming.md`, `agentic-sandbox-runbook.md` and `contributor-guide.md` each lose their design-notes links.
- `docs/context-regressions.yaml`:
  - CR2 and CR4 drop their design-note source and keep their test source.
  - CR8 had only a design-note source. It now cites `tests/test_worker_cli_fixes.py::test_nested_prompt_and_brief_give_paths_from_the_git_root`, which checks that the nested-layout summary path is given from the git root. `test_the_set_validates_and_cites_sources_that_exist` would otherwise fail on a clean export.
- Package files outside templates (every diff line is citation-only; see `git diff -U0 afbbae5d HEAD -- specy_road ':!specy_road/templates'`):
  - module docstrings and comments in `agents_md_block`, `brainstorm_lenses`, `generated_files`, `harness_instruction_files`, `review_defer`, `review_deferral`, `review_next_step`, `review_rca`, `review_trend`, `role_prompt`, `session_presence`, `specyrd_skills`, `tool_call_guard`, `worker_adapter_base`, `worker_adapters` and `worker_state`;
  - the `ref:` fields in `agent_rule_provenance.md`;
  - the description in `rca-record.schema.json`;
  - the `models stale` hint in `models_cli.py`, now "(orchestration proposal §7)", the same wording `docs/orchestration-models.md` uses.
- Both `constraints/file-limits.yaml` and `sr/constraints/file-limits.yaml` drop the `orchestration_proposal_verbatim` override and its comment.
- Left alone, as the acceptance puts them out of scope:
  - mentions and temporary-repository fixtures of a consumer `.cursor/rules` (`templates/adoption/README.md`, `suggested_prompts/bootstrap-agents-md.md`, `docs/install-and-usage.md`, `docs/optional-ai-tooling-patterns.md`, `agent_guide_block.py`, `harness_instruction_files.py`'s rules walker, and `tests/test_context_meter_harnesses.py`, `tests/test_worker_sandbox.py` and `tests/test_contract_citations.py`);
  - the ignore entries;
  - `CHANGELOG.md` and `tests/parity/`;
  - `docs/release-runbook.md` and `docs/toolkit-development.md` (M22.57).
- `tests/test_doc_links.py` is unchanged and passes.

## A3: tests

Removed tests and asserts, each with the path it read:

- `tests/test_review_effort_study.py`: the whole file, because it imported and ran `scripts/review_effort_study.py`. Deleted with `git rm`.
- `tests/test_review_rca.py::test_design_note_attributes_each_report`: the whole test, because every assert read `docs/design-notes/review-loop-rca.md`.
- `tests/test_roster_generate.py::test_docs_and_starter_roster_examples_name_shipped_profile_ids`: `docs/design-notes/model-aware-orchestration-proposal.md` is no longer in the scanned file list. The docs and starter-roster asserts stay.
- `tests/test_review_record_write.py`: the `M87_NOTE` constant and its two asserts (`Review-only runs omit --force` and `sandbox_mode=read-only` in `docs/design-notes/M8.7-runtime-verification-harness-facts.md`) are gone. The Cursor and Codex argv, env and stdin asserts stay.
- `tests/test_release_harness.py::test_release_runbook_exists_and_referenced`: the read of `.cursor/rules/030-git-workflow-management.mdc` and its three asserts are gone. The runbook and `AGENTS.md` asserts stay.
- Docstrings that cited a note or rule lost only the citation: `test_review_evidence`, `test_project_layouts_outside`, `test_context_meter_harnesses`, `test_agents_md_block`, `test_shared_checkout_guidance`, `test_skill_mirrors` and `test_version_resolution`. The `_note` in `tests/fixtures/worker_turn_check/streams.json` lost its citation too.
- Tests that write `.cursor/rules` into a temporary repository are unchanged.

The commit message lists the same removals.

## Gates

- **Clean export:** I ran `git clone --no-local` of the branch into a temp directory. The clone has none of the four paths and none of the retained untracked files. In it, the full suite passed: `pytest -n 4`, 6973 passed and 15 skipped.
- **Wheel:** built in the clean export with `pip wheel . --no-deps --no-build-isolation`. `scripts/verify_wheel_contents.py` passes, and `grep -r design-notes` finds nothing in the unpacked wheel or in `specy_road/templates/`.
- `specy-road file-limits` passes.
- `specy-road validate`, `export --check` and `digest --check` pass with `--repo-root tests/fixtures/specy_road_dogfood`.
- `refresh-profiles --check --repo-root specy_road/templates/project` reports no drift.

## Touch zones

The zones are accurate as listed. Every changed path is inside them, and every zone is used. No new module was needed, and this change brings no file near a file-limit cap.

## Added

### Helpers
none

### Branches or guards
none

### Mocks
none

### Tests
none
