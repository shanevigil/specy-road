# Deep-research prompt (v1): efficient and effective unit testing when agents write the code and the tests

Paste into a deep-research tool (ChatGPT Deep Research, Claude Research). It needs no repository access. Paste the
report back; it is saved as `docs/research/agentic-unit-testing-<date>-<tool>.md`.

---

## Context: the toolkit, its suite and its fixed constraints

I maintain an open-source Python toolkit for spec-driven, multi-agent software work. It drives existing coding-agent
CLIs (Claude Code, Cursor's agent CLI, OpenAI Codex CLI) as unattended executors and reviewers in git worktrees.
Almost all of its code and almost all of its tests are now written by those agents; every change is reviewed by two
reviewers from distinct model families before it lands, and every fix a review asks for tends to add a test.

The maintainer has ruled (2026-11-05) that **suite speed is the wrong goal**: tests should be judged by coverage and
by how well they catch regressions (or other standard measures of what unit tests are for). Speed and cost matter
only as a secondary concern. The maintainer will choose the suite's effectiveness measures from this report.

Any proposal must fit these constraints. Mark anything that breaks one as INCOMPATIBLE rather than recommending it:
1. Python; the package's core is standard library first, and the toolkit adds **no new runtime dependency** for
   testing.
2. pytest is the runner (pytest-xdist in use); coverage.py is in use with a CI floor (`fail_under`); Hypothesis is
   already approved as a pinned, test-only dev dependency. Any other test-only tool needs a buy-vs-build case.
3. Local-first and offline-capable: anything that needs a hosted service must be optional.
4. Cautious about dependencies: pinned, hash-checked, license-reviewed; copyleft avoided in anything bundled.
5. The toolkit never calls an LLM itself; any LLM-based step (test generation, test review) runs in the user's own
   coding agent through a prompt the toolkit generates.
6. Measures must be reproducible on one developer machine and in GitHub Actions, and a CI gate must not be flaky.

## What we already know (don't repeat; build on it)

Today's suite (2026-11-05): 5,408 collected items, 3,778 test functions in 393 files, about 74k test lines against
about 65k package lines; full run 72 s with `pytest -n auto` on 32 CPUs. A per-test coverage analysis of an earlier
snapshot (4,400 items, branch arcs per test, subprocesses captured through a sitecustomize hook) found:
- Line plus branch coverage 89% (91.2% lines, 83.7% branches), yet thin spots in real logic (milestone rollup 29-71%,
  outline restructuring 66%, one migration module at 0%) while leaf-level worker and review flows are tested many
  times over.
- 76% of items cover no arc that no other test covers; a greedy set of 31% of items reproduces 100% of arc coverage;
  1,874 items sit at Jaccard >= 0.95 to their nearest neighbour. A hand-read sample sorted them into (a) duplicate
  assertions of the same behaviour (~300-400 items), (b) single-input regressions a parametrized table would subsume
  (~500-700 functions), (c) implementation-detail tests (137 functions on private names, 100 monkeypatches of private
  names), and (d) genuinely valuable tests (the rest, including concurrency, crash and git-semantics scenarios).
- Organisational causes: 32 files named after a review round or roadmap leaf rather than a module; 98 files importing
  helpers from other test files; 105 helper names defined in several files; 1,496 assertions matching message text of
  12+ characters; 16 files sleeping on the wall clock; 464 tests spawning the CLI as a subprocess (32% of CPU).
- Coverage proves execution, not checking: "zero unique coverage" is a lead, not a verdict.
- Planned work already in flight: a parity harness at the user-visible surface, committed per-subsystem dedupe
  worklists, public seams replacing private-name patches, five Hypothesis properties, a CLI smoke lane of at most 50
  subprocess items with everything else in process, and a review-finding test rule (a new test must fail before the
  fix, check something no existing test checks, live at the cheapest level, be named for the behaviour, and assert
  structured results rather than message text).

## Open questions to research in depth

1. **What to measure.** For each candidate measure, say what it detects, what it misses, its cost on a suite of this
   size, its flakiness, and whether it is fit as a CI gate, a periodic report, or a review aid: line vs branch vs
   per-test (context) coverage; mutation score (whole package vs named core modules vs changed lines only);
   regression-catch rate (historical bug reintroduction, fault seeding, red-green records of fixes); flake rate;
   test-to-code coupling (private-name use, patch targets, assertion on message text); duplicate and low-value tests
   (arc-set similarity, assertion overlap). Which two or three measures give most signal for an agent-written suite?
2. **Mutation testing in practice for Python.** mutmut, Cosmic Ray, mutatest, MutPy and any newer tool: maturity,
   speed with pytest-xdist and coverage-guided test selection, incremental or diff-only runs, equivalent-mutant
   handling, and realistic thresholds teams use. Evidence from published case studies and from industry (e.g. Google's
   diff-based mutation testing) on what works at scale.
3. **Keeping agent-written tests effective.** Evidence on how LLM-written tests differ from human-written ones
   (assertion strength, oracle problems, testing the implementation rather than the spec, near-duplicate tests from
   per-fix additions). Concrete prompt-side and process-side rules that reduce these: spec- or acceptance-derived test
   lists, property-based tests from invariants, "one behaviour, one table" rules, forbidding private-name imports,
   mutation-guided test writing, and test review rules reviewers can apply mechanically.
4. **Test review rules.** A short checklist a reviewer (human or model) can apply to an added or changed test in a
   diff, with the evidence behind each rule, and which rules can be checked by a script instead of a reviewer.
5. **Suite structure.** Unit vs integration (git-backed flows) vs CLI smoke vs repository-consistency lanes: how to
   decide the level for a new test, how much of each a CLI toolkit like this should have, and how to keep shared
   fixtures from becoming a private library that couples tests.
6. **Property-based testing.** Where Hypothesis pays off for this kind of code (graph edits, parsers, state machines,
   config migration), stateful testing, and how to keep property tests deterministic and fast enough in CI.
7. **Cost and speed (secondary).** Only where it serves the measures above: test impact analysis, coverage-guided
   selection, sharding, and which speed work also improves effectiveness (for example in-process execution that
   coverage and mutation tools can see) versus speed work that weakens it.

## Weighted buy-vs-build (required for every candidate tool)

Score each candidate 0-3 on each criterion, show the weighted total, and give a verdict: **adopt as test-only
dependency**, **integrate optionally** (detect and use if installed), **recommend only**, **build in-house** (small
script over pytest and coverage.py data), or **incompatible**.

| Criterion | Weight |
|---|---|
| Fit with the six constraints above | 3 |
| Signal it adds for regression catching | 3 |
| Supply-chain risk (maintainers, release signing, incident history) | 2 |
| License (permissive vs copyleft) | 2 |
| Run cost and flakiness on a 5,000-item suite | 2 |
| Maturity and maintenance (releases, issue response, adoption) | 1 |
| Integration effort with pytest, xdist and coverage.py | 1 |

Candidates to include at minimum: mutmut, Cosmic Ray, mutatest, pytest-testmon, pytest-randomly, pytest-rerunfailures
(as a flake detector, not a hider), coverage.py dynamic contexts, diff-cover, Hypothesis (already approved: how to use
it well), and any newer agent-oriented test-quality tools from 2025-2026.

## Output

1. A short executive summary with a recommended set of effectiveness measures for specy-road's own suite: for each,
   the definition, scope (whole package, named core modules, changed lines), a starting threshold or a "report only"
   status, where it runs (every PR, nightly, per release) and its expected cost.
2. Concrete, adoptable rules for agent-written tests and a reviewer checklist, marking which rules a script can check.
3. Answers to each open question with evidence, marking weak, anecdotal or vendor-only sources.
4. The scored buy-vs-build table.
5. Recommendations for adopters of the toolkit (projects whose code and tests its agents write): what a default
   should be, what they should opt into, and what the toolkit could check or report for them without new runtime
   dependencies.
6. Where the evidence disagrees with the "what we already know" section or the planned work, say so.
Cite sources with URLs and dates.
