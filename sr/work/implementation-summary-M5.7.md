# Implementation summary for M5.7

## Summary

I ran the reduced managed-section ablation the maintainer chose on 2026-11-02 (planning sheet `## Approach`): one `specy-road init project` app × Claude Code, Codex and Cursor agent × two runs × managed `AGENTS.md`/`CLAUDE.md` section on and off. That is 12 executor runs, all run once, none discarded, and no more than 12. A fixed reviewer (Grok 4.7 high, Cursor ask mode) gave each run one blind first-round review. The results and the decision are in `docs/design-notes/managed-section-ablation.md`.

Findings:
- **First-round approvals:** 4/6 with the section on, 5/6 with it off.
- **Both "on" failures trace to the section's own text.**
  - Codex stopped to ask for a base commit. The section's "if a prompt has no `base: <sha>`, ask" clause conflicts with the pickup prompt, which has none.
  - Cursor ran a `--local` pickup, an opt-out that only the section names, so its claim never reached the remote.
- **Cost:** Claude Code +26 % with the section on, Cursor −39 % input tokens, Codex flat.
- **Session presence:** 5/6 "on" runs ran `specy-road session start`; 0/6 "off" runs did.
- **Verdict: test further.** Two template edits are justified now, both outside this leaf's zones. Then replay context regressions CR1–CR3 on and off before trimming anything else.

## Acceptance

- **A1:** met. One `init project` app × Claude Code, Codex and Cursor agent × two runs, with and without the managed section, same task list: 12 executor runs, the matrix A1 asks for since the maintainer reduced the study on 2026-11-02. Two runs per cell limit the statistics, so the note reads every difference as a direction ("Limits").
- **A2:** met. Turns (Claude only; the others report none), tool calls, tokens, cost (Claude only; the others report none), wall time and the first-round review are recorded per run, with means per cell.
- **A3:** met. "Decision" states the verdict, test further, and what the numbers do and do not justify.

## Changes

- `docs/design-notes/managed-section-ablation.md`: new measurement note covering protocol, per-run table, cell means, rule-following checks, the two failure analyses, the decision and the limits.
- `docs/design-notes/README.md`: an index row for the note. Its status is "historical triage", like the lean-code census measurement note.
- **Touch zones:** confirmed `docs/design-notes/`. `docs/agentic-sandbox-runbook.md` is unchanged. The study used its harness prerequisites and its §9 failure rule, and the note cites both; no runbook step needed to change.

## Verification

- `specy-road file-limits` → `OK: file limits satisfied.`
- `python -m pytest -q tests/test_doc_links.py tests/test_doctor.py tests/test_agents_md_block.py tests/test_shared_checkout_guidance.py tests/test_context_regressions.py tests/test_review_round6_docs.py tests/test_post_release_readme_cleanup.py` → 71 passed.
- Full `python -m pytest -q` → 2984 passed, 2 skipped (16:24), run after the note was final and before it was committed.
- Review round 2 (gpt-5.6-sol-high blocked on wording only): the note's "Limits" and this summary's A1 line now match the current A1, the 12-run reduced matrix, which is met; the two-runs-per-cell limit stays. Re-run for the touched docs: `.conda/bin/pytest -q tests/test_doc_links.py` → 4 passed; `specy-road file-limits` → OK.
- **Study artifacts are local only, never committed:** the app copies, harness JSON logs, review packets and verdicts, and the collection and review scripts. They live in this session's scratchpad, outside the repo. The note gives enough of the protocol (app shape, prompt, exact harness commands, metric definitions, packet contents) to rebuild them.

## Follow-ups for the coordinator (outside this leaf's touch zones)

- `specy_road/templates/specyrd/agents-md-block.md` and the pickup prompt writer: either the pickup prompt carries `base: <sha>`, or the base-commit clause exempts pickup and `specy-road prompt` prompts.
- `specy_road/templates/specyrd/agents-md-block.md`: drop the `--local` mention from "Task pickup".
- An on/off replay of CR1–CR3 from `docs/context-regressions.yaml` in the same reduced shape.

## Added

- Helpers: none
- Branches or guards: none
- Mocks: none
- Tests: none. The leaf is a measurement note; no code changed.
- Files: `docs/design-notes/managed-section-ablation.md` (the A2/A3 record) and one index row in `docs/design-notes/README.md` (so the note can be found).
