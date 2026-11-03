# Implementation summary: M11.60 (`harness-facts-nov-refresh`)

Branch `feature/rm-harness-facts-nov-refresh`, base `082cf4ae`, implementation commit `46ae9e52`.

## Source of the triage

The brief names "the 2026-11-02 triage" but does not include it. I found it as
`harness-triage.json` in the coordinator session's scratchpad. It has rows F1-F24. F1-F22
change the fixture; F23 (a Copilot record) and F24 (an `agy` record) are new harnesses for
M8.6 and are left out. Before writing each row I opened its vendor URL on 2026-11-02 and
checked the quote. The triage is now recorded in
`docs/design-notes/harness-facts-2026-11-02-triage.md`, which also has the runtime checks
and what was left out and why.

## Acceptance

- **A1:** `harness-facts.yaml` carries F1-F22. Each row is labelled `documented` with a
  vendor URL (code.claude.com, learn.chatgpt.com, cursor.com, or the vendor's own GitHub
  issues and PRs), or `runtime` with its capture or run. Each source ends with
  `2026-11-02 triage Fn`. No row rests on the OpenAI report. I dropped the claims whose only
  sources were secondary (the design note's "Left out" section lists them). These labels
  changed:
  - claude-code `hooks`: runtime to documented.
  - claude-code `--cloud` git action: runtime to documented.
  - cursor `executor_template`: documented to runtime (K13).

  `refresh-profiles --render --repo-root specy_road/templates/project` rewrote only the
  README block. No profile `access.cli` changed. `--check` then reports no drift (exit 0).
- **A2:** `WORKFLOW_WORDS` adds goal, loop, queue, persist, gist, fleet, teleport, remote and
  spawn. Every accepted identifier that now matches has a relationship:
  - claude-code: 4 identifiers.
  - codex: 10 identifiers, `plugin_discovery_prefetch` (new in 0.166.0) among them.
  - cursor: `persist`.

  The existing empty-baseline test passes. The new test
  `test_a_capture_that_adds_persist_fails_until_it_is_classified` runs a baseline without
  Cursor's `persist` row through `refresh-profiles --capture cursor --accept`. Without a
  relationship it exits 1 and accepts nothing; once `persist: avoid` is set it is accepted.
  Red-green: with the new words removed, both new tests fail.
- **A3:**
  - **How 0.166.0 was installed.** The shared `/opt/homebrew/bin/codex` is still 0.165.0, and
    the plan leaves upgrading it to the maintainer. Other sessions use that binary, so I left
    it alone. Instead I installed codex-cli 0.166.0 into my scratchpad
    (`npm install --prefix <scratch> @openai/codex@0.166.0`).
  - **How it was captured.** I ran `refresh-profiles --capture codex --accept` with that
    binary first on PATH and a fresh `CODEX_HOME`, so the new binary could not migrate the
    shared `~/.codex`. Control: 0.165.0's `features list` with a fresh home is byte-identical
    to the accepted 0.165.0 capture, so the fresh home does not change the inventory.
  - **What changed.** `--help` and `exec --help` are unchanged; `features list` adds eight
    features.
  - **Docs.** `docs/orchestration-workers.md` now cites the captured versions in three places
    instead of `codex-cli 0.165.0` and the 2026-10-27 date: Claude Code 2.1.312, codex-cli
    0.166.0, agent 2026.10.22-27dcf5f, captured 2026-11-02.

Runtime checks I ran (details in the design note):
- **K7:** Codex hooks are on by default.
- **K8, partial:** the `memories` feature is off on a fresh profile. This disagrees with the
  changelog, and the row records both.
- **K13:** Cursor `--force` alone passes a fresh worktree's trust prompt, and a bare `-p`
  exits 1. So F22's proposed `--trust` was not added, and the cursor-composer profiles
  (outside the touch zones) stay as they are.
- **K12:** answered as a side effect of K13; Cursor's JSON result carries `usage`.

## Touch zones

All changes are inside the listed zones:
- `specy_road/harness_facts.py`
- `harness-facts.yaml`
- `harness-captures/codex/`
- `model-profiles/README.md`
- `docs/orchestration-workers.md`
- `docs/design-notes/`: the new note and an index row in its README
- `tests/`: the new module `tests/test_harness_facts_workflow_words.py`, and
  `tests/test_harness_facts.py`

**Outside the zones, left as is:** `docs/orchestration-models.md:209-212` still lists the
old 17 workflow words as if they were the complete set, so it now understates what fails
the diff. It needs the nine new words. Add that path to the zones, or to a follow-up, to fix it.

## Verification

- `python -m pytest -n 8 -q -p no:cacheprovider`: 3259 passed, 2 skipped (exit 0)
- `python -m pytest tests/test_harness_facts.py tests/test_harness_facts_workflow_words.py -q`: exit 0
- `specy-road file-limits`: exit 0. `tests/test_harness_facts.py` reached 401 lines, which
  is why the new tests went into their own module.
- `specy-road refresh-profiles --check --repo-root specy_road/templates/project`: exit 0

## Added

- `WORKFLOW_WORDS` entries `goal`, `loop`, `queue`, `persist`, `gist`, `fleet`, `teleport`, `remote`, `spawn`: A2, to watch the new autonomy features.
- Fixture relationships for the 15 captured identifiers that now match, plus the F9, F15 and F20 identifiers: A1 and A2.
- Fixture git_actions rows:
  - Claude background wait, native subagents, auto memory (F2, F7)
  - Codex `multi_agent`, `goals`, `queue` (F13)
  - Cursor `agent persist`, `/goal` (F20)
- `docs/design-notes/harness-facts-2026-11-02-triage.md`: A1 requires the triage to be recorded; it also holds the K7, K8 and K13 runtime record.
- Design-notes index row for that note: keeps `docs/design-notes/README.md` a complete index.
- `tests/test_harness_facts_workflow_words.py::test_the_scope_escape_words_are_watched`: pins the nine words (A2).
- `tests/test_harness_facts_workflow_words.py::test_a_capture_that_adds_persist_fails_until_it_is_classified`: the A2 test, through the public `refresh-profiles` CLI.
- `run_main` in the new test module: imported from `tests/test_harness_facts.py`, as other tests here import helpers from sibling test modules (for example `from tests.test_grind_session import ...`), rather than duplicated. This was changed after the Sol review.
- Mocks: `monkeypatch` of `hf.bundled_captures_dir` (a temporary accepted capture) and `hf.load_facts` (a fixture copy without `persist`), the pattern the existing capture tests use.
- Changed test data: in `test_capture_cli_fails_on_unassigned_and_accept_stores_a_passing_one`, the "new" capture version went from 0.166.0 to 0.167.0. It must differ from the fixture's version so that the "update codex's version" note still prints, and the fixture is now 0.166.0. No assertion was removed or loosened.
- Guards and branches in code: none.
