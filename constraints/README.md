# Constraints (specy-road toolkit)

This directory applies to **this repository** — the `specy-road` Python package and docs — not to consumer projects created with `specy-road init project`.

Consumer-style roadmap validation for maintainers uses the sample tree under [`tests/fixtures/specy_road_dogfood/`](../tests/fixtures/specy_road_dogfood/).

| Rule | Where | Check |
|------|--------|--------|
| Max file / function length | [`file-limits.yaml`](file-limits.yaml) | `specy-road file-limits` |
| Dogfood roadmap graph | `tests/fixtures/specy_road_dogfood/roadmap/` | `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` |
