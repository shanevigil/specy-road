# Context-feedback pilot (M5.6)

**Status:** live design (the flag and the triage rule); the results table is a dated record.
**Decision pending:** whether the block ships in the implementation-summary template by default.

## Question

Agents sometimes report that their brief or prompt was missing something, wrong, or padded.
Before asking that of every implementation summary, the toolkit needed to know whether such
reports reproduce when checked, or are mostly noise that a reviewer would have to triage.

## What exists

`specy-road prompt <ID> --role executor --context-feedback` (opt-in; `CONTEXT_FEEDBACK_LINES`
in `specy_road/bundled_scripts/role_prompt.py`) appends a block that asks the executor to end
its implementation summary with a `## Context feedback` section of exactly three lines:

- `missing:` what the brief or prompt should have said and did not, quoting the line that should
  have said it or naming the turn where the executor found it out;
- `wrong:` a brief or prompt line that was false or out of date, quoted;
- `unused:` a brief or prompt section never needed, by heading.

`none` is a valid answer on each line. The default prompt is unchanged; `worker delegate` and
`worker reconcile` build the default prompt.

## Triage rule

Act on an item only when it

1. **cites**: quotes a brief or prompt line, or names a turn; and
2. **reproduces**: recurs in another run (same or another leaf), or holds when the quoted line is
   read against the brief and the run's transcript.

An item that fails (1) is dropped unread. One that passes (1) but not (2) is recorded and left.
`none` is a result, not a blank. Hit rate = items passing (2) / items offered.

## Pilot (2026-11-02)

Maintainer decision: run locally, not in the sandbox VMs, because the question is about prompt
behaviour. Setup: three closed leaves replayed from their briefs, two runs each (six executor
runs, the cap the planning sheet set), each in a fresh scratch clone of this repository checked
out at the leaf's registration commit on its `feature/rm-<slug>` branch, with the brief rendered
into `sr/work/`. The executor prompt was rendered once per leaf with the candidate code
(`--model claude-fable-5-1 --role executor --context-feedback`) and sent verbatim to a fresh
Claude session, with two operator overrides: skip `specy-road ready` (it writes into another
checkout) and run `specy-road` and `pytest` through the project interpreter from the clone root.

| Leaf | Base commit | Prompt `sha256` (first 12) |
| --- | --- | --- |
| `M10.19` no-foreign-kills | `14019e0b` | `5f6999d56b3d` |
| `M10.18` review-file-case | `3a54d407` | `b7a206095a58` |
| `M10.17` packet-byte-budget | `d65b0856` | `23d8008953db` |

### What the six runs returned

Every run completed the leaf (implementation and summary committed in its clone, targeted tests and
`file-limits` at exit 0) and ended its summary with the three lines. Items are counted per line;
`none` is not an item. "Cited" is triage rule (1); "reproduced" is rule (2), checked by reading the
quoted line against the brief and the base commit (line counts, command presence, touch zones).

| Run | missing | wrong | unused | offered | cited | reproduced |
| --- | --- | --- | --- | --- | --- | --- |
| `M10.19/r1` | brief says the docs file "is near its cap"; it was 400/400 and the test file 399/400 | prompt names `specy-road ready`, absent at the base commit; its may-not list already carries the rule the leaf adds | Model notes; Rollup semantics | 3 | 3 | 3 |
| `M10.19/r2` | same cap item, found when `file-limits` failed on a 7-line test | "Add one or two lines to `docs/orchestration-workers.md` … (near its cap)": the file is at the cap | Model notes | 3 | 3 | 3 |
| `M10.18/r1` | "Verify with the review-file tests and file-limits" did not say `review_files.py` was 397/400 | the brief's "normalise the reported name" presumes reporting sites that sit outside the touch zones (`review_gate.py`, `mark_implementation_reviewed.py` print `path.name`) | Model notes; Rollup semantics | 3 | 3 | 3 |
| `M10.18/r2` | same 397/400 item | `none` | Model notes; Rollup semantics | 2 | 2 | 2 |
| `M10.17/r1` | "Verify with … the docs line" names no file; the only line-cap prose is `docs/dev-workflow.md:211`, outside the zones | the brief file in `sr/work/` and the brief inlined in the prompt differ (the file has `## 9. History`) | Model notes; Rollup semantics | 3 | 3 | 3 |
| `M10.17/r2` | same docs item, plus `cli_usage.py:161` outside the zones | "If the module nears its cap, move the budget logic into a helper module": a new module is outside the touch zones | Model notes; Rollup semantics | 3 | 3 | 3 |
| **Total** | | | | **17** | **17** | **17** |

**Hit rate: 17 / 17 offered items cited a line or turn, and 17 / 17 reproduced** (every item recurred
in another run or held against the brief and base commit). The two runs per leaf agreed on the
`missing` item every time and on the `unused` item every time.

### What the 17 items are, deduplicated

1. **Line-cap headroom** (6 of 6 runs, `missing`; 1 `wrong`). Every brief named a file that was at
   or within three lines of the 400-line `file-limits` cap and said at most "near its cap". Executors
   found out from a failing `file-limits` run and spent turns compacting unrelated text.
2. **Touch zones narrower than the brief's approach** (3 `wrong`). The brief suggested a helper module,
   a docs line, or a "reported name" fix whose files were outside the declared zones; the executor had
   to leave them stale and say so.
3. **Model notes are not executor advice** (6 of 6 runs, `unused`). The profile's prompting rules as
   rendered (forced tool use, turn-scoped system messages, "use Opus first") address an API caller, not
   an agent editing files. **Rollup semantics** (5 of 6) was unused by every executor that mentioned it.
4. **Replay artefacts** (2 `wrong`): the prompt was rendered by the candidate code against a base
   commit that predates `specy-road ready`, and the inlined brief omits the file's git-history section.
   Both are true and both are consequences of this pilot's setup, not of a live run.

### Reading

The block is cheap (three lines, answered in every run) and the triage rule did not have to drop
anything: agents cited lines and turns when asked to. The signal is dense but narrow: six runs produced
four distinct findings, two of them already real work items (1 and 3), one a brief-authoring rule (2),
one noise from the replay (4). The two-runs-per-leaf design mattered less than expected because the
same leaf's runs agreed; recurrence across leaves is what separated findings 1–3 from 4.

### Decision left open

Shipping the block in the implementation-summary template by default is a separate decision. What
this pilot settles: the triage rule above is enough to read the lines in under a minute per summary,
and the first three findings are worth acting on regardless (a brief that names a file should carry
its `file-limits` headroom; a brief's approach text must stay inside the touch zones or widen them;
the executor prompt should render only the profile rules that address an executor).
