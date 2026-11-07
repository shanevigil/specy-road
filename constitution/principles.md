# Principles

Principle numbers are stable references (code comments and plans cite them), so the two groups below keep their original numbers.

## Product invariants

What specy-road guarantees to every project that installs it.

4. **The coordination CLI never calls a model or search API** — claims, briefs, workers, the review gate and brainstorm sessions leave that to the harness. The named exceptions are the opt-in `review-node` command (advisory LLM review, your own API key), `brainstorm verify` (fetches one URL and asks first), and the GUI's configured search and LLM providers.
5. **Harness-native, no daemon** — one-shot CLI adapters, hooks and skills per harness; no daemon and no MCP server. The PM GUI is a local server the user starts, and detached workers are processes a command launches: neither is a coordination daemon nor an MCP server.
6. **Separated roles, recorded review** — the session that implements a leaf does not review it, and a review is a file bound to the commit it read; the one exception is a human approving interactively in `mark-implementation-reviewed`, which is recorded as such (`is_coordinator: true`).
7. **The agent advises, the human decides** — the review gate closes deterministically from recorded reviews, by a human interactively or by `--yes` in unattended mode only for an approval those records already earned; brainstorm decisions, review policy, triage and version numbers are human-owned.
8. **Launch the harness, add the roadmap layer** — specy-road launches the team's agent CLIs as workers and adds roadmap-specific prompts, records, guards and supervision on top of each harness's own tools, skills and review commands; the roster names which harness and model fill each role, and model profiles are data the team chooses from.

## Engineering rules for this repository

1. **Consumer-first CLI** — `pip install specy-road` and `init project` must work without cloning this repo.
2. **Dogfood in fixtures** — Sample roadmap graphs for CI live under `tests/fixtures/`, not as the only story at repo root.
3. **Small, checkable changes** — Prefer extending `specy_road/bundled_scripts/` and tests over one-off scripts.

And for every change in this repository:

9. **Docs win, smallest change** — tracked repo docs beat chat, and a task takes the smallest change that satisfies it: one test per observable behaviour, and no guard without a reachable trigger.
