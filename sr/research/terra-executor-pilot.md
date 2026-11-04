# GPT-6.1 Terra as an executor: pilot findings (M10.20)

Run 2026-11-03 by `claude-opus-5.5` as the M10.20 executor. Three already-landed Agentic-led leaves were replayed from their claim commits with `gpt-6.1-terra` on the Codex CLI. Two of the results were then reviewed by Grok and an Anthropic reviewer. Nothing was merged or pushed. This is a small pilot (n = 3), not a benchmark.

## Recommendation

**Roster it as an executor for small Agentic-led leaves, with three conditions.** In this pilot, Terra's two reviewable results were approved by both reviewers in the first round. It took a quarter to two-thirds of the landed Opus turn's wall time and produced a smaller diff. These three conditions come from what the pilot showed:

1. **Give it a launch that can commit.** The default Codex executor launch is `CODEX_POLICY` (`sandbox_mode=workspace-write`) in `specy_road/worker_adapter_base.py`. In a linked worktree, that sandbox denies writes to the git metadata under the main checkout's `.git/worktrees/`, even when that directory is passed with `--add-dir`. The first replay finished its work but could not commit. Until the adapter handles this, the roster entry needs a `channels.cli` that grants it. The pilot used `-s danger-full-access`, which matches the Claude worker's `--dangerously-skip-permissions`. Something narrower would be better.
2. **Route its reviews to Grok plus the Anthropic reviewer (or a human).** Terra is `family: openai`, so a Sol approval cannot count for a Terra-executed leaf. With `reviewers_distinct_families: true`, the only roster pair that can approve one is xai + anthropic: `grok-4.7-high` or `cursor-grok-4.6-high`, plus `claude-opus-5-5-review`. Every Terra leaf therefore spends one Anthropic review. `claude-review.sh` describes that channel as a fallback "used sparingly", so some of the Claude cost moves from execution to review.
3. **Do not count on it to relieve the OpenAI rate limit.** On the Codex route, Terra runs on the same ChatGPT/Codex login and usage limit as the Sol reviewers (the user's `~/.codex/config.toml` already defaults to `gpt-6.1-terra`). It is not on a separate limit, and Terra executors draw down the budget that stalled the Sol review gate twice on 2026-11-02. Cursor does not offer GPT-6.1 Terra (see A1), so it is no way around that limit either. While OpenAI routes are rate-limited, Terra execution stalls with them, though its reviews (Grok + Anthropic) do not. Claude-executed leaves keep using Grok + Sol, so one rate-limited day stalls Sol-reviewed Claude leaves and Terra execution at the same time.

The reviewers' main reservation was test depth. Terra wrote one test per acceptance item where the landed version split cases, and it once skipped a case the landed version covered (M11.77, the stale-commit record). Where acceptance wording names a case, the prompt should ask for a test of that case.

If the maintainer rosters it, a starting entry looks like this (not added by this leaf; Approach says not to change roster defaults here):

```yaml
  - id: gpt-6.1-terra
    family: openai
    roles: [executor]
    profile: model-profiles/openai-gpt/gpt-6.1-terra.md
    harness: codex
    # plus a channels.cli that lets codex write the worktree's git metadata (condition 1)
```

## A1, A4: availability and the capture

| Inventory | Version | GPT-6.1 Terra |
|---|---|---|
| `codex debug models` | `codex-cli 0.165.0` (installed; the A4 recheck on 0.166.0+ was not needed) | **present**: slug `gpt-6.1-terra`, display "GPT-6.1 Terra", `visibility: list`, `supported_in_api: true` |
| `cursor-agent --list-models` | `2026.10.22-27dcf5f` | **absent**; only `gpt-5.6-terra-{none,low,medium,high,xhigh,max}[-fast]` |

The Terra catalog entry from codex-cli 0.165.0, captured 2026-11-03 with `base_instructions` omitted:

- `default_reasoning_level: low`
- effort levels `low, medium, high, xhigh, max, ultra` (`ultra` = "Maximum reasoning with automatic task delegation")
- `context_window: 500000`, `max_context_window: 872000`, `effective_context_window_percent: 95`
- `tool_mode: code_mode_only`, `shell_type: unified_exec`, `apply_patch_tool_type: freeform`
- `multi_agent_version: v2`, `multi_agent_reasoning_effort: xhigh`
- `service_tiers: priority` ("Fast", 1.5x speed), `default_verbosity: low`, input modalities text and image

The full catalog (slug, display name, visibility) at that capture: `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6.1-terra`, `gpt-6-sol`, `gpt-reserve` (hidden), `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `codex-auto-review` (hidden).

The fixture capture at `model-profiles/harness-captures/codex/version.txt` says `codex-cli 0.166.0`, but this machine runs 0.165.0. Terra is already in the 0.165.0 catalog.

## A2: replays

### Protocol

- Each leaf was replayed in its own linked worktree at the leaf's claim commit, the `base:` of its saved executor prompt. Each replay ran on a local branch `pilot/terra-<ID>`, which was never pushed.
- Each run used the saved prompt `work/prompt-<ID>-executor-claude-opus-5.5.md`, verbatim except for three edits: the header model, the branch name, and step 4's `specy-road ready`. That step would have overwritten the real hand-off, so it was replaced by "list each verifier and its exit code in the final reply".
- The run command was `codex exec -m gpt-6.1-terra -c model_reasoning_effort=medium --json -C <worktree> - < prompt`.
- Wall time is launch to exit. M11.65 and M11.73 ran in parallel.
- Each reviewer ran as a single fresh session through the roster channels `cursor-review.sh cursor-grok-4.6-high` and `claude-review.sh medium`. These are the same reviewer ids that approved the landed versions.
- The reviewer prompt asked for an Acceptance / Correctness / Regression / Boundary / Test integrity / Excess record and a verdict at the real gate's bar. Only after the verdict did it show the landed round-1 diff for a comparison section. Reviewers printed their records instead of filing them, so `work/reviews/` was not touched.

### Results

| Leaf | Terra outcome | Wall | Tokens: input (cached) / output (reasoning) | Verifiers | Grok | Anthropic | Landed Opus first turn |
|---|---|---|---|---|---|---|---|
| M11.65 why-blocked plan holds | Implemented; **could not commit** (sandbox; see condition 1). The pilot committed its unchanged work as `1ce36bc2` | 288 s | 1,745,721 (1,705,600) / 5,246 (479) | pass: 3 test files, 36 passed; file-limits 0; private-imports 0 | approve | approve | 812 s, $1.27 reported; +226/-5; round 1 **blocked by Sol** (private `_leaf` test import), approved after a fix round |
| M11.73 ready warns on integration conflict | **Stopped** with no changes: `cmd_ready` lives in `specy_road/review_gate_ready.py`, outside the zones | 38 s | 154,444 (127,104) / 957 (117) | none run | not reviewed | not reviewed | 596 s, $0.77; added an out-of-zone module `review_ready_merge.py` (file-limits escape) and a one-line import swap; zone added afterwards; approved |
| M11.77 run record, no false failure | Implemented and committed (`453ab4e3`) with `danger-full-access` | 211 s | 1,237,185 (1,201,152) / 3,744 (556) | pass: 3 test files, 77 passed; file-limits 0; private-imports 0 | approve | approve | 328 s, $0.80; +130/-2; approved round 1 |

Terra's diffs, including the implementation summary: M11.65 +73/-1 and M11.77 +43/-3. The landed round-1 versions were +226/-5 and +130/-2.

Terra's final reply on M11.65 reported `pytest=0`. The event log confirms that a first run failed on a JSON comma in its own new fixture, and the rerun after the fix passed (21 passed). That claim held up.

### What the reviewers said against the landed versions

- **M11.65.** Both reviewers called the landed version better product work: a nested `plan_hold.pickup_honours`, updated `--help`, a named constant, and five focused tests. Both called Terra's version minimal, correct and acceptance-complete. Terra's version also avoided the private test-helper import that drew Sol's round-1 block on the landed version.
- **M11.77.** Grok preferred Terra's version, because closing the run first and reading `close_run`'s state checks the record once. The Anthropic reviewer judged Terra's code fix leaner and the landed tests stronger, because the landed tests include a stale-commit case that tests acceptance's "for that commit" directly.
- **M11.73.** There was nothing to review. Terra's stop follows the prompt's rule literally ("A needed change outside the touch zones stops this leaf"). Opus used the file-limits escape (a new module plus an import swap in a zoned file) and still needed a later zone edit. Terra's stop is defensible, but it got no work done in a case where a workaround existed. A Terra roster entry should expect more out-of-zone stops on leaves whose zones are tight.

### Usage and cost

There is no verified per-token price for GPT-6.1 Terra in the repo, and Codex runs on a ChatGPT login are charged against the plan's usage limit, not in dollars. As a ceiling, assume Terra costs no more per token than GPT-6.1 Sol's profile price ($2 input, $0.10 cached input, $10 output per million tokens). On that assumption the runs cost at most about $0.30 (M11.65), $0.08 (M11.73) and $0.23 (M11.77). The landed Opus first turns reported $1.27, $0.77 and $0.80 (Claude Code's API-equivalent `total_cost_usd`; billed on the Claude subscription). Terra's output tokens were about a third of Opus's on the same leaves (5.2K vs 14.9K, 3.7K vs 9.7K).

### Run count

There were 7 model runs (3 executor, 4 reviewer), against a cap of about 6. The third replay (M11.77) was added because M11.73 produced nothing to review, which would have left one reviewable result.

## Profile

The recommendation is yes, so `model-profiles/openai-gpt/gpt-6.1-terra.md` records the catalog facts above and this pilot's observations. It has no vendor research run behind it, and no price.
