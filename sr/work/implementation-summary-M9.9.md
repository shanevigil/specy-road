# Implementation summary: M9.9 — tests at risk

## Summary

New `specy-road impact <ID> [--ref REF] [--zones]` lists the Python test files that
import a leaf's code at any depth. `specy_road/impact.py` reads every `.py` blob at
REF (one `git ls-tree` plus one `git cat-file --batch`, with no checkout), parses the
imports with `ast` (relative imports resolved against the importing file's package,
each parent package counted as imported) and walks the reverse import graph from
the targets to the test files (`test_*.py`, `*_test.py`). Targets are the `.py`
files changed in `merge-base...REF` (diff mode) or the `.py` files under the node's
touch zones at REF (`--zones`). If the diff changes any `conftest.py`, the output is
the single line `ALL`. Otherwise a final `not analysed: <n> files` line counts the
changed files that are not Python, and only appears when n > 0. Paths are git-root
relative, like `specy-road integrity`. Zones are matched against the
project-relative form, like the packet's changed paths. The command is advisory: it
exits 0 whatever it lists, and exits 1 only when the target or git cannot be resolved.

The executor prompt written at pickup (`do_next_prompt.write_agent_prompt`) now has a
`## Tests at risk` section after `## Planned test changes`. It holds the `--zones`
list at the pickup `HEAD` (or `_none found_`). `review-packet` has a
`## Tests at risk` section after `## Test integrity` with the diff list. Both are
rendered by `impact.section_lines`, which shows at most 50 paths and then
`… and <n> more`. The packet section is computed from git objects only, so it is
deterministic for the same refs.

Module naming: a file is importable under its name from its topmost package with an
`__init__.py` (so `src/pkg/api.py` → `pkg.api`, and `tests/helpers.py` → `helpers`)
and under its full git-root dotted path. A name shared by several files links to all
of them, which over-reports rather than under-reports. Out of scope: imports the
static graph cannot see, such as scripts run as subprocesses (for example `cli.py`
→ `python -m specy_road.bundled_scripts.*`) and `importlib` with computed names.
The doc says so.

## Changes

- `specy_road/impact.py` (new): graph, `Impact`, `impact_for_diff`, `impact_for_zones`, `section_lines`.
- `specy_road/bundled_scripts/impact_cli.py` (new): thin CLI on `resolve_target_or_exit`, like `integrity_cli.py`.
- `specy_road/cli.py`: `impact` → `impact_cli.py` in `_SCRIPTS`.
- `specy_road/cli_usage.py`: `impact` usage lines; `review-packet` lists the new section.
- `specy_road/bundled_scripts/do_next_prompt.py`: `_tests_at_risk_lines`, wired into `write_agent_prompt`.
- `specy_road/bundled_scripts/review_packet.py`: `tests_at_risk_section`, wired after test integrity; module docstring renumbered.
- `docs/orchestration-review.md`: new `## Tests at risk` section.
- `CHANGELOG.md`: `[Unreleased] / Added` entry.
- `tests/test_impact.py` (new); `tests/test_review_packet.py`: the provenance-label count goes from 3 to 4, because the new section carries the same `_Computed by review-packet from git_` label as the other git-computed sections. The count is still exact.

Touch zones confirmed: every changed path is inside the declared zones. `generate_brief.py` is not touched, as the planning sheet asks.

## Verification

- `pytest tests/test_impact.py tests/test_review_packet.py tests/test_do_next_prompt.py tests/test_integrity.py tests/test_integrity_gate.py` → 57 passed.
- `specy-road file-limits` → OK.
- `ruff check specy_road tests scripts` → all checks passed.
- `python scripts/check_clones.py` (pylint 4.1.3) → 0 new. One stale baseline entry predates this leaf (refresh_schemas/refresh_stubs).
- `python scripts/check_test_private_imports.py` → 0 new. One stale baseline entry predates this leaf (`review_packet._changed` in `test_review_round6_evidence.py`).
- Full `pytest` → 2766 passed, 2 skipped in 1439s (exit 0).
- Smoke test on this checkout: `python -m specy_road.bundled_scripts.impact_cli M9.9 --zones` printed 153 test files in about 0.9 s.

## Walkthrough

1. Read `tests/test_impact.py::_FILES`, the fixture (10 Python files, with `tests/test_api.py` → `pkg/api.py` → `pkg/core.py` through a relative import), then the three A3 tests: diff, `--zones` and conftest.
2. Check `impact.tests_importing` / `module_names` / `imported_names` against those expectations.
3. Check the two section call sites and the 50 cap (`test_pickup_prompt_lists_zone_tests_capped_at_fifty`, `test_packet_section_lists_diff_tests_capped_and_byte_identical`).

## Added

### Helpers
- `impact.Impact` + `lines()`: one result shape for the CLI output and both sections (ALL / list / not-analysed line).
- `impact.is_test_file`: the A1 test-file rule (`test_*.py`, `*_test.py`).
- `impact.impact_for_diff`: diff mode (A1/A2), with the conftest → ALL short-circuit.
- `impact.impact_for_zones`: `--zones` mode (A1), used by the CLI and the pickup prompt.
- `impact.python_sources` / `_read_blobs`: reads the tree at a commit from git objects in one batch, so the result is deterministic (A5) and fast. Per-file `git show` was too slow for a whole repo.
- `impact.tests_importing`: reverse-graph walk from the targets to the test files.
- `impact._parts` / `module_names` / `_package`: import names for a path, and the base package for relative imports.
- `impact.imported_names`: `ast` import extraction, relative imports resolved, parent packages included.
- `impact.section_lines`: the shared `## Tests at risk` rendering with the 50-path cap (A4/A5).
- `do_next_prompt._tests_at_risk_lines`: the prompt section (A4).
- `review_packet.tests_at_risk_section`: the packet section (A5).

### Branches / guards
- `impact_for_*` return `None` when git cannot answer, and the sections render `_(cannot compute …)_`. Prompt writing must not fail outside a git checkout (existing prompt tests use non-git tmp dirs).
- `_tests_at_risk_lines` skips the computation when `HEAD` does not resolve, for the same reason.
- `tests_importing` keeps module names for targets deleted at REF, so a test that still imports a deleted module is listed.
- `imported_names` ignores unparsable sources (`SyntaxError`/`ValueError`), so fixture files that are not valid Python cannot crash the walk.
- `imported_names` skips a relative import that climbs above the top package (it cannot resolve).
- `python_sources` skips symlinks (mode 120000), whose blob is a path, not source.
- `impact_cli` exits 1 when there is no commit, or no merge base in diff mode, or git fails, matching `integrity_cli`.

### Mocks
- none

### Tests
- `test_diff_lists_tests_through_a_two_level_chain_and_counts_other_files`: A1/A2/A3, exact diff output, including the non-Python count.
- `test_zones_use_the_modules_under_the_touch_zones`: A1/A3, exact `--zones` output, plus a second zone that selects a different test.
- `test_conftest_change_prints_all`: A2/A3, exact `ALL`.
- `test_deleted_module_still_lists_its_importers`: covers the deleted-target guard.
- `test_pickup_prompt_lists_zone_tests_capped_at_fifty` (3 and 55 tests): A4, the list and the cap with a count of the rest.
- `test_pickup_prompt_says_none_found`: A4, the "none found" case.
- `test_packet_section_lists_diff_tests_capped_and_byte_identical`: A5, the diff list, the cap, identical output from two builds, and the section's position in the packet.
