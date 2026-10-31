# Triage: agent-performance and orchestration research (2026-10-30)

Two deep-research runs were requested from the prompt in
`sr/work/research-prompt-agentic-performance-orchestration.md`, seeded by Martin Alderson's
"Making agents fast" (2026-10-29). This note records what each report is worth, which of its
claims about specy-road were checked against the checkout, and what is left for a maintainer to
decide. The report files themselves are untracked root files and are not committed.

## 0. Provenance

| Report | Status |
|---|---|
| `Openai-deep-research-report-agentcoordination.md` | **Off-target.** A generic description of OpenAI's Deep Research product. It never mentions specy-road, the seed article, or any framework in Part A. Treat as a failed run; re-submit the prompt if a second opinion is wanted. |
| `specy-road_ Making CLI-Driven Agent Orchestration Faster and Better Coordinated.md` | **On-target.** Answers Parts A–E, ranks 11 recommendations and 10 patterns, separates verified from inferred, and lists its own gaps (AG2, Semantic Kernel, Gemini CLI effort/resume not verified). The rest of this note is about this report. |

## 1. Landscape verdict, accepted

The report confirms the hypothesis for CrewAI, LangGraph, AutoGen, OpenAI Agents SDK, Google ADK,
smolagents and Pydantic AI: all call provider APIs or LiteLLM with in-process tools. It also shows
the exception list has grown since the 2026-10-27 research: Microsoft Agent Framework's
`ClaudeAgent`/`GitHubCopilotAgent`, LiteLLM's beta `litellm.agent()` over `claude -p` /
`codex exec --json`, and Bernstein (a deterministic, worktree-per-task orchestrator of CLI agents,
beta). Its positioning conclusion is worth adopting in docs: **"CLIs as workers" is no longer the
differentiator; roadmap-first governance is** (roles, fresh-session distinct-family reviewers,
reviews bound to a commit, everything as tracked files). D1–D3 are unaffected.

## 2. "Verify in repo" items, checked

| Report claim or question | Checkout (WIP/improvements-0-3-1 at c900767) |
|---|---|
| Does `worker sync` return only unacknowledged events? | **Yes.** `worker sync` returns every worker's events since the last `--ack` ([worker_cli.py:129-143](../../specy_road/bundled_scripts/worker_cli.py)). |
| Is there a blocking `sync --wait`? | **No.** Polling is per coordinator turn only. |
| Does the Claude adapter re-pass permission mode and output format on resume? | **Yes.** Both launch and resume pass `--output-format stream-json --verbose --permission-mode acceptEdits` ([worker_adapters.py:186-197](../../specy_road/worker_adapters.py)). Cursor resume likewise re-passes `--output-format` and `--force --trust`. Rec. 6 is already satisfied; a fixture test for it may still be worth adding. |
| Does the adapter pin Claude's discovery mode (`--bare` vs full)? | **No.** Nothing passes or guards against `--bare`; the only mention is a hook-guard string. Rec. 1 is a real gap. |
| Do profiles carry effort? | **Partly.** Profiles have `access.effort_map` (profile → harness effort names), read today only by the review-loop RCA. There is no per-role effort, and adapters pass no `--effort` / `-c model_reasoning_effort`. Rec. 2 extends an existing field rather than adding a new one. |
| Does `--implement-mode hook` fan out a wave? | **No.** It runs one `--implement-cmd` per picked leaf, sequentially ([grind_session.py:170-184](../../specy_road/bundled_scripts/grind_session.py)). `max_workers` (default 2) is enforced on `worker delegate` as a slot limit, not used for dispatch. Rec. 5 is a gap. |
| Is usage/cost parsed from harness output? | **Partly.** Claude `total_cost_usd` and Codex `turn.completed.usage` are already captured into event detail ([worker_adapters.py:216-275](../../specy_road/worker_adapters.py)). Not normalised, not per-role, no phase timestamps, no Cursor/Gemini. Rec. 4 / Part E builds on this. |
| Registry write lock for fan-out? | None found beyond the worker lock. Needed only if rec. 5 is built. |
| Output caps with `--full`? | None; `review_node` truncates one list. Rec. 7 is a gap. |
| Opt-in CLI timing? | None. Part E item 4 is a gap. |

## 3. Recommendations, re-ranked after verification

Accepted as candidate leaves, in order. None is scheduled; see §4.

1. **Pin Claude discovery mode** (rec. 1). Add a profile/roster `launch_mode: full|bare` and
   have the Claude adapter assert it on the `init` event. Small, and it protects the design
   intent before `--bare` becomes the `-p` default. Unverified: the exact opt-out flag name.
2. **Per-role effort** (rec. 2). Extend `access.effort_map` with `effort_by_role`; `prompt` and
   `worker delegate` emit the harness flag; clear `CLAUDE_CODE_EFFORT_LEVEL` in the child env.
   Cheapest latency win per the seed article.
3. **Phase timestamps and normalised usage in the event log** (rec. 4 / Part E). The wrapper
   already sees cost and usage; add `launch`/`first_output`/`ready` phase events and a `usage`
   event with nullable fields. Enables measuring everything else.
4. **`worker sync --wait [--timeout]`** (rec. 3). A foreground stat-loop or file-watch in the
   CLI process. Decision needed on whether this fits D3 (it is not a daemon; it lives for one
   tool call).
5. **Output budgets** (rec. 7) and **lazy imports / validation cache** (rec. 8). Measure first;
   the report's start-up numbers are estimates.
6. **Deterministic wave fan-out** (rec. 5). Largest piece; depends on 3 and 4 and on a registry
   lock. Defer until the above have produced measurements.
7. **Docs only**: sandbox preflight (rec. 10), shell-environment hygiene (rec. 11), and the
   positioning sentence from §1 in `docs/philosophy-and-scope.md`.

Already done or dropped: rec. 6 (resume hygiene) is implemented; rec. 9 (SIGINT interrupt on
Claude) stays "unsupported" until a second adapter can offer it, to keep the capability uniform.
All six rejected patterns in the report (in-process tools, LLM routers, daemons, memory stores,
model-call retries, LiteLLM harness as adapter) are rejected here too, for the D1–D3 reasons it gives.

## 4. Maintainer decisions needed

- Whether a blocking `sync --wait` is acceptable under D3's wording.
- When Claude flips `-p` to bare: default executors to full discovery (design intent) or to
  explicit config (reproducible, loses user skills)?
- Which of §3 items 1–3 go into the next batch, and whether they belong on this line or 0.3.2.
  Version numbers stay human-owned.
- Whether to re-run the off-target OpenAI report for a second opinion.

## 5. Secondary-source claims not to repeat as fact

`--bare` start-up gain (14% vs "10×", disputed); `CLAUDE_CODE_EFFORT_LEVEL` precedence over
`--effort`; Systima's ~32,800-token first-turn payload (a replication found inflated counts);
Bernstein's 43%→0% merge-conflict figure; Cursor CLI hooks not firing on Linux. Every timeline
number in the report is the author's estimate.
