# Principles

1. **Consumer-first CLI** — `pip install specy-road` and `init project` must work without cloning this repo.
2. **Dogfood in fixtures** — Sample roadmap graphs for CI live under `tests/fixtures/`, not as the only story at repo root.
3. **Small, checkable changes** — Prefer extending `specy_road/bundled_scripts/` and tests over one-off scripts.
4. **The CLI never calls a model or search API** — the harness does. The one exception is `brainstorm verify`, which fetches a URL and asks first.
5. **Harness-native** — one-shot CLI adapters, hooks and skills per harness; no daemon and no MCP server.
6. **Separated roles, recorded review** — whoever implements does not approve; a review is a file bound to the commit it read.
7. **The agent advises, the human decides** — brainstorm decisions, review-gate approval, and version numbers are human-owned.
8. **Use the harness's tools and augment them** — specy-road adds roadmap-specific prompts and records on top of the harness's own tools, skills and review commands; it does not reinvent generic agent tooling.
9. **Docs win, smallest change** — tracked repo docs beat chat, and a task takes the smallest change that satisfies it.
