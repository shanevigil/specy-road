# Principles

1. **Consumer-first CLI** — `pip install specy-road` and `init project` must work without cloning this repo.
2. **Dogfood in fixtures** — Sample roadmap graphs for CI live under `tests/fixtures/`, not as the only story at repo root.
3. **Small, checkable changes** — Prefer extending `specy_road/bundled_scripts/` and tests over one-off scripts.
