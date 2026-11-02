# Implementation summary: M5.6 — Pilot the context-feedback question in the sandbox before shipping it

Branch `feature/rm-context-feedback-pilot`, base `10d20be9`.

## What changed

- `specy_road/bundled_scripts/role_prompt.py`: `specy-road prompt --context-feedback` (opt-in, executor only).
  `build_prompt(..., context_feedback=False)` appends `CONTEXT_FEEDBACK_LINES` after the executor preamble: a
  `## Context feedback (pilot)` block asking for three lines at the end of the implementation summary,
  `missing:` / `wrong:` / `unused:`, each quoting the brief or prompt line or naming the turn, or `none`. The default
  prompt, `worker delegate` and `worker reconcile` are unchanged (they pass no flag). Module docstring updated.
- `docs/agentic-sandbox-runbook.md`: §10 "Context feedback (pilot)" says to render the §2.8, §4.2 and §5 executor
  prompts with `--context-feedback`, where the three lines go, and the triage rule (**A1**, **A2**). The quickstart
  pointer was folded into the §9 bullet and the intro paragraph that repeated the first "Must know" bullet was
  dropped, so the file stays at the 400-line `file-limits` cap (it was 396; no exemption).
- `docs/design-notes/context-feedback-pilot.md` (new, indexed in `docs/design-notes/README.md` as live design): the
  flag, the triage rule, and the 2026-11-02 pilot record with the hit rate (**A3**). The default-shipping decision
  is recorded as open.

## The pilot

Per the maintainer's 2026-11-02 decision it ran locally, not in sandbox VMs. Three closed leaves (`M10.19`,
`M10.18`, `M10.17`), two runs each (six executor runs, the planning sheet's cap), each in a fresh scratch clone of
this repository at the leaf's registration commit on its `feature/rm-*` branch, brief rendered into `sr/work/`,
executor prompt rendered once per leaf with this branch's code (`--model claude-fable-5-1 --role executor
--context-feedback`; `sha256` in the note) and sent verbatim to a fresh Claude session with two operator overrides
(skip `specy-road ready`, which writes into another checkout; run `specy-road`/`pytest` through the project
interpreter from the clone root). All six completed their leaf with targeted tests and `file-limits` green and
answered the block. Result: 17 items offered, 17 cited a line or turn, 17 reproduced against the brief and base
commit; deduplicated they are four findings (line-cap headroom unnamed in briefs, 6/6 runs; touch zones narrower
than the brief's approach text, 3; model-profile notes and rollup section unused by executors, 6/6; two replay
artefacts). Raw lines per run are in the design note's table. Scratch clones live only in this session's scratchpad.

## Touch zones

Confirmed as listed: `docs/agentic-sandbox-runbook.md`, `docs/design-notes/`, `specy_road/bundled_scripts/role_prompt.py`.
Not added: `tests/`. A unit test for the flag would belong in `tests/test_models_and_prompt.py`, which is outside the
zones, so none was added; the flag is covered by the rendered pilot prompts (the block appears once in each) and by
the existing prompt tests still passing with the default off.

## Verification

- `pytest -q tests/test_models_and_prompt.py tests/test_do_next_prompt.py tests/test_lean_rules.py tests/test_worker_cli_fixes.py tests/test_context_regressions.py tests/test_brainstorm_v2.py` → 87 passed
- `specy-road file-limits` → OK
- `ruff check specy_road/bundled_scripts/role_prompt.py` → clean

## Added

- Helpers: `CONTEXT_FEEDBACK_LINES` constant in `role_prompt.py` (the block text, one place for the runbook and the
  design note to cite).
- Branches or guards: `if context_feedback:` in `build_prompt` (executor branch only, so reviewer, coordinator and
  rca prompts cannot carry it); `--context-feedback` store-true argument in `main`.
- Mocks: none.
- Tests: none (see Touch zones).
