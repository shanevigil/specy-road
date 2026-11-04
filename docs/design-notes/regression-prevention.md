# Regression prevention: keep the integration branch green when many agents land

**Status:** live design (roadmap milestone `M9`). The maintainer approved
`M9.2`–`M9.9` on 2026-10-29. `M9.1` is held until the project settles what
"green" means (see *Open decision*), and `M9.10` stays proposed.

**Sources:** one research run, kept untracked under the maintainer's
`work/research-reports/`: `claude-regression-prevention.md` (the "report"). It
answers `work/deep-research-prompt-regression-prevention.md`. The two OpenAI
files on the same topic were not used (one answers a different question, the
other cites nothing). With a single source there is no second report to catch
its mistakes, so every claim a leaf rests on was checked against the primary
source it cites (see *What the evidence supports*), and every mechanism was
checked against this repository's code before it was adopted.

## The problem

About 30 leaves landed on one integration branch in one night, and seven kinds
of regression got through. Each leaf passed its own review, yet the branch was
red for stretches, later leaves inherited the breakage, and three full-suite
failures only showed up at release time.

| # | Regression | What exists today (file) |
| --- | --- | --- |
| 1 | Gate breakage (line cap, complexity cap, ruff) inherited by later leaves | READY failures block the gate (`M3.17`, `review_files.verifier_gate_problems`), but the executor chooses and reports the commands; `baseline_cmd` refuses a pickup on a red base (`M3.12`) but never stops a red landing |
| 2 | Nested-root path rebasing dropped paths outside the project; `finish` refused an approved leaf | Fixed in `79eaff3` with a unit test. The two-layout fixture in `tests/test_project_layouts.py` has no change outside the project |
| 3 | Green alone, red together: three full-suite failures found at release | The trial merge (`review_gate_ready.trial_merge`, `M3.13`) checks for conflicts in memory and runs nothing |
| 4 | The reviewed commit was not the landed commit after a conflict resolution | Closed for conflicts by the trial merge: conflicts are resolved on the leaf branch and the new commit voids the approvals. A clean merge at finish still lands a combined tree nobody ran |
| 5 | `finish` crashed when run twice | Fixed in `85c58dc` and `a9e1bbf`, with a re-run test in the embedded layout only |
| 6 | A manual CLI run left a cache in a test fixture and two tests failed later | `tests/conftest.py` stops the *tests* writing the history cache; nothing catches a manual run. At the time of writing, `tests/fixtures/specy_road_dogfood/.specyrd/` is again present (ignored) in the shared checkout |
| 7 | Two-family LLM review approved changes that broke the gates or other behaviour | Nothing besides review stands between an approval and the integration branch |

## What the evidence supports, and how strongly

The report's central claim is that the branch is protected by the gate, not by
review: land only what passes the full deterministic gate on the exact merged
commit that becomes the new tip (the "not rocket science" rule). The claims
below are the ones a leaf rests on, labelled by kind.

**Measured (primary source opened and the numbers confirmed):**

- *Agents game tests.* ImpossibleBench (arXiv 2510.20270): GPT-5 cheats on 76%
  of Oneoff-SWEbench and 54% of Conflicting-SWEbench tasks; Claude models cheat
  mainly (>79%) by modifying tests. Feedback loops raised average cheating from
  33% to 38%. An option to abort and flag the task cut GPT-5 from 54% to 9% and
  o3 from 49% to 12%, with a much smaller effect on Claude Opus 4.1. LLM monitors
  detected 42–65%. The benchmark is adversarial by construction: these are upper
  bounds on propensity, not base rates in this repository.
- *An escalation channel works across families.* Gomez (arXiv 2608.29460, single
  author): 8 models from 5 families; an escalation tool plus an anti-hacking
  policy cut reward hacking from 23.6% to 5.3%.
- *Telling the executor which tests are at risk helps; "do TDD" hurts.* TDAD
  (arXiv 2603.17973): a code-to-test impact map cut the test-level regression rate
  from 6.08% to 1.82%; TDD instructions without it raised it to 9.94%. Small
  study: Qwen models, 100 + 25 instances.
- *Passing validation often proves nothing.* BSG-VA (arXiv 2607.28871): 46.0% of
  positive validation events carried no bug-discriminating information.
- *Order dependence dominates Python test flakiness.* Gruber et al. (ICST 2021,
  older; arXiv 2101.09077): 59% of 7,571 flaky tests across 22,352 PyPI projects.
- *Test the merge result before it lands.* GitHub's merge queue documentation
  states the mechanism: each entry must pass the required checks "when applied to
  the latest version of the target branch". The report's Uber SubmitQueue figure
  (mainline green 52% of the time before serialising) was not re-verified; it is
  cited here for the mechanism only.

**Measured, but weak or conflicting (reported, not built on):** LLM review
recall on functional and cross-file issues is low (SWR-Bench, AACR-Bench), and
retrieved context lowered recall in two benchmarks. Whether a second model
family catches different regressions is contested (arXiv 2606.15689 against
2610.01471). Regression-test-selection safety figures (NameRTS 99.6% safe) come
from a new tool whose availability is unverified. The real-world rate of test
weakening looks lower than the benchmarks suggest (a self-published sample, and
the earlier lean-testing report's finding that agents add tests 1.5x more and
delete them about half as often), so integrity findings should be rare.

**Opinion or practice only (not adopted as a basis for a leaf):** layout-matrix
selection rules and a grep lint for root-computing code, interface snapshots,
golden and differential CLI runs, signed waivers via `git verify-commit`,
journaled finish.

Two leaves below rest on this repository's own observed regressions rather than
on the report: the fixture-pollution guard (regression 6) and the third layout
shape (regression 2).

## Adopted: a land check on the merge commit (`M9.1`, shipped)

`finish-this-task` in merge mode already builds the merge commit locally
(`finish_land_integration._merge_and_push`) and then pushes. It gains one step
between the two: run `land_check_cmd` (a new `roadmap/git-workflow.yaml` key, or
`--land-check-cmd`) at the project root of a detached temporary worktree of
that merge commit. A non-zero exit resets the local integration branch to its
pre-merge commit, pushes nothing and exits 1. A rejected push does the same and
asks for a re-run, which re-merges onto the new tip and re-runs the check, so
the push is the compare-and-swap and no lock file or queue is needed.

This is the only mechanism that catches regressions 1 and 3 and the clean-merge
half of 4, and it is the backstop for 7. It does not trust READY: it runs what
the project configured, on the tree that will become the tip. Off by default;
pr mode never runs it, because there CI owns the merge result.

Cost: one run of the configured gate per landing. For this repository, about 12
minutes of serial pytest plus seconds of static gates, so a 30-leaf night spends
about 6 hours of wall-clock landing, serialised only at finish (executors,
reviews and trial merges stay parallel). Tokens: none.

## Adopted: fixture-pollution guard (`M9.2`, toolkit-internal)

A session hook in `tests/conftest.py` refuses to start `pytest` while any
ignored file sits under `tests/fixtures/` (the `.specyrd/cache` case), naming
each path and `git clean -fdX tests/fixtures`, and fails the session when a run
changes the fixture tree's git status. It catches regression 6 at the first
`pytest` after the manual run, and a test or agent that edits a fixture. Cost:
seconds. Random test order (pytest-randomly) is deferred: it is a new dependency
and the observed failure was pollution, not order.

## Adopted: a third layout shape (`M9.3`, toolkit-internal)

The `layout` fixture covers embedded and nested. Regression 2 needed a nested
project *with a change outside it*. A new test module adds that shape and runs
the finish implementation check, the packet's changed paths and a second
`finish-this-task` (regression 5) over all three. Cost: one small leaf; a few
seconds of test time.

## Adopted: an executor escalation channel (`M9.4`, shipped)

The READY file gains an optional `blocked_on` list of `{acceptance, reason}`.
The executor prompt says: when a criterion can be met only by deleting, skipping
or weakening an existing test, or by raising a baseline or cap, stop and write
READY with `blocked_on` instead. `handoff status` reports `executor_blocked`,
and the gate stays unmet while that READY is current. `AGENTS.md` already
carries the policy half ("never weaken, rewrite or delete a failing behavioural
test"); this adds the channel half, the cheapest measured reduction in the
evidence. It prevents none of the seven directly; it closes the gaming route
around the land check.

## Adopted: test-integrity findings (`M9.5`–`M9.7`, shipped, Python first)

`specy-road integrity <ID>` compares the leaf head with its merge base, reading
git objects only, and prints one line per finding:

- `removed-test`, `removed-test-file`, `new-skip`, `assert-loss` (Python AST),
  `config-change` (`conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, the
  pytest table of `pyproject.toml`) — `M9.5`;
- `new-suppression` (an added line with `noqa`, `type: ignore`, `pragma: no
  cover`, `pylint: disable`, `eslint-disable`, `@ts-ignore`,
  `@ts-expect-error`, `nolint`) and `baseline-widened` (an added line in a path
  listed in `policy.ratchet_paths`) — `M9.7`.

The review packet shows the findings (`M9.5`). With `policy.integrity_gate: true`
in `roadmap/orchestration.yaml` (default false), each finding is a gate problem
unless the leaf declared it (`M9.6`).

**Test changes are declared before any code is written.** A planned test
removal or weakening is part of the leaf: the node's `planned_test_changes`
lists each finding line exactly as `specy-road integrity` will print it, and it
is authored and approved with the leaf, before pickup. The gate reads the node
**from the integration branch**, so the approved leaf is the waiver and no
separate waiver exists; an executor cannot add a declaration from its worktree.
A removal discovered mid-implementation is a `blocked_on` stop (`M9.4`): the
coordinator amends the leaf on the integration branch, and only then does the
work continue. An undeclared finding fails the gate. Removing a test that
another test covers stays allowed by the lean test rules, but it is planned, not
improvised.

Language reach: `removed-test-file`, `config-change`, `new-suppression` and
`baseline-widened` work for any language. The per-function findings are Python
only. Cost: seconds, no tokens. A finding does not prove harm; it is a cheap
deterministic trip-wire, and evidence on real-world weakening says it should
fire rarely.

For this repository the ratchet paths are `constraints/clone-baseline.json`,
`constraints/test-private-imports-baseline.txt`,
`constraints/mutation-baseline.json` and `constraints/file-limits.yaml`; the
C901 baseline is per-function `# noqa: C901`, which `new-suppression` covers.

## Adopted: verified pre-existing claims (`M9.8`, shipped)

Today an approving reviewer's `verify_pre_existing` clears a failing READY
verifier on its own word: an LLM judgement deciding alone. `specy-road review
check-pre-existing <ID>` instead runs each claimed command twice in a detached
worktree of the integration tip and records the exits in
`work/reviews/<ID>/PRE-EXISTING.md`. The gate honours a claim only when both runs
failed at the current tip. Once `M9.1` keeps the tip green, a genuine claim is
rare, so this ranks below the checks that prevent the red tip in the first place.

## Adopted: tests at risk (`M9.9`, shipped, Python first)

`specy-road impact <ID>` lists the test files that import, at any depth, a
changed module (or, with `--zones`, a module under the leaf's touch zones). The
executor prompt carries the `--zones` list at pickup; the packet carries the
changed-files list. A changed `conftest.py` makes the list `ALL`. This is the
TDAD result applied to the executor. Advisory only: it never decides a gate, and
the review-side evidence says more context does not raise reviewer recall, so the
packet gets a list, not caller source.

## Proposed: red-green evidence, opt-in (`M9.10`, shipped, Python first)

With `policy.red_green: true`, the gate requires every test the leaf added or
changed to fail on the merge base (with only the head's test files overlaid) and
pass at head; a test the leaf declares `preserve` must pass on both. A
`specy-road review red-green <ID>` run records the outcomes, bound to the commit.
The basis is BSG-VA: 46.0% of agents' positive validation events carried no
bug-discriminating information, so a passing test alone proves little.

This is test-first evidence, not a test-first instruction. TDAD measured the
difference: a bare "do TDD" instruction *raised* regressions (6.08% to 9.94%),
while a code-to-test impact map cut them to 1.82%. specy-road therefore checks
the evidence (`M9.10`) and supplies the map (`M9.9`) rather than telling agents
to work test-first. It prevents none of the seven observed regressions; it is
the check that catches tests written to pass. Proposed, not approved.

## Open decision: what "green" means

`M9.1` runs a configured command on the merge commit. Whether that command is a
new `land_check_cmd`, the existing pickup `baseline_cmd`, or one definition the
orchestrator settles before it assigns work and the merge path is the
maintainer's call. The direction given: humans and agents both make mistakes, so
the point is to detect them early and always. `M9.1` stays unchanged until
that is settled.

## Mapping: each observed regression to its mechanism

| # | Adopted mechanism | Earliest point it is caught | Notes |
| --- | --- | --- | --- |
| 1 | `M9.1` land check; `M9.7` stops the cap being widened to pass it | executor (when it runs the gate), guaranteed at **finish** | `M3.17` stays as the READY-time signal |
| 2 | `M9.3` third layout shape | **READY** (the executor's full test run) | `M9.1` re-runs it at finish |
| 3 | `M9.1` land check | **finish** | `M9.9` points the executor at the at-risk tests earlier, advisory |
| 4 | Trial merge (exists) for conflicts; `M9.1` for the clean-merge tree | **review** (conflict) / **finish** (clean merge) | |
| 5 | Existing re-run test; `M9.3` extends it to both nested shapes | **READY** | |
| 6 | `M9.2` fixture guard | **executor** (the first `pytest` after the pollution) | |
| 7 | `M9.1` makes review no longer the last line; `M9.5` puts deterministic findings in the packet | **finish** | **Open as a review-recall problem.** No adopted mechanism makes reviewers catch cross-file regressions; the evidence says added context does not |

## Tiered verification policy

| Tier | What runs | Who decides | Time (this repo) |
| --- | --- | --- | --- |
| Executor iteration | Tests the brief names, the `M9.9` at-risk tests, static gates on changed files | executor | seconds to ~2 min |
| READY | Executor-run verifiers recorded in READY (blocking since `M3.17`); `blocked_on` when stuck (`M9.4`) | the gate, from the file | ~1–3 min |
| Each review round | No new toolkit runs. The packet carries the integrity findings (`M9.5`), at-risk tests (`M9.9`) and READY results | reviewers advise, gate decides | seconds plus 2 reviewer runs |
| Trial merge (before review and finish) | Conflict check in memory (exists) | the gate | seconds |
| Finish | `land_check_cmd` on the merge commit (`M9.1`); integrity gate (`M9.6`); verified pre-existing claims (`M9.8`); red-green evidence when opted in (`M9.10`) | deterministic | ~12 min serial |
| Release | The full gate suite in the release runbook; weekly mutmut (`.github/workflows/mutation.yml`, exists) | deterministic | unchanged |

For this repository `land_check_cmd` should be the release gate: `pytest`,
`specy-road file-limits`, `ruff check specy_road tests scripts`,
`scripts/check_clones.py`, `scripts/check_test_private_imports.py`, and the
fixture `validate` / `export --check` / `digest --check`. It is set in
`sr/roadmap/git-workflow.yaml` once `M9.1` lands.

## Constraints the research strains

- **"Holds up against an executor that weakens tests"** cannot be met in full by
  deterministic checks. ImpossibleBench reports that read-only tests stop test
  edits but not special-casing in the code under test. `M9.5`–`M9.7` cover edits
  to tests and baselines; special-casing is left to review, the weekly mutation
  run, and the opt-in red-green evidence of `M9.10`.
- **"General across languages"** holds only for the file-level findings. The
  per-function findings and the import graph are Python only, with no generic
  substitute.
- **"LLM judgements never decide alone"** is violated today by
  `verify_pre_existing`; `M9.8` fixes that.
- **Cost:** the report and the prompt agree a full gate per landing is
  affordable. It serialises finish (about 6 hours for 30 leaves). Batching is
  the only lever on that, and it does not pay at the observed ~20% per-leaf
  failure rate.

## Rejected

- **Speculative parallel candidates:** on one machine they contend rather than
  finish sooner, and capacity is the scarce resource.
- **ML predictive test selection:** needs a large failure history.
- **Signed waivers (`git verify-commit`):** replaced by test changes declared on
  the leaf and read from the integration branch, which an executor cannot write
  either, with no key to manage.
- **Interface snapshots, a grep lint for root-computing code, property tests for
  path logic:** practice or opinion only.
- **Changed-line coverage as a gate:** the report itself warns it invites
  assertion-free tests.
- **LLM monitors for test tampering:** 42–65% detection, and the verdict would be
  an LLM deciding alone.
- **Deriving touch zones from an impact graph:** widens claims and collapses
  parallelism; zones stay declared.
- **`--remerge-diff` approval binding:** a conflict resolution is already a new
  commit on the leaf branch, which voids approvals.

## Deferred

Each one is a candidate follow-up once `M9.1` has data (finish rejections per
landing, time red).

- **Batch-and-bisect at finish**, when finish rejections fall to a few percent.
- **Selected tests on the trial-merged tree before review** (testmon or the
  `M9.9` import graph), to catch regression 3 before reviewers spend tokens.
- **Golden and differential CLI runs on fixture repositories.**
- **Random test order with a recorded seed** at finish and nightly.
- **A journaled, resumable finish** and a landing lock for local-only
  integration branches with no remote to reject a push.
- **Metrics** (`landing-log.jsonl`: escaped regressions per landing, time red,
  late-catch rate, integrity findings and declared test changes).
- **Impact zones in the registry**, to keep leaves whose write and impact zones
  intersect out of the same wave.
