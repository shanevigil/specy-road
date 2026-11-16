---
purpose: Find how to make unit testing efficient and effective when most code and tests are written by AI agents (what to measure, how to keep agent-written tests from pinning implementation details or duplicating each other, review rules, suite structure, tools that fit a stdlib-first Python core), so the maintainer can choose M16.7.8's effectiveness measures; rerun each minor release (90 days approximates that)
prompt: research/prompts/agentic-unit-testing.md
cadence_days: 90
last_run: 2026-11-16
fed: [M16.7.8]
---

Opened 2026-11-05 by maintainer decision 5d: suite speed is the wrong goal for M16's test
leaves; tests should target coverage and effectiveness at catching regressions. M16.7.8 carries a
`human:` acceptance line that the maintainer chooses the suite's effectiveness measures from this
item's report, so the first run is a prerequisite of that leaf.

Evidence that prompted it: the slimming report's tests analysis
(`docs/research/slimming-2026-11-05/02-tests.md`: 4,400 items at `b216d799`, 76% of items with no
uniquely covered arc, about 30-35% of test functions removable with no coverage loss, 137 tests on
private names) and the suite on 2026-11-05 at `469b9322`: 5,408 collected items, 3,778 test
functions in 393 files (74k test lines), 72 s wall time with `pytest -n auto` on 32 CPUs.

Runs: (1) 2026-11-06, Codex: `docs/research/agentic-unit-testing-2026-11-06-codex.md` (recommends branch coverage by subsystem, targeted mutation on named core modules, historical regression detection). (2) 2026-11-16, preliminary automated multi-agent web research pass: `docs/research/agentic-unit-testing-2026-11-16-claude-code.md` (recommends its Option B: coverage and hygiene checks plus a core-module mutation ratchet). The M16.7.8 A1 decision should draw on both; the maintainer may also run the full prompt in the deep-research tool.
