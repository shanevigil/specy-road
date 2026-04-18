# Constraints (specy-road toolkit)

This directory applies to **this repository** — the `specy-road` Python package and docs — not to consumer projects created with `specy-road init project`.

Consumer-style roadmap validation for maintainers uses the sample tree under [`tests/fixtures/specy_road_dogfood/`](../tests/fixtures/specy_road_dogfood/).

| Rule | Where | Check |
|------|--------|--------|
| Max file length (any matched glob) | [`file-limits.yaml`](file-limits.yaml) | `specy-road file-limits` |
| Max function length (**Python `.py` only**, stdlib `ast`) | same | same |
| Optional: `exclude_path_globs`, `override_limits`, `hard_alerts` | same | same (`--strict-hard-alerts` fails on warnings) |
| Roadmap manifest / JSON chunk line caps | same (`roadmap_*_max_lines` keys) | `specy-road validate` (via roadmap loader) |
| Dogfood roadmap graph | `tests/fixtures/specy_road_dogfood/roadmap/` | `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` |

**Non-Python files** matched by `applies_to_globs` are checked for **line count per file** only. Per-function / `hard_alerts.max_lines_per_function` apply to **`.py`** sources in this toolkit; use your stack’s analyzers in CI for other languages.
