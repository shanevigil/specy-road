# Reviewer effort study: does a lower effort change review verdicts?

**Status:** live design (roadmap leaf `M10.6`, run 2026-11-02). The shipped
`effort_by_role` defaults in `specy_road/templates/project/model-profiles/`
cite this note.

## Question

`M10.5` made effort a per-role profile field and kept the reviewer at each
model's documented default. Its only reason to lower that default was one
practitioner post ("Check thinking budgets! This is overwhelmingly the lowest
hanging fruit", martinalderson.com/posts/making-agents-fast). Principle 7 keeps
the gate human-owned, so a reviewer default moves only on evidence. This note
measures whether a reviewer one level below its usual effort reaches the same
verdict, for the same reasons, on packets the gate has already decided.

## Decision rule

A model family's reviewer default is lowered only when, on **every** packet,
the two levels give the same verdict **and** their block reasons overlap (both
empty on an approve; on a block, at least one reason names the same defect).
Anything else keeps the default.

## Protocol

- **Tool:** `scripts/review_effort_study.py`. It runs only the roster entry's
  `channels.cli` (never a model API), once per packet, model and level, and
  writes `results.csv` with one row per run: node, commit, model, family,
  level, verdict, block reasons, exit code, seconds. A level reaches the
  command as `M10.5` passes effort: `{effort}` for a harness with an effort
  flag, and the model id's effort suffix on Cursor, whose ids carry the effort
  (`grok-4.7-high` → `grok-4.7-medium`).
- **Prompt:** a short study preamble, then the recorded `PACKET.md` unchanged.
  The reviewer judges from the packet alone, runs no commands, files nothing,
  and ends with a YAML block (`verdict`, `block_reasons`) the script reads.
  Each run gets its own scratch directory outside the repository.
- **Packets:** the latest packet of three leaves of this line, each for the
  commit the gate finally approved (table below).
- **Levels:** `high` (the roster's level for both reviewers) and `medium`.
- **Budget:** the maintainer's cap is 12 reviewer runs; the script refuses a
  larger study before running anything.

### Deviation: Sol ran on Cursor, not Codex

The roster's Codex Sol reviewer (`gpt-6.1-sol`) runs
`sr/tools/codex-review.sh gpt-6.1-sol "<prompt>"`, which names no `{effort}`,
so both levels would have run the same command; the script refuses it. The
`openai` family was measured through the roster's Cursor entry
`gpt-5.6-sol-high` instead. To measure GPT-6.1 Sol on Codex, add `{effort}` to
that `channels.cli` and have the wrapper pass it to `codex exec`.

## Packets used

| Node | Commit under review | What it changed |
| --- | --- | --- |
| `M3.16` | `89bd140df3ae9c77f23305af81a7396efc933506` | Bring worker_cli and worker_adapters back under the 400-line cap |
| `M9.1` | `ea48cee75ca557bca31d4661412a2005bcb7ae2f` | finish-this-task runs a configured land check on the merge commit before it pushes |
| `M3.13` | `b28c1982acd4023478bce8d3cb2d3e3fcb871765` | A trial merge with the integration branch runs before review and before finish |

Reproduce one packet's rows with:

```bash
python scripts/review_effort_study.py --repo-root sr --model grok-4.7-high --model gpt-5.6-sol-high \
  --levels high medium M3.16 -o <dir>
```

## Results

**Reviewer runs: 12 of the 12 budgeted** (3 packets × 2 levels × 2 models).
Every run exited 0 and ended with a verdict block the script could read.

| Node | Model (family) | Level | Verdict | Block reasons | Seconds |
| --- | --- | --- | --- | --- | --- |
| `M3.16` | `grok-4.7-high` (xai) | high | approve | | 230 |
| `M3.16` | `grok-4.7-high` (xai) | medium | approve | | 120 |
| `M3.16` | `gpt-5.6-sol-high` (openai) | high | block | A2 fails: `worker_adapters` removes the public `PLACEHOLDERS` and `has_prompt_placeholder` names instead of re-exporting them | 12 |
| `M3.16` | `gpt-5.6-sol-high` (openai) | medium | block | A2 fails: `worker_adapters.has_prompt_placeholder` was removed instead of re-exported | 8 |
| `M9.1` | `grok-4.7-high` (xai) | high | approve | | 388 |
| `M9.1` | `grok-4.7-high` (xai) | medium | approve | | 387 |
| `M9.1` | `gpt-5.6-sol-high` (openai) | high | approve | | 20 |
| `M9.1` | `gpt-5.6-sol-high` (openai) | medium | approve | | 23 |
| `M3.13` | `grok-4.7-high` (xai) | high | approve | | 379 |
| `M3.13` | `grok-4.7-high` (xai) | medium | approve | | 306 |
| `M3.13` | `gpt-5.6-sol-high` (openai) | high | approve | | 33 |
| `M3.13` | `gpt-5.6-sol-high` (openai) | medium | approve | | 27 |

Wall time per family, high → medium: Grok 997 s → 813 s (−18%); Sol 65 s →
58 s.

Sol's block on `M3.16` names the same defect at both levels, so the reasons
overlap. That block also disagrees with the gate's recorded approvals of that
commit (GPT-6.1 Sol and Grok 4.6). At that commit nothing imported the name
from `worker_adapters`, so the block reads A2's wording strictly rather than
finding a breakage. It is evidence about agreement between levels, which is
what this note measures, not about whether the block was right.

## Decision per family

| Family | Rule met? | Decision |
| --- | --- | --- |
| `xai` (Grok 4.7 on Cursor) | Yes: same verdict on 3/3 packets, no block reasons at either level | A medium reviewer is supported. On Cursor the effort is in the model id, so this is a roster choice (`grok-4.7-medium`), not a profile default; the shipped Grok profiles carry no `effort_by_role` and stay unchanged. |
| `openai` (GPT-5.6 Sol on Cursor) | Yes: same verdict on 3/3 packets, overlapping reasons on the one block | A medium reviewer is supported for GPT-5.6 Sol on Cursor (`gpt-5.6-sol-medium`), again a roster choice. GPT-6.1 Sol on Codex was **not** measured (see *Deviation*), so the shipped Sol profiles stay unchanged. |
| `anthropic` (Claude) | Not measured | The shipped Claude profiles keep `reviewer` at the documented default (Opus 5.5 `medium`, Opus 5 and Fable `high`); each `effort_by_role` line cites this note. Lowering it needs a Claude run of this study. |

## Limits of this evidence

- **Three packets, mostly approvals.** All three were the commits the gate
  finally approved, and 10 of the 12 runs approved. Agreement on approvals
  says little about whether the lower level would miss a real defect. A
  stronger study adds packets from rounds that were blocked; packets are
  overwritten each round, so such a packet has to be kept when it is written.
- **Packet only.** The replay runs no commands. The gate's reviewers rerun the
  verifiers (`reviewer_reruns_required`), and the effort spent there is not
  measured.
- **One run per cell.** No repeat runs, so run-to-run variance at one level
  is not separated from the effect of the level.
- **Packets picked by the executor.** The approach asks a human to pick the
  packets; the executor picked these three within the budget, so the
  maintainer can rerun with their own pick.
