# Implementation summary — M11.66 (`version-shows-checkout-sha`)

## What changed

- Added `specy_road/toolkit_version.py` with `running_toolkit_version()`: semver from `__version__`, plus `+<12-char HEAD>` only when the package lives in the toolkit’s own git checkout (`specy_road_package_dir().parent == git root` and `git ls-files --error-unmatch` on `specy_road/__init__.py`), with `.dirty` when that worktree is not clean; plain semver for wheels, copied trees, and venv installs inside unrelated repos.
- `specy-road --version` prints `specy-road {running_toolkit_version()}` via `specy_road/cli.py`.
- `version_skew.py` re-exports `running_toolkit_version`; skew warnings still compare pins to plain `__version__`.
- Worker YAML records store `toolkit_version` at delegation time (`worker_state.create_record`).
- `render_front_matter` does not stamp. `stamp_review_toolkit_version` runs only in `review record` and interactive human approve immediately before `sign()`, always setting `toolkit_version` to `running_toolkit_version()` (overwriting any value copied into reviewer notes). Independence relabel re-renders do not call the stamp helper.
- JSON schemas: optional `toolkit_version` on `review-record` and `worker-record`; handoff schema unchanged.
- Merged `origin/WIP/improvements-0-3-1` (M11.27, M11.39, M11.67, M11.74 among others); `review_cli.py` keeps both `stamp_review_toolkit_version` and WIP `gate_policy_summary`.

## Touch zones

| Path | Role |
|------|------|
| `specy_road/cli.py` | `--version` output |
| `specy_road/version_skew.py` | Re-export |
| `specy_road/toolkit_version.py` | Checkout detection + stamp helper |
| `specy_road/worker_state.py` | Worker record field |
| `specy_road/review_gate_ready.py`, `specy_road/bundled_scripts/review_cli.py` | Stamp before sign |
| `specy_road/review_files.py` | Front matter render only |
| `specy_road/schemas/review-record.schema.json`, `worker-record.schema.json` | Optional field |
| `tests/` | Behaviour coverage |

## Verification

- `pytest` (full suite)
- `specy-road file-limits`

## Added (behaviour)

- `_toolkit_git_root()` — limits SHA suffix to tracked toolkit checkout.
- Unconditional stamp at filing — filed REVIEW always records the running build, even when notes front matter includes `toolkit_version`.
- `test_record_overwrites_bogus_toolkit_version_in_notes` — `review record` integration check.
