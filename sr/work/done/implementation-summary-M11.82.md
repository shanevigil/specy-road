# Implementation summary: M11.82 (`wip-ruff-clean`)

## What changed

- **A1** — `ruff check specy_road tests scripts` passes (it reported two C901 errors at base).
  - `specy_road/bundled_scripts/review_packet_uncommitted_refs.py`: `uncommitted_refs_section`
    (complexity 12) now gathers texts with `_packet_texts` and finds missing paths with
    `_missing_refs`. Same order of texts (brief, implementation summary, chain sheets), same
    commit-then-disk fallback, same output. Signature unchanged.
  - `specy_road/orchestration_config.py`: `load_availability_overlay` (complexity 14) now reads
    the file's roster with `_overlay_roster` and checks each entry with `_overlay_patch`. Same
    errors in the same order, same `None`/`{}` returns. Signature unchanged.
- **A2** — `sr/roadmap/git-workflow.yaml` `land_check_cmd` is now
  `python -m ruff check ../specy_road ../tests ../scripts && python -m pytest -n auto -p no:cacheprovider ../tests`
  (one shell command; cwd is `sr/`, and ruff picks up the git-root `pyproject.toml` config,
  checked with `--show-settings`: max_complexity 10). `docs/git-workflow.md` adds an example
  that puts the linter ahead of the tests when CI enforces it, and says why.

## Touch zones

Final list as given. `specy_road/orchestration_local_overlay.py` was not needed (no file-limits
pressure: `specy-road file-limits` is OK) and was not created. No call site changed: both public
functions keep their signatures.

## Verification

- `ruff check specy_road tests scripts` — pass
- `python -m ruff check ../specy_road ../tests ../scripts` from `sr/` (the land check's lint step) — pass
- `python -m pytest -p no:cacheprovider tests/test_review_packet.py tests/test_roster_availability.py tests/test_agent_ignores.py` — 53 passed, unchanged tests
- `python -m pytest -n auto -p no:cacheprovider tests` — 3550 passed, 2 skipped
- `specy-road file-limits` — OK
- `specy-road validate` — OK

## Added

### Helpers
- `_committed_or_disk` (review_packet_uncommitted_refs.py) — a file's text at the commit, else on disk; shared by the summary and sheet reads that were two copies of the same fallback.
- `_packet_texts` (review_packet_uncommitted_refs.py) — collects the brief, summary and sheet texts, moved out of `uncommitted_refs_section` for C901.
- `_missing_refs` (review_packet_uncommitted_refs.py) — the per-text/per-path loop, moved out for C901.
- `_overlay_roster` (orchestration_config.py) — YAML read and mapping/roster shape checks, moved out of `load_availability_overlay` for C901.
- `_overlay_patch` (orchestration_config.py) — per-entry checks, moved out for C901.

### Branches or guards
none

### Mocks
none

### Tests
none (A1 requires the existing tests to pass unchanged; A2 needs no test)
